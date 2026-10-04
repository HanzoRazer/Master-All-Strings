import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { mountLessonPractice } from "../lesson_practice.js";
import {
  choiceBody,
  preparationBody,
  previewBody,
} from "./lesson_practice_fixture.js";
import {
  acknowledgementDocument,
  beginDocument,
  evaluatedDocument,
  interruptedDocument,
} from "./received_attempt_fixture.js";

const pageSource = readFileSync(
  fileURLToPath(new URL("../lesson-practice.html", import.meta.url)),
  "utf8",
);
const practiceSource = readFileSync(
  fileURLToPath(new URL("../lesson_practice.js", import.meta.url)),
  "utf8",
);
const ART = previewBody().assignment_artifact_digest;
const BEH = previewBody().assignment_behavior_digest;

function el(tag, document) {
  const classes = new Set();
  return {
    tagName: tag,
    ownerDocument: document,
    id: "",
    children: [],
    hidden: false,
    disabled: false,
    checked: false,
    value: "0",
    type: "",
    className: "",
    dataset: {},
    attributes: {},
    listeners: {},
    _text: "",
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      toggle: (name, force) => {
        const on = force === undefined ? !classes.has(name) : Boolean(force);
        if (on) classes.add(name);
        else classes.delete(name);
        return on;
      },
      contains: (name) => classes.has(name),
    },
    get textContent() {
      if (this.children.length > 0) return this.children.map((child) => child.textContent).join("");
      return this._text;
    },
    set textContent(value) {
      this._text = value == null ? "" : String(value);
      this.children = [];
    },
    set innerHTML(value) {
      document.innerHtmlUsed = true;
      this._text = String(value);
    },
    append(...nodes) { this.children.push(...nodes); },
    replaceChildren(...nodes) { this.children = [...nodes]; },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
      if (name === "data-rate") this.dataset.rate = String(value);
    },
    getAttribute(name) {
      return Object.hasOwn(this.attributes, name) ? this.attributes[name] : null;
    },
    addEventListener(type, handler) {
      (this.listeners[type] ||= []).push(handler);
    },
    click() {
      if (this.disabled) return;
      for (const handler of this.listeners.click || []) handler();
    },
    change() {
      for (const handler of this.listeners.change || []) handler();
    },
    input() {
      for (const handler of this.listeners.input || []) handler();
    },
  };
}

function walk(node, found = []) {
  found.push(node);
  for (const child of node.children || []) walk(child, found);
  return found;
}

function buildRoot() {
  const document = {
    innerHtmlUsed: false,
    activeElement: null,
    createElement: (tag) => el(tag, document),
  };
  const root = document.createElement("main");
  root.ownerDocument = document;
  const add = (tag, id, parent = root) => {
    const node = document.createElement(tag);
    node.id = id;
    parent.append(node);
    return node;
  };
  for (const id of [
    "status", "lesson-title", "lesson-objective", "teacher-note", "instrument-name",
    "identity-delivery", "identity-assignment", "identity-content", "warning-list",
    "unsupported-list", "unresolved-list", "score-notice", "clock", "repetition-count",
    "loop-bounds", "loop-target", "audio-status", "laneLabels", "scrollViewport",
    "scrollCanvas", "playLine", "gutterNotes", "unplayableGutter", "neckMap",
    "instrumentTitle", "tabView", "notationView", "attempt-feedback",
    "attempt-evidence-body", "attempt-status", "attempt-count", "midi-status",
    "attempt-policy-note",
  ]) {
    add(id === "warning-list" || id.endsWith("-list") ? "ul" : "div", id);
  }
  add("details", "attempt-evidence");
  add("button", "refresh-lesson");
  add("button", "btn-enable-midi");
  add("select", "midi-input").disabled = true;
  for (const id of ["btn-start-attempt", "btn-finish-attempt"]) {
    add("button", id).disabled = true;
  }
  add("button", "btn-cancel-attempt").hidden = true;
  add("button", "btn-retry-finish").hidden = true;
  add("a", "back-inbox").setAttribute("href", "lesson-inbox.html");
  for (const id of ["btn-play", "btn-pause", "btn-restart"]) {
    const button = add("button", id);
    button.disabled = true;
  }
  const seek = add("input", "seek");
  seek.disabled = true;
  for (const rate of ["0.5", "0.75", "1", "1.5"]) {
    const button = add("button", `rate-${rate}`);
    button.setAttribute("data-rate", rate);
    button.disabled = true;
  }
  for (const id of ["loop-enabled", "sound-enabled"]) {
    const box = add("input", id);
    box.disabled = true;
    box.checked = false;
  }
  const volume = add("input", "master-volume");
  volume.disabled = true;
  volume.value = "0.6";
  root.querySelector = (selector) => walk(root).find((node) => node.id === selector.slice(1)) || null;
  root.querySelectorAll = (selector) => walk(root).filter((node) => (
    selector === "[data-rate]" && node.getAttribute("data-rate")
  ));
  return root;
}

function ok(body, status = 200) {
  return { ok: true, status, error: null, body };
}

function failed(status, error) {
  return { ok: false, status, error, body: null };
}

function clientFor(handlers) {
  const calls = [];
  return {
    calls,
    async preview(id) {
      calls.push({ method: "preview", id });
      return handlers.preview(id);
    },
    async getChoice(id) {
      calls.push({ method: "getChoice", id });
      return handlers.getChoice(id);
    },
    async prepare(id, artifact, behavior) {
      calls.push({ method: "prepare", id, artifact, behavior });
      return handlers.prepare(id, artifact, behavior);
    },
    async choose() {
      calls.push({ method: "choose" });
      throw new Error("practice page must not POST a choice");
    },
  };
}

function fakeRuntime(spec, record) {
  const runtime = {
    spec,
    transport: {
      durationSeconds: 2,
      playbackRate: 1,
      positionSeconds: () => record.position ?? 0,
    },
    coordinator: {
      views: {
        tab: { mounted: true },
        notation: { mounted: spec.notationMounted !== false },
      },
      applyGuidance(projection) {
        record.guidance = projection;
        return projection;
      },
    },
    disposed: false,
    dispose() {
      this.disposed = true;
      record.disposed += 1;
    },
    play() {
      this.played = true;
      spec.onPlayback("playing");
    },
    pause() { spec.onPlayback("paused"); },
    restart() { spec.onPlayback("paused"); },
    seek(seconds) { this.sought = seconds; },
    setRate(rate) { this.rate = rate; },
    setLoopEnabled(enabled) { this.loopEnabled = enabled; },
    setVolume(value) { this.volume = value; },
    silence() { this.silenced = (this.silenced || 0) + 1; },
    setInteractionLock(locked) { this.locked = locked; },
    enableSound() {
      this.soundCalls = (this.soundCalls || 0) + 1;
      return record.sound;
    },
    disableSound() { this.soundOff = true; },
  };
  record.runtimes.push(runtime);
  return runtime;
}

function midiStub(devices = [{ id: "key-1", name: "Injected keyboard" }]) {
  const midi = {
    listener: null,
    devicesList: devices,
    permission: "ready",
    async requestPermission() {
      return this.permission;
    },
    devices() {
      return this.devicesList;
    },
    connect(id, listener) {
      this.connected = id;
      this.listener = listener;
      return this.devicesList.some((device) => device.id === id);
    },
    disconnect() {
      this.listener = null;
      this.connected = null;
    },
    emit(payload, captureTimeNs) {
      this.listener?.({
        device_id: this.connected,
        raw_payload: payload,
        capture_time_ns: captureTimeNs,
      });
    },
  };
  return midi;
}

function attemptCalls() {
  const calls = [];
  return {
    calls,
    async begin(body) {
      calls.push({ op: "begin", body });
      return this.next.begin(body);
    },
    async append(body) {
      calls.push({ op: "append", body });
      return this.next.append(body);
    },
    async finish(body) {
      calls.push({ op: "finish", body });
      return this.next.finish(body);
    },
    async cancel(body) {
      calls.push({ op: "cancel", body });
      return this.next.cancel(body);
    },
    next: {},
  };
}

async function mount(handlers, {
  search = "?delivery_id=delivery-001",
  view,
  notationMounted = true,
  attemptClient,
  midi,
  nowNs,
  runtimeFactory,
  record = {
    disposed: 0,
    runtimes: [],
    sound: Promise.resolve({ ok: true }),
    position: 0.25,
  },
} = {}) {
  const root = buildRoot();
  const client = clientFor(handlers);
  const ui = mountLessonPractice(root, {
    client,
    location: { search },
    view,
    attemptClient,
    midi,
    nowNs,
    runtimeFactory: runtimeFactory || ((spec) => fakeRuntime({ ...spec, notationMounted }, record)),
  });
  await ui.idle();
  return { root, client, ui, record, q: (id) => root.querySelector(`#${id}`) };
}

test("the practice page is a separate shell", () => {
  assert.match(pageSource, /lesson_practice\.js/);
  assert.match(pageSource, /lesson-practice\.css/);
  assert.match(pageSource, /score-view\.css/);
  assert.match(pageSource, /disappear when the server process ends/);
  assert.match(pageSource, /href="lesson-inbox.html"/);
  assert.match(pageSource, /Attempts use one pass at normal speed/);
  assert.doesNotMatch(pageSource, /styles\.css|app\.js|index\.html/);
  assert.match(practiceSource, /fakeMode:\s*false/);
  assert.doesNotMatch(practiceSource, /fakeMidi/);
  assert.doesNotMatch(practiceSource, /renderResultsPanel|guided-sessions|\/api\/performance\//);
});

test("a bad URL fails before any request", async () => {
  for (const search of ["", "?delivery_id=", "?delivery_id=a&extra=1", "?delivery_id=a&delivery_id=b"]) {
    const page = await mount({
      preview() { throw new Error("preview"); },
      getChoice() { throw new Error("choice"); },
      prepare() { throw new Error("prepare"); },
    }, { search });
    assert.equal(page.client.calls.length, 0);
    assert.equal(page.q("btn-play").disabled, true);
    assert.match(page.q("status").textContent, /one delivery id/);
  }
});

test("load order is preview, choice GET, then preparation with preview pins", async () => {
  const id = "a/b c";
  const page = await mount({
    preview: () => ok(previewBody(id)),
    getChoice: () => ok(choiceBody(id)),
    prepare: () => ok(preparationBody(id)),
  }, { search: `?${new URLSearchParams({ delivery_id: id })}` });
  assert.deepEqual(page.client.calls.map((call) => call.method), ["preview", "getChoice", "prepare"]);
  assert.equal(page.client.calls[0].id, id);
  assert.equal(page.client.calls[2].artifact, ART);
  assert.equal(page.client.calls[2].behavior, BEH);
  assert.equal(page.client.calls.some((call) => call.method === "choose"), false);
  assert.equal(page.q("btn-play").disabled, false);
  assert.equal(page.q("sound-enabled").checked, false);
  assert.match(page.q("status").textContent, /Paused/);
  assert.equal(page.q("lesson-title").textContent, "Blues Turnaround");
  assert.equal(page.q("identity-delivery").textContent, id);
  assert.match(page.q("warning-list").textContent, /Watch the third/);
  assert.match(page.q("unsupported-list").textContent, /bend/);
  assert.match(page.q("loop-target").textContent, /2/);
  assert.equal(page.record.runtimes[0].played, undefined);

  page.q("btn-play").click();
  assert.equal(page.record.runtimes[0].played, true);
  assert.match(page.q("status").textContent, /Playing/);
  page.q("btn-pause").click();
  assert.match(page.q("status").textContent, /Paused/);
  page.record.runtimes[0].spec.onPlayback("ended");
  assert.match(page.q("status").textContent, /Playback ended/);
  assert.equal(page.q("status").textContent.includes("passed"), false);
  assert.equal(page.q("status").textContent.includes("completed"), false);

  page.q("seek").value = "250";
  page.q("seek").input();
  assert.equal(page.record.runtimes[0].sought, 0.5);
  page.root.querySelectorAll("[data-rate]").find((button) => button.getAttribute("data-rate") === "0.75").click();
  assert.equal(page.record.runtimes[0].rate, 0.75);
  page.q("loop-enabled").checked = false;
  page.q("loop-enabled").change();
  assert.equal(page.record.runtimes[0].loopEnabled, false);
  assert.equal(page.root.ownerDocument.innerHtmlUsed, false);
});

test("preview and choice failures never prepare", async () => {
  const previewFailed = await mount({
    preview: () => failed(404, "unknown_delivery_id"),
    getChoice() { throw new Error("choice"); },
    prepare() { throw new Error("prepare"); },
  });
  assert.deepEqual(previewFailed.client.calls.map((call) => call.method), ["preview"]);
  assert.match(previewFailed.q("status").textContent, /404, unknown_delivery_id/);
  assert.equal(previewFailed.q("btn-play").disabled, true);

  const unchosen = await mount({
    preview: () => ok(previewBody()),
    getChoice: () => failed(404, "unknown_practice_choice"),
    prepare() { throw new Error("prepare"); },
  });
  assert.deepEqual(unchosen.client.calls.map((call) => call.method), ["preview", "getChoice"]);
  assert.match(unchosen.q("status").textContent, /404, unknown_practice_choice/);

  const malformed = preparationBody();
  malformed.extra = true;
  const invalid = await mount({
    preview: () => ok(previewBody()),
    getChoice: () => ok(choiceBody()),
    prepare: () => ok(malformed),
  });
  assert.match(invalid.q("status").textContent, /invalid/);
  assert.equal(invalid.q("btn-play").disabled, true);
  assert.equal(invalid.record.runtimes.length, 0);
});

test("server text is rendered as text and a score view can fail alone", async () => {
  const preview = previewBody();
  preview.title = "<img src=x onerror=alert(1)>";
  const page = await mount({
    preview: () => ok(preview),
    getChoice: () => ok(choiceBody()),
    prepare: () => ok(preparationBody()),
  }, { notationMounted: false });
  assert.equal(page.q("lesson-title").textContent, preview.title);
  assert.equal(page.root.ownerDocument.innerHtmlUsed, false);
  assert.match(page.q("score-notice").textContent, /notation/);
  assert.equal(page.q("btn-play").disabled, false);
});

test("refresh drops the old runtime and a late result cannot replace it", async () => {
  const gates = [];
  let hold = false;
  const page = await mount({
    preview: () => {
      if (!hold) return ok(previewBody());
      return new Promise((resolve) => gates.push(resolve));
    },
    getChoice: () => ok(choiceBody()),
    prepare: () => ok(preparationBody()),
  });
  assert.equal(page.client.calls.filter((call) => call.method === "prepare").length, 1);
  hold = true;
  const firstRefresh = page.ui.refresh();
  const secondRefresh = page.ui.refresh();
  assert.equal(page.record.runtimes[0].disposed, true);
  assert.equal(gates.length, 2);
  gates[0](ok(previewBody()));
  gates[1](ok(previewBody()));
  await firstRefresh;
  await secondRefresh;
  assert.equal(page.client.calls.filter((call) => call.method === "prepare").length, 2);
  assert.match(page.q("status").textContent, /Paused/);
  assert.equal(page.q("sound-enabled").checked, false);

  let releaseSound;
  page.record.sound = new Promise((resolve) => {
    releaseSound = resolve;
  });
  const current = page.record.runtimes.at(-1);
  page.q("sound-enabled").checked = true;
  page.q("sound-enabled").change();
  assert.equal(current.soundCalls, 1);
  const duringSound = page.ui.refresh();
  assert.equal(current.disposed, true);
  assert.equal(page.q("sound-enabled").checked, false);
  releaseSound({ ok: true });
  await page.record.sound;
  gates.at(-1)(ok(previewBody()));
  await duringSound;
  assert.equal(page.q("sound-enabled").checked, false);
  assert.equal(page.q("audio-status").textContent.includes("Sound ready"), false);
  assert.equal(page.record.runtimes.at(-1).soundCalls || 0, 0);
});

test("restoration reloads and stays paused with sound off", async () => {
  const listeners = {};
  const view = {
    addEventListener(type, handler) {
      (listeners[type] ||= []).push(handler);
    },
    dispatch(type, event) {
      for (const handler of listeners[type] || []) handler(event);
    },
  };
  const page = await mount({
    preview: () => ok(previewBody()),
    getChoice: () => ok(choiceBody()),
    prepare: () => ok(preparationBody()),
  }, { view });
  assert.equal(page.client.calls.length, 3);
  view.dispatch("pagehide", {});
  assert.equal(page.record.runtimes[0].disposed, true);
  assert.equal(page.q("btn-play").disabled, true);
  view.dispatch("pageshow", { persisted: true });
  await page.ui.idle();
  assert.equal(page.client.calls.filter((call) => call.method === "preview").length, 2);
  assert.match(page.q("status").textContent, /Paused/);
  assert.equal(page.q("sound-enabled").checked, false);
  assert.equal(page.record.runtimes.at(-1).played, undefined);
});

test("a network failure is shown and not retried", async () => {
  const page = await mount({
    preview: () => failed(0, null),
    getChoice() { throw new Error("choice"); },
    prepare() { throw new Error("prepare"); },
  });
  assert.match(page.q("status").textContent, /unavailable, unavailable/);
  assert.equal(page.client.calls.length, 1);
});

test("an explicit attempt mounts the server snapshot and shows text feedback", async () => {
  const attempt = beginDocument({ attemptId: "<attempt>", revisionId: "rev-from-server" });
  const midi = midiStub();
  const transport = attemptCalls();
  const record = {
    disposed: 0,
    runtimes: [],
    sound: Promise.resolve({ ok: true }),
    position: 0.25,
  };
  let holdMount = null;
  transport.next = {
    begin: () => ok(attempt, 201),
    append: (body) => ok(acknowledgementDocument(attempt, body.sequenceNumber + 1)),
    finish: () => ok(evaluatedDocument(attempt)),
    cancel: () => ok(interruptedDocument(attempt)),
  };
  const page = await mount({
    preview: () => ok(previewBody()),
    getChoice: () => ok(choiceBody()),
    prepare: () => ok(preparationBody()),
  }, {
    midi,
    attemptClient: transport,
    nowNs: () => 4_000_000,
    record,
    runtimeFactory: (spec) => {
      const revision = spec.bundle.score.canonical_revision.revision_id;
      if (revision === "rev-from-server") {
        return new Promise((resolve) => {
          holdMount = () => resolve(fakeRuntime(spec, record));
        });
      }
      return fakeRuntime(spec, record);
    },
  });
  assert.equal(page.q("btn-play").disabled, false);
  assert.equal(page.q("btn-start-attempt").disabled, true);
  page.q("btn-play").click();
  assert.equal(page.record.runtimes[0].played, true);

  page.q("btn-enable-midi").click();
  await page.ui.idle();
  assert.match(page.q("midi-status").textContent, /ready/);
  page.q("btn-start-attempt").click();
  for (let step = 0; step < 8 && typeof holdMount !== "function"; step += 1) {
    await Promise.resolve();
  }
  midi.emit([0x90, 64, 80], 50);
  assert.equal(transport.calls.some((call) => call.op === "append"), false);
  assert.equal(midi.connected, null);
  holdMount();
  await page.ui.idle();
  const mounted = page.record.runtimes.at(-1);
  assert.equal(mounted.spec.bundle.score.canonical_revision.revision_id, "rev-from-server");
  assert.equal(mounted.locked, true);
  assert.deepEqual(mounted.calls?.includes?.("play") || mounted.played, true);
  assert.equal(page.q("btn-pause").hidden, true);
  assert.equal(page.q("btn-cancel-attempt").hidden, false);
  assert.equal(page.q("seek").disabled, true);
  assert.equal(page.q("refresh-lesson").disabled, true);
  assert.equal(page.q("sound-enabled").disabled, false);
  page.q("seek").value = "500";
  page.q("seek").input();
  assert.equal(mounted.sought, undefined);
  page.root.querySelectorAll("[data-rate]").find((button) => button.getAttribute("data-rate") === "0.75").click();
  assert.equal(mounted.rate, 1);

  midi.emit([0x90, 64, 80], 60);
  midi.emit([0x90, 64, 0], 70);
  midi.emit([0x80, 67, 0], 80);
  for (
    let step = 0;
    step < 12 && transport.calls.filter((call) => call.op === "append").length < 3;
    step += 1
  ) {
    await Promise.resolve();
  }
  assert.deepEqual(
    transport.calls.filter((call) => call.op === "append").map((call) => call.body.sequenceNumber),
    [0, 1, 2],
  );
  page.q("btn-finish-attempt").click();
  await page.ui.idle();
  const feedback = page.q("attempt-feedback").textContent;
  assert.match(feedback, /Matched: 1/);
  assert.match(feedback, /Missing: 2/);
  assert.match(feedback, /Extra: 1/);
  assert.match(feedback, /<attempt>/);
  assert.match(feedback, /<img src=x onerror=alert\(1\)>/);
  assert.match(feedback, /No immediate repetition is required under this attempt policy/);
  assert.match(feedback, /UNVERIFIED_PHYSICAL_MIDI_INPUT/);
  assert.equal(feedback.toLowerCase().includes("lesson complete"), false);
  assert.equal(page.root.ownerDocument.innerHtmlUsed, false);
  assert.equal(page.record.guidance.canonical_revision_id, "rev-from-server");
  assert.equal(mounted.rate, 1);
  assert.equal(page.q("btn-play").disabled, false);
  assert.equal(page.q("loop-enabled").checked, true);
  assert.equal(
    transport.calls.every((call) => ["begin", "append", "finish", "cancel"].includes(call.op)),
    true,
  );
  assert.equal(transport.calls.filter((call) => call.op === "finish").length, 1);

  const next = beginDocument({ attemptId: "attempt-2", revisionId: "rev-from-server" });
  transport.next.begin = () => ok(next, 201);
  transport.next.append = (body) => ok(acknowledgementDocument(next, body.sequenceNumber + 1));
  transport.next.finish = () => ok(evaluatedDocument(next));
  const previousHold = holdMount;
  page.q("btn-start-attempt").click();
  assert.equal(page.q("attempt-feedback").textContent, "");
  for (let step = 0; step < 8 && holdMount === previousHold; step += 1) {
    await Promise.resolve();
  }
  holdMount();
  await page.ui.idle();
  assert.equal(transport.calls.filter((call) => call.op === "begin").at(-1).body.deviceId, "Injected keyboard");
});

test("MIDI denial leaves reference practice usable", async () => {
  const midi = midiStub([]);
  midi.permission = "permission_denied";
  const page = await mount({
    preview: () => ok(previewBody()),
    getChoice: () => ok(choiceBody()),
    prepare: () => ok(preparationBody()),
  }, { midi });
  page.q("btn-enable-midi").click();
  await page.ui.idle();
  assert.match(page.q("midi-status").textContent, /denied/);
  assert.match(page.q("midi-status").textContent, /Reference practice/);
  assert.equal(page.q("btn-play").disabled, false);
  assert.equal(page.q("btn-start-attempt").disabled, true);
  page.q("btn-play").click();
  assert.equal(page.record.runtimes[0].played, true);
});

test("leaving the page abandons an attempt and restoration does not resume capture", async () => {
  const listeners = {};
  const view = {
    addEventListener(type, handler) {
      (listeners[type] ||= []).push(handler);
    },
    dispatch(type, event) {
      for (const handler of listeners[type] || []) handler(event);
    },
  };
  const attempt = beginDocument();
  let releaseBegin;
  const midi = midiStub();
  const transport = attemptCalls();
  transport.next = {
    begin: () => new Promise((resolve) => {
      releaseBegin = resolve;
    }),
    append: () => ok(acknowledgementDocument(attempt, 1)),
    finish: () => ok(evaluatedDocument(attempt)),
    cancel: (body) => {
      transport.cancelBody = body;
      return ok(interruptedDocument(attempt));
    },
  };
  const page = await mount({
    preview: () => ok(previewBody()),
    getChoice: () => ok(choiceBody()),
    prepare: () => ok(preparationBody()),
  }, { view, midi, attemptClient: transport });
  page.q("btn-enable-midi").click();
  await page.ui.idle();
  page.q("btn-start-attempt").click();
  await Promise.resolve();
  assert.equal(page.q("attempt-status").textContent, "Starting the attempt.");
  view.dispatch("pagehide", {});
  releaseBegin(ok(attempt, 201));
  await page.ui.idle();
  assert.equal(transport.calls.some((call) => call.op === "cancel"), true);
  assert.equal(transport.cancelBody.keepalive, true);
  assert.equal(page.record.runtimes.some((runtime) => runtime.played && runtime.spec.bundle.score.canonical_revision.revision_id === "rev-attempt"), false);
  view.dispatch("pageshow", { persisted: true });
  await page.ui.idle();
  assert.match(page.q("status").textContent, /Paused/);
  assert.equal(page.q("sound-enabled").checked, false);
  assert.match(page.q("attempt-status").textContent, /No attempt/);
  assert.equal(page.record.runtimes.at(-1).played, undefined);
  assert.equal(midi.connected, null);
});
