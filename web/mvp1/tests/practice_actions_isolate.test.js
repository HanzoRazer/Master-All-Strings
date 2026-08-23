import assert from "node:assert/strict";
import test from "node:test";

import { PracticeActionController } from "../practice_actions.js";
import { resolveFocusRangeSeconds } from "../teaching-timeline.js";
import { Transport } from "../transport.js";

// 4.5s lesson at 120 BPM / 960 PPQ.
const ANCHORS = [
  { schema_version: "1.0.0", tick: 0, seconds: 0.0 },
  { schema_version: "1.0.0", tick: 8640, seconds: 4.5 },
];

/** Records what the Educational API was asked to do, and answers it. */
function fakeApi() {
  const calls = [];
  return {
    calls,
    applyAction: async (payload) => {
      calls.push(payload);
      return { applied: true };
    },
  };
}

function controller({ anchors = ANCHORS, targetRepetitions = () => null } = {}) {
  let now = 0;
  const transport = new Transport({ now: () => now });
  transport.setDuration(4.5);
  const status = [];
  const actions = new PracticeActionController({
    transport,
    onStatus: (m) => status.push(m),
    resolveFocusRange: anchors
      ? (startTick, endTick) => {
          try {
            return resolveFocusRangeSeconds(anchors, startTick, endTick);
          } catch (_) {
            return null;
          }
        }
      : undefined,
    targetRepetitions,
  });
  return { actions, transport, status, advance: (ms) => (now += ms) };
}

const ISOLATE = {
  action_type: "isolate_passage",
  focus_start_tick: 1920,
  focus_end_tick: 3840,
  message_key: "isolate",
  reason_finding_ids: ["f1"],
};

// --- the gap this closes -----------------------------------------------------

test("ISOLATE_PASSAGE now sets an actual practice loop", async () => {
  const { actions, transport } = controller();
  await actions.apply(ISOLATE, fakeApi());
  assert.ok(transport.loop, "no loop was applied");
  assert.equal(transport.loop.enabled, true);
  assert.ok(Math.abs(transport.loop.startSeconds - 1.0) < 1e-9);
  assert.ok(Math.abs(transport.loop.endSeconds - 2.0) < 1e-9);
});

test("the loop range is the Educational range, not a widened one", async () => {
  const { actions, transport } = controller();
  await actions.apply(ISOLATE, fakeApi());
  // 1920 and 3840 ticks are exactly 1.0s and 2.0s. No snapping, no padding.
  assert.equal(transport.loop.startSeconds, 1.0);
  assert.equal(transport.loop.endSeconds, 2.0);
});

test("the practice policy's repetition target is carried into the loop", async () => {
  const { actions, transport } = controller({ targetRepetitions: () => 3 });
  await actions.apply(ISOLATE, fakeApi());
  assert.equal(transport.loop.targetRepetitions, 3);
});

// --- Educational output is untouched ----------------------------------------

test("the Educational API receives exactly the action it issued", async () => {
  const { actions } = controller();
  const api = fakeApi();
  await actions.apply(ISOLATE, api);
  assert.deepEqual(api.calls, [
    {
      action_type: "isolate_passage",
      target_rate: undefined,
      focus_start_tick: 1920,
      focus_end_tick: 3840,
      message_key: "isolate",
    },
  ]);
});

test("applying an action does not mutate it", async () => {
  const { actions } = controller();
  const action = { ...ISOLATE };
  const before = JSON.stringify(action);
  await actions.apply(action, fakeApi());
  assert.equal(JSON.stringify(action), before);
});

test("the adapter makes no Educational decision when the range is absent", async () => {
  const { actions, transport, status } = controller();
  await actions.apply(
    { ...ISOLATE, focus_start_tick: null, focus_end_tick: null },
    fakeApi(),
  );
  assert.equal(transport.loop, null);
  assert.ok(status.some((m) => m.includes("Isolate passage")));
});

// --- degradation -------------------------------------------------------------

test("without anchors the action is reported rather than guessed at", async () => {
  const { actions, transport, status } = controller({ anchors: null });
  await actions.apply(ISOLATE, fakeApi());
  assert.equal(transport.loop, null);
  assert.ok(status.some((m) => m.includes("no timeline anchors")));
});

test("an inverted focus range is refused, not reversed", async () => {
  const { actions, transport } = controller();
  await actions.apply(
    { ...ISOLATE, focus_start_tick: 3840, focus_end_tick: 1920 },
    fakeApi(),
  );
  assert.equal(transport.loop, null);
});

test("a focus range past the lesson end is clamped, not rejected", async () => {
  const { actions, transport } = controller();
  // 8640 ticks is exactly the 4.5s end; 12000 would run past it.
  await actions.apply(
    { ...ISOLATE, focus_start_tick: 6720, focus_end_tick: 12000 },
    fakeApi(),
  );
  assert.ok(transport.loop, "a final-bar passage should still be loopable");
  assert.equal(transport.loop.endSeconds, 4.5);
});

test("a transport-refused loop is reported, not thrown", async () => {
  const { actions, transport, status } = controller();
  transport.setDuration(0.5);
  await assert.doesNotReject(() => actions.apply(ISOLATE, fakeApi()));
  assert.equal(transport.loop, null);
  assert.ok(status.some((m) => m.includes("Isolate passage")));
});

// --- other actions are unchanged ---------------------------------------------

test("SLOW_DOWN still only changes rate", async () => {
  const { actions, transport } = controller();
  await actions.apply(
    { action_type: "slow_down", target_rate: 0.75, message_key: "slow" },
    fakeApi(),
  );
  assert.equal(transport.playbackRate, 0.75);
  assert.equal(transport.loop, null);
});

test("CONTINUE and REPEAT set no loop", async () => {
  for (const action_type of ["continue", "repeat"]) {
    const { actions, transport } = controller();
    await actions.apply({ action_type, message_key: "m" }, fakeApi());
    assert.equal(transport.loop, null, `${action_type} should not loop`);
  }
});

test("a null action is a no-op", async () => {
  const { actions } = controller();
  assert.equal(await actions.apply(null, fakeApi()), null);
});

// --- repetition --------------------------------------------------------------

test("the isolate loop repeats without duplicating anything", async () => {
  const { actions, transport, advance } = controller();
  await actions.apply(ISOLATE, fakeApi());
  // Start at the loop start, so elapsed time maps to whole passes.
  transport.seek(1.0);
  transport.play(advance(0));
  // Three full passes through a 1.0s loop, plus a little.
  transport.positionSeconds(advance(3100));
  assert.equal(transport.repetitionCount, 3);
  assert.equal(transport.loop.startSeconds, 1.0);
  assert.equal(transport.loop.endSeconds, 2.0);
});
