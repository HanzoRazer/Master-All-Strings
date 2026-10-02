import assert from "node:assert/strict";
import test from "node:test";

import { mountReceivedLessonRuntime } from "../received_lesson_runtime.js";
import { preparationBody } from "./lesson_practice_fixture.js";

function createElement() {
  const node = {
    children: [],
    style: {},
    dataset: {},
    className: "",
    textContent: "",
    clientWidth: 640,
    clientHeight: 280,
    listeners: {},
    classList: {
      add(...names) {
        node.className = `${node.className} ${names.join(" ")}`.trim();
      },
      remove() {},
      toggle(name, force) {
        if (force) node.className = `${node.className} ${name}`.trim();
        return Boolean(force);
      },
      contains(name) {
        return node.className.split(/\s+/).includes(name);
      },
    },
    appendChild(child) {
      this.children.push(child);
      child.parent = this;
      return child;
    },
    append(...children) {
      for (const child of children) this.appendChild(child);
    },
    replaceChildren(...children) {
      this.children = [];
      for (const child of children) this.appendChild(child);
    },
    querySelectorAll(selector) {
      const names = selector.split(",").map((part) => part.trim().slice(1));
      const found = [];
      const walk = (current) => {
        for (const child of current.children || []) {
          const classes = (child.className || "").split(/\s+/);
          if (names.some((name) => classes.includes(name))) found.push(child);
          walk(child);
        }
      };
      walk(this);
      return found;
    },
    remove() {
      if (!this.parent) return;
      this.parent.children = this.parent.children.filter((child) => child !== this);
    },
    addEventListener(type, handler) {
      this.listeners[type] = handler;
    },
    removeEventListener(type) {
      delete this.listeners[type];
    },
    setAttribute(name, value) {
      this.dataset[name] = value;
    },
  };
  return node;
}

function roots() {
  const fretboard = {
    laneLabels: createElement(),
    scrollViewport: createElement(),
    scrollCanvas: createElement(),
    playLine: createElement(),
    gutterNotes: createElement(),
    unplayableGutter: createElement(),
    neckMap: createElement(),
    instrumentTitle: createElement(),
  };
  return { fretboard, tab: createElement(), notation: createElement() };
}

function scheduling() {
  const timers = new Set();
  let frame = null;
  let scheduled = 0;
  return {
    timers,
    scheduled: () => scheduled,
    requestAnimationFrame(callback) {
      scheduled += 1;
      frame = callback;
      return scheduled;
    },
    cancelAnimationFrame() {
      frame = null;
    },
    setIntervalFn(callback) {
      const timer = { callback };
      timers.add(timer);
      return timer;
    },
    clearIntervalFn(timer) {
      timers.delete(timer);
    },
    frame(nowMs) {
      frame?.(nowMs);
    },
  };
}

class FakeSynth {
  constructor() {
    this.readiness = "uninitialized";
    this.volume = 0.6;
    this.panicCount = 0;
    this.context = { currentTime: 0 };
    this.gate = null;
    this.fail = false;
  }

  initialize() {
    return new Promise((resolve, reject) => {
      this.gate = {
        resolve: () => {
          this.readiness = "ready";
          resolve();
        },
        reject: () => {
          this.readiness = "failed";
          reject(new Error("audio blocked"));
        },
      };
      if (this.fail) this.gate.reject();
    });
  }

  panic() {
    this.panicCount += 1;
  }

  setVolume(value) {
    this.volume = value;
  }

  scheduleNote() {}
}

function renderer(name, { fail = false, applied = [] } = {}) {
  return {
    mount() {
      if (fail) throw new Error(`${name} broke`);
      return { name };
    },
    applyActive(_root, ids) {
      applied.push([...ids]);
      return ids;
    },
    applySelection() {
      return null;
    },
  };
}

test.before(() => {
  globalThis.document = { createElement };
});

test.after(() => {
  delete globalThis.document;
});

async function mount(bundle = preparationBody(), extra = {}) {
  const clock = scheduling();
  const runtime = await mountReceivedLessonRuntime({
    bundle,
    roots: extra.roots || roots(),
    requestAnimationFrame: clock.requestAnimationFrame,
    cancelAnimationFrame: clock.cancelAnimationFrame,
    setIntervalFn: clock.setIntervalFn,
    clearIntervalFn: clock.clearIntervalFn,
    ReferenceSynth: extra.ReferenceSynth || FakeSynth,
    renderers: extra.renderers || {
      tab: renderer("tab", { applied: extra.applied }),
      notation: renderer("notation"),
    },
    now: extra.now,
    isCurrent: extra.isCurrent,
  });
  return { runtime, clock };
}

test("one transport stays paused, loops, and drives both score views", async () => {
  const applied = [];
  let clockMs = 0;
  const { runtime, clock } = await mount(preparationBody(), {
    applied,
    now: () => clockMs,
  });
  assert.equal(runtime.transport.playing, false);
  assert.equal(runtime.scheduler.enabled, false);
  assert.equal(runtime.transport.playbackRate, 1);
  assert.equal(runtime.transport.loop.enabled, true);
  assert.equal(runtime.transport.loop.targetRepetitions, 2);
  assert.equal(runtime.score.ok, true);

  clock.frame(0);
  assert.deepEqual(applied.at(-1), ["ev-1"]);

  runtime.play();
  assert.equal(runtime.transport.playing, true);
  runtime.pause();
  assert.equal(runtime.transport.playing, false);
  runtime.seek(0.25);
  assert.equal(runtime.transport.positionSeconds(), 0.25);
  runtime.restart();
  assert.equal(runtime.transport.positionSeconds(), 0);
  for (const rate of [0.5, 0.75, 1, 1.5]) {
    runtime.setRate(rate);
    assert.equal(runtime.transport.playbackRate, rate);
  }
  runtime.setLoopEnabled(false);
  assert.equal(runtime.transport.loop.enabled, false);
  runtime.setLoopEnabled(true);
  runtime.setRate(1);
  runtime.play();
  clockMs = 1100;
  const wrapped = runtime.transport.positionSeconds(clockMs);
  assert.ok(wrapped < runtime.transport.loop.endSeconds);
  assert.ok(runtime.transport.repetitionCount >= 1);

  runtime.coordinator.seekTo("ev-2");
  assert.equal(runtime.transport.positionSeconds(), 1);

  const frames = clock.scheduled();
  runtime.dispose();
  clock.frame(2000);
  assert.equal(clock.scheduled(), frames);
  assert.equal(clock.timers.size, 0);
  assert.equal(runtime.transport.playing, false);
  assert.equal(runtime.timeline.ready, false);
});

test("fretboard selection does not invent active events", async () => {
  const { runtime, clock } = await mount();
  clock.frame(0);
  const active = runtime.coordinator.activeEventIds.slice();
  const canvas = runtime.renderer.roots.scrollCanvas;
  canvas.listeners.click({
    target: {
      closest(selector) {
        return selector === ".note" ? { dataset: { eventId: "ev-2" } } : null;
      },
    },
  });
  assert.equal(runtime.coordinator.selectedEventId, "ev-2");
  assert.deepEqual(runtime.coordinator.activeEventIds, active);
  runtime.dispose();
});

test("one score renderer failure leaves the lesson usable", async () => {
  const { runtime } = await mount(preparationBody(), {
    renderers: {
      tab: renderer("tab"),
      notation: renderer("notation", { fail: true }),
    },
  });
  assert.equal(runtime.score.ok, true);
  assert.equal(runtime.coordinator.views.tab.mounted, true);
  assert.equal(runtime.coordinator.views.notation.mounted, false);
  runtime.play();
  assert.equal(runtime.transport.playing, true);
  runtime.dispose();
});

test("a mount failure disposes the partial runtime", async () => {
  const clock = scheduling();
  const bundle = preparationBody();
  bundle.playback.events.reverse();
  await assert.rejects(() => mountReceivedLessonRuntime({
    bundle,
    roots: roots(),
    requestAnimationFrame: clock.requestAnimationFrame,
    cancelAnimationFrame: clock.cancelAnimationFrame,
    setIntervalFn: clock.setIntervalFn,
    clearIntervalFn: clock.clearIntervalFn,
    ReferenceSynth: FakeSynth,
    renderers: { tab: renderer("tab"), notation: renderer("notation") },
  }));
  assert.equal(clock.timers.size, 0);
});

test("a late audio init cannot enable a replacement runtime", async () => {
  const first = await mount();
  const pending = first.runtime.enableSound();
  first.runtime.dispose();
  const second = await mount();
  first.runtime.synth.gate.resolve();
  const result = await pending;
  assert.equal(result.stale, true);
  assert.equal(second.runtime.scheduler.enabled, false);
  assert.equal(first.runtime.scheduler.enabled, false);
  second.runtime.dispose();
});

test("repeated disposal leaves no timers", async () => {
  const created = [];
  for (let index = 0; index < 3; index += 1) {
    created.push(await mount());
    created.at(-1).runtime.dispose();
    created.at(-1).runtime.dispose();
  }
  assert.equal(created.every((item) => item.clock.timers.size === 0), true);
});
