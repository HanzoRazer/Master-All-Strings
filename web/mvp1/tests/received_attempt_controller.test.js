import assert from "node:assert/strict";
import test from "node:test";

import { createReceivedAttemptController } from "../received_attempt_controller.js";
import { choiceBody, previewBody } from "./lesson_practice_fixture.js";
import {
  acknowledgementDocument,
  beginDocument,
  evaluatedDocument,
  interruptedDocument,
} from "./received_attempt_fixture.js";

function deferred() {
  /** @type {(value: unknown) => void} */
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function ok(body, status = 200) {
  return { ok: true, status, error: null, body };
}

function harness(options = {}) {
  const begin = options.begin ?? beginDocument();
  const calls = [];
  let now = 1_000_000;
  let position = 0;
  let current = true;
  const shown = [];
  const locks = [];
  const playback = [];
  const runtime = {
    calls: [],
    play() { this.calls.push("play"); },
    pause() { this.calls.push("pause"); },
    restart() { this.calls.push("restart"); },
    setRate(rate) { this.calls.push(["rate", rate]); },
    setLoopEnabled(enabled) { this.calls.push(["loop", enabled]); },
    setInteractionLock(locked) { this.calls.push(["lock", locked]); },
    dispose() { this.calls.push("dispose"); },
  };
  const midi = {
    list: options.devices ?? [{ id: "key-1", name: "Keyboard" }],
    listener: null,
    disconnectListener: null,
    connected: null,
    connectResult: options.connectResult ?? true,
    async requestPermission() {
      return options.permission ?? "ready";
    },
    devices() {
      return this.list.map((item) => ({ ...item }));
    },
    connect(id, listener, disconnectListener) {
      this.connected = id;
      this.listener = listener;
      this.disconnectListener = disconnectListener;
      calls.push({ op: "midi-connect", id });
      if (options.onConnect) options.onConnect(midi);
      return this.connectResult;
    },
    disconnect() {
      calls.push({ op: "midi-disconnect" });
      this.keptListener = this.listener;
      this.listener = null;
      this.connected = null;
    },
    emit(payload, captureTimeNs = now, deviceId = this.connected) {
      const listener = this.listener || this.keptListener;
      listener?.({
        device_id: deviceId ?? "key-1",
        raw_payload: payload,
        capture_time_ns: captureTimeNs,
      });
    },
  };
  const gates = { append: [] };
  const client = {
    async begin(body) {
      calls.push({ op: "begin", body });
      if (options.beginResult) return options.beginResult(body);
      return ok(begin, 201);
    },
    async append(body) {
      calls.push({ op: "append", body });
      if (options.appendResult) return options.appendResult(body, calls);
      const gate = gates.append.shift();
      if (gate) return gate.promise;
      return ok(acknowledgementDocument(begin, body.sequenceNumber + 1));
    },
    async finish(body) {
      calls.push({ op: "finish", body });
      if (options.finishResult) return options.finishResult(body);
      return ok(evaluatedDocument(begin));
    },
    async cancel(body) {
      calls.push({ op: "cancel", body });
      if (options.cancelResult) return options.cancelResult(body);
      return ok(interruptedDocument(begin));
    },
  };
  const controller = createReceivedAttemptController({
    client,
    midi,
    nowNs: () => now,
    isCurrent: () => current,
    getLesson: () => options.lesson ?? { preview: previewBody(), choice: choiceBody() },
    positionSeconds: () => position,
    lockInteractions(locked) { locks.push(locked); },
    stopPlayback() { playback.push("stop"); },
    pausePlayback() { playback.push("pause"); },
    replaceRuntime: options.replaceRuntime ?? (async () => runtime),
    clearFeedback() { shown.push({ kind: "clear" }); },
    showEvaluated(body) { shown.push({ kind: "evaluated", body }); },
    showInterrupted(body) { shown.push({ kind: "interrupted", body }); },
  });
  return {
    begin,
    controller,
    midi,
    calls,
    shown,
    locks,
    playback,
    runtime,
    gates,
    setNow(value) { now = value; },
    setPosition(value) { position = value; },
    setCurrent(value) { current = value; },
  };
}

function ops(calls, name) {
  return calls.filter((call) => call.op === name);
}

async function capture(env) {
  await env.controller.enableMidi();
  return env.controller.start();
}

test("start replaces the runtime before any message is captured", async () => {
  let releaseMount;
  const mounted = new Promise((resolve) => {
    releaseMount = resolve;
  });
  const env = harness({
    replaceRuntime: () => mounted,
  });
  const pending = capture(env);
  await Promise.resolve();
  env.midi.emit([0x90, 64, 80], 10);
  assert.equal(ops(env.calls, "append").length, 0);
  assert.equal(ops(env.calls, "midi-connect").length, 0);
  const runtime = env.runtime;
  releaseMount(runtime);
  const started = await pending;
  assert.equal(started.state, "CAPTURING");
  assert.deepEqual(runtime.calls, [
    ["lock", true],
    ["rate", 1],
    ["loop", false],
    "restart",
    "play",
  ]);
  assert.equal(env.calls.find((call) => call.op === "begin").body.deviceId, "Keyboard");
  assert.equal(env.runtime.calls.includes("play"), true);
  env.midi.emit([0xb0, 7, 100], 11);
  env.midi.emit([0x90, 64, 80], 12);
  await Promise.resolve();
  const appended = ops(env.calls, "append");
  assert.equal(appended.length, 1);
  assert.equal(appended[0].body.sequenceNumber, 0);
  assert.deepEqual(appended[0].body.rawPayload, [0x90, 64, 80]);
});

test("a different canonical revision is the attempt snapshot", async () => {
  const begin = beginDocument({ revisionId: "rev-from-server", attemptId: "attempt-new" });
  let mounted = null;
  const env = harness({
    begin,
    replaceRuntime: async (bundle) => {
      mounted = bundle;
      return env.runtime;
    },
  });
  await capture(env);
  assert.equal(mounted.score.canonical_revision.revision_id, "rev-from-server");
  env.midi.emit([0x90, 64, 0], 20);
  env.midi.emit([0x80, 67, 40], 21);
  await env.controller.finish();
  assert.equal(env.shown.some((item) => item.kind === "evaluated"), true);
  assert.equal(ops(env.calls, "finish").length, 1);
  assert.equal(ops(env.calls, "append").length, 2);
  assert.equal(ops(env.calls, "append")[0].body.sequenceNumber, 0);
  assert.equal(ops(env.calls, "append")[1].body.sequenceNumber, 1);
});

test("slow acknowledgements keep the original intake time and position", async () => {
  const env = harness();
  await capture(env);
  const first = deferred();
  const second = deferred();
  env.gates.append.push(first, second);
  env.setPosition(0.2);
  env.setNow(100);
  const payload = [0x90, 64, 80];
  env.midi.emit(payload, 100);
  payload[1] = 1;
  env.setPosition(0.8);
  env.setNow(400);
  env.midi.emit([0x90, 67, 80], 250);
  assert.equal(ops(env.calls, "append").length, 1);
  first.resolve(ok(acknowledgementDocument(env.begin, 1)));
  await Promise.resolve();
  await Promise.resolve();
  second.resolve(ok(acknowledgementDocument(env.begin, 2)));
  await env.controller.finish();
  const appended = ops(env.calls, "append").map((call) => call.body);
  assert.deepEqual(appended.map((body) => body.sequenceNumber), [0, 1]);
  assert.deepEqual(appended.map((body) => body.captureTimeNs), [100, 250]);
  assert.deepEqual(appended.map((body) => body.practicePositionSeconds), [0.2, 0.8]);
  assert.deepEqual(appended[0].rawPayload, [0x90, 64, 80]);
  assert.equal(ops(env.calls, "finish")[0].body.captureTimeNs >= 250, true);
});

test("finish drains the queue and natural end does not finish twice", async () => {
  const env = harness();
  await capture(env);
  const gate = deferred();
  env.gates.append.push(gate);
  env.midi.emit([0x90, 64, 80], 30);
  env.midi.emit([0x90, 67, 70], 40);
  const finishing = env.controller.finish();
  const again = env.controller.noteNaturalEnd();
  assert.equal(ops(env.calls, "finish").length, 0);
  gate.resolve(ok(acknowledgementDocument(env.begin, 1)));
  await finishing;
  await again;
  assert.equal(ops(env.calls, "finish").length, 1);
  assert.equal(ops(env.calls, "append").length, 2);
  assert.equal(env.calls.findIndex((call) => call.op === "finish") >
    env.calls.findIndex((call) => call.op === "append"), true);
  assert.equal(env.controller.snapshot().state, "EVALUATED");
  assert.equal(env.shown.filter((item) => item.kind === "evaluated").length, 1);
});

test("a finish timestamp is never earlier than the last captured timestamp", async () => {
  const env = harness();
  env.setNow(100);
  await capture(env);
  env.midi.emit([0x90, 64, 80], 500);
  await Promise.resolve();
  env.setNow(40);
  await env.controller.finish();
  assert.equal(ops(env.calls, "finish")[0].body.captureTimeNs, 500);
});

test("append failure, a bad count, and overflow cancel without evaluation", async () => {
  const failed = harness({
    appendResult: () => ({ ok: false, status: 409, error: "sequence_conflict", body: null }),
  });
  await capture(failed);
  failed.midi.emit([0x90, 64, 80], 5);
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(failed.controller.snapshot().state, "INTERRUPTED");
  assert.equal(ops(failed.calls, "finish").length, 0);
  assert.equal(failed.shown.some((item) => item.kind === "evaluated"), false);
  assert.equal(failed.shown.some((item) => item.kind === "interrupted"), true);

  const counted = harness({
    appendResult: (body) => ok(acknowledgementDocument(beginDocument(), body.sequenceNumber + 2)),
  });
  await capture(counted);
  counted.midi.emit([0x90, 64, 80], 6);
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(ops(counted.calls, "finish").length, 0);
  assert.equal(counted.controller.snapshot().state, "INTERRUPTED");

  const overflow = harness();
  await capture(overflow);
  const held = deferred();
  overflow.gates.append.push(held);
  for (let index = 0; index < 257; index += 1) {
    overflow.midi.emit([0x90, 60 + (index % 20), 40], 1000 + index);
  }
  assert.equal(ops(overflow.calls, "cancel").length, 1);
  assert.equal(ops(overflow.calls, "append").length, 1);
  held.resolve(ok(acknowledgementDocument(overflow.begin, 1)));
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(ops(overflow.calls, "finish").length, 0);
  assert.equal(overflow.shown.some((item) => item.kind === "evaluated"), false);
});

test("device loss and a failed mount cancel the open attempt", async () => {
  const lost = harness();
  await capture(lost);
  lost.midi.disconnectListener("key-1");
  await Promise.resolve();
  assert.equal(lost.controller.snapshot().state, "INTERRUPTED");
  assert.equal(ops(lost.calls, "finish").length, 0);

  const unmounted = harness({
    replaceRuntime: async () => null,
  });
  await capture(unmounted);
  assert.equal(unmounted.runtime.calls.includes("play"), false);
  assert.equal(ops(unmounted.calls, "cancel").length, 1);
  assert.equal(unmounted.controller.snapshot().state, "INTERRUPTED");

  const disconnected = harness({ connectResult: false });
  await capture(disconnected);
  assert.equal(disconnected.runtime.calls.includes("play"), false);
  await Promise.resolve();
  assert.equal(ops(disconnected.calls, "cancel").length, 1);
});

test("a late begin cannot start a replaced page", async () => {
  const gate = deferred();
  const env = harness({ beginResult: () => gate.promise });
  const pending = capture(env);
  for (let step = 0; step < 8 && env.controller.snapshot().state !== "STARTING"; step += 1) {
    await Promise.resolve();
  }
  assert.equal(env.controller.snapshot().state, "STARTING");
  env.controller.abandon();
  gate.resolve(ok(env.begin, 201));
  await pending;
  assert.equal(env.controller.snapshot().state, "IDLE");
  assert.equal(ops(env.calls, "midi-connect").length, 0);
  assert.equal(ops(env.calls, "cancel").length, 1);
  assert.equal(ops(env.calls, "cancel")[0].body.keepalive, true);
  assert.equal(env.runtime.calls.includes("play"), false);
  assert.equal(env.shown.some((item) => item.kind === "evaluated"), false);
});

test("a lost begin is not repeated and an invalid begin is cancelled", async () => {
  const lost = harness({
    beginResult: () => ({ ok: false, status: 0, error: null, body: null }),
  });
  await capture(lost);
  assert.equal(lost.controller.snapshot().state, "UNCONFIRMED");
  assert.equal(lost.controller.snapshot().unconfirmedKind, "begin");
  assert.equal(ops(lost.calls, "begin").length, 1);
  await lost.controller.start();
  assert.equal(ops(lost.calls, "begin").length, 2);

  const invalid = harness({
    beginResult: () => ok({ ...beginDocument(), extra: true, attempt_id: "attempt-bad" }, 201),
  });
  await capture(invalid);
  assert.equal(ops(invalid.calls, "cancel")[0].body.attemptId, "attempt-bad");
  assert.equal(invalid.controller.snapshot().state, "IDLE");
  assert.equal(invalid.shown.some((item) => item.kind === "interrupted"), false);

  const unconfirmedCancel = harness({
    beginResult: () => ok({ attempt_id: "attempt-late" }, 201),
    cancelResult: () => ({ ok: false, status: 0, error: null, body: null }),
  });
  await capture(unconfirmedCancel);
  assert.equal(unconfirmedCancel.controller.snapshot().state, "UNCONFIRMED");
  assert.equal(unconfirmedCancel.controller.snapshot().unconfirmedKind, "cancel");
});

test("retry finish keeps the attempt and sends no new MIDI", async () => {
  let finishCalls = 0;
  const env = harness({
    finishResult: () => {
      finishCalls += 1;
      if (finishCalls === 1) return { ok: false, status: 0, error: null, body: null };
      return ok(evaluatedDocument(env.begin));
    },
  });
  await capture(env);
  env.midi.emit([0x90, 64, 80], 9);
  await env.controller.finish();
  assert.equal(env.controller.snapshot().state, "UNCONFIRMED");
  assert.equal(env.controller.snapshot().unconfirmedKind, "finish");
  assert.equal(env.shown.some((item) => item.kind === "evaluated"), false);
  const blocked = await env.controller.start();
  assert.equal(blocked.state, "UNCONFIRMED");
  assert.equal(ops(env.calls, "begin").length, 1);
  env.midi.emit([0x90, 65, 80], 10);
  await env.controller.retryFinish();
  assert.equal(ops(env.calls, "finish").length, 2);
  assert.equal(ops(env.calls, "finish")[0].body.attemptId, env.begin.attempt_id);
  assert.equal(ops(env.calls, "finish")[1].body.attemptId, env.begin.attempt_id);
  assert.equal(ops(env.calls, "append").length, 1);
  assert.equal(env.controller.snapshot().state, "EVALUATED");
});

test("a malformed evaluation and a lost cancel do not become feedback", async () => {
  const malformed = harness({
    finishResult: () => ok({ ...evaluatedDocument(beginDocument()), extra: true }),
  });
  await capture(malformed);
  await malformed.controller.finish();
  assert.equal(malformed.controller.snapshot().state, "UNCONFIRMED");
  assert.equal(malformed.shown.some((item) => item.kind === "evaluated"), false);

  const lost = harness({
    cancelResult: () => ({ ok: false, status: 0, error: null, body: null }),
  });
  await capture(lost);
  await lost.controller.cancel();
  assert.equal(lost.controller.snapshot().state, "UNCONFIRMED");
  assert.equal(lost.controller.snapshot().unconfirmedKind, "cancel");
  assert.equal(lost.shown.some((item) => item.kind === "interrupted"), false);
});

test("stale callbacks, input changes, and exit cancellation stay on the old attempt", async () => {
  const env = harness({
    devices: [
      { id: "key-1", name: "Keyboard" },
      { id: "key-2", name: "  " },
    ],
  });
  await env.controller.enableMidi();
  assert.equal(env.controller.snapshot().selectedId, null);
  env.controller.selectInput("missing");
  assert.equal(env.controller.snapshot().selectedId, null);
  env.controller.selectInput("key-2");
  const started = await env.controller.start();
  assert.equal(started.state, "CAPTURING");
  assert.equal(ops(env.calls, "begin")[0].body.deviceId, "key-2");
  const stale = env.midi.listener;
  env.controller.selectInput("key-1");
  assert.equal(env.controller.snapshot().selectedId, "key-2");
  env.midi.emit([0x90, 64, 80], 3, "key-1");
  stale({ device_id: "key-2", raw_payload: [0x90, 64, 80], capture_time_ns: 4 });
  await Promise.resolve();
  assert.equal(ops(env.calls, "append").length, 1);
  env.controller.abandon();
  assert.equal(ops(env.calls, "cancel").length, 1);
  assert.equal(ops(env.calls, "cancel")[0].body.keepalive, true);
  stale({ device_id: "key-2", raw_payload: [0x90, 64, 80], capture_time_ns: 5 });
  await Promise.resolve();
  assert.equal(ops(env.calls, "append").length, 1);
  assert.equal(env.controller.snapshot().state, "IDLE");
});

test("a second start is ignored until the first attempt is terminal", async () => {
  const gate = deferred();
  const env = harness({ beginResult: () => gate.promise });
  const first = capture(env);
  for (let step = 0; step < 8 && ops(env.calls, "begin").length === 0; step += 1) {
    await Promise.resolve();
  }
  const second = await env.controller.start();
  assert.equal(second.state, "STARTING");
  assert.equal(ops(env.calls, "begin").length, 1);
  gate.resolve(ok(env.begin, 201));
  await first;
  assert.equal(env.controller.snapshot().state, "CAPTURING");
});

test("permission denial leaves the controller idle", async () => {
  const env = harness({ permission: "permission_denied", devices: [] });
  const enabled = await env.controller.enableMidi();
  assert.equal(enabled.midiState, "permission_denied");
  const started = await env.controller.start();
  assert.equal(started.state, "IDLE");
  assert.equal(ops(env.calls, "begin").length, 0);
});

test("a late acknowledgement cannot change a newer attempt", async () => {
  const env = harness();
  await capture(env);
  const gate = deferred();
  env.gates.append.push(gate);
  env.midi.emit([0x90, 64, 80], 8);
  const firstId = env.begin.attempt_id;
  env.controller.abandon();
  gate.resolve(ok(acknowledgementDocument(env.begin, 1)));
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(env.controller.snapshot().attemptId, null);
  assert.equal(env.controller.snapshot().acked, 0);
  assert.equal(ops(env.calls, "cancel")[0].body.attemptId, firstId);
  assert.equal(env.shown.some((item) => item.kind === "evaluated"), false);
});
