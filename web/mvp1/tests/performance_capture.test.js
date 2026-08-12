import test from "node:test";
import assert from "node:assert/strict";
import { PerformanceCaptureController } from "../performance_capture.js";
test("Start Attempt coordinates restart capture and playback", async () => {
  const calls = [];
  const transport = {
    restart: () => calls.push("restart"),
    play: () => calls.push("play"),
    snapshot: () => ({
      positionSeconds: 0,
      repetitionCount: 0,
      playbackRate: 1,
    }),
  };
  const midi = { connect: () => true };
  const api = {
    arm: async () => calls.push("arm"),
    start: async () => calls.push("capture"),
    message: async () => {},
    stop: async () => ({}),
    interrupt: async () => {},
  };
  const c = new PerformanceCaptureController({
    midiInput: midi,
    transport,
    api,
  });
  await c.arm("d");
  await c.startAttempt();
  assert.deepEqual(calls, ["arm", "restart", "capture", "play"]);
});
test("messages preserve shared transport repetition context", async () => {
  let body;
  const transport = {
    restart() {},
    play() {},
    snapshot: () => ({
      positionSeconds: 2,
      repetitionCount: 3,
      playbackRate: 0.5,
    }),
  };
  const api = {
    arm: async () => {},
    start: async () => {},
    message: async (x) => (body = x),
    stop: async () => ({}),
    interrupt: async () => {},
  };
  const c = new PerformanceCaptureController({
    midiInput: { connect: () => true },
    transport,
    api,
  });
  await c.arm("d");
  await c.startAttempt();
  await c.record({ raw_payload: [144, 60, 90] });
  assert.equal(body.repetition_index, 3);
});

test("three loop repetitions retain independent observation context", async () => {
  const seen = [];
  let repetition = 0;
  const transport = {
    restart() {
      repetition = 0;
    },
    play() {},
    snapshot: () => ({
      positionSeconds: 0.1,
      repetitionCount: repetition,
      playbackRate: 1,
    }),
  };
  const api = {
    arm: async () => {},
    start: async () => {},
    message: async (x) => seen.push(x),
    stop: async () => ({}),
    interrupt: async () => {},
  };
  const c = new PerformanceCaptureController({
    midiInput: { connect: () => true },
    transport,
    api,
  });
  await c.arm("d");
  await c.startAttempt();
  for (repetition = 0; repetition < 3; repetition++)
    await c.record({ raw_payload: [144, 60, 90] });
  assert.deepEqual(
    seen.map((x) => x.repetition_index),
    [0, 1, 2],
  );
});
