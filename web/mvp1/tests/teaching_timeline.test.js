import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  TeachingTimeline,
  resolveFocusRangeSeconds,
  roundHalfAwayFromZero,
  secondsAtTick,
  tickAtSeconds,
} from "../teaching-timeline.js";
import { Transport } from "../transport.js";

const VECTORS = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL(
        "../../../resources/presentation/examples/interpolation_vectors.json",
        import.meta.url,
      ),
    ),
    "utf-8",
  ),
);

// 4.5s lesson at 120 BPM / 960 PPQ, matching the golden demo.
const ANCHORS = [
  { schema_version: "1.0.0", tick: 0, seconds: 0.0 },
  { schema_version: "1.0.0", tick: 8640, seconds: 4.5 },
];

function harness() {
  let now = 0;
  const transport = new Transport({ now: () => now });
  const timeline = new TeachingTimeline({ transport });
  transport.setDuration(4.5);
  timeline.setLesson({ lessonId: "half_steps_one_string", anchors: ANCHORS });
  return {
    transport,
    timeline,
    advance(ms) {
      now += ms;
      return now;
    },
    now: () => now,
  };
}

// --- cross-language parity ---------------------------------------------------

test("browser interpolation reproduces the Python reference vectors", () => {
  for (const testCase of VECTORS.cases) {
    for (const probe of testCase.seconds_at_tick) {
      const actual = secondsAtTick(testCase.anchors, probe.tick);
      assert.ok(
        Math.abs(actual - probe.seconds) < 1e-9,
        `${testCase.case_id}: secondsAtTick(${probe.tick}) = ${actual}, expected ${probe.seconds}`,
      );
    }
    for (const probe of testCase.tick_at_seconds) {
      assert.equal(
        tickAtSeconds(testCase.anchors, probe.seconds),
        probe.tick,
        `${testCase.case_id}: tickAtSeconds(${probe.seconds})`,
      );
    }
  }
});

test("vector file covers a tempo change, not just a constant tempo", () => {
  const ids = VECTORS.cases.map((c) => c.case_id);
  assert.ok(ids.includes("tempo_change_120_to_90"));
});

test("rounding follows Musical Core, not banker's rounding", () => {
  // Math.round(-0.5) is -0 in JavaScript; Core rounds halves away from zero.
  assert.equal(roundHalfAwayFromZero(0.5), 1);
  assert.equal(roundHalfAwayFromZero(1.5), 2);
  assert.equal(roundHalfAwayFromZero(2.5), 3);
  assert.equal(roundHalfAwayFromZero(-0.5), -1);
  assert.equal(roundHalfAwayFromZero(-2.5), -3);
});

test("interpolation is monotonic across a tempo change", () => {
  const testCase = VECTORS.cases.find((c) => c.case_id === "tempo_change_120_to_90");
  let previous = -Infinity;
  for (let tick = 0; tick <= 8640; tick += 97) {
    const seconds = secondsAtTick(testCase.anchors, tick);
    assert.ok(seconds >= previous, `non-monotonic at tick ${tick}`);
    previous = seconds;
  }
});

test("positions past the last anchor continue at the final rate", () => {
  assert.ok(Math.abs(secondsAtTick(ANCHORS, 17280) - 9.0) < 1e-9);
  assert.equal(tickAtSeconds(ANCHORS, 9.0), 17280);
});

// --- anchor table validation -------------------------------------------------

test("an empty or malformed anchor table is refused", () => {
  assert.throws(() => secondsAtTick([], 0), /must not be empty/);
  assert.throws(
    () => secondsAtTick([{ tick: 960, seconds: 0.5 }], 960),
    /begin at tick 0/,
  );
  assert.throws(
    () =>
      secondsAtTick(
        [
          { tick: 0, seconds: 0 },
          { tick: 0, seconds: 1 },
        ],
        0,
      ),
    /strictly increasing/,
  );
  assert.throws(
    () =>
      secondsAtTick(
        [
          { tick: 0, seconds: 1 },
          { tick: 960, seconds: 0.5 },
        ],
        0,
      ),
    /non-decreasing/,
  );
});

test("negative positions are refused rather than clamped", () => {
  assert.throws(() => secondsAtTick(ANCHORS, -1), /nonnegative/);
  assert.throws(() => tickAtSeconds(ANCHORS, -0.5), /nonnegative/);
});

// --- coordinator -------------------------------------------------------------

test("the coordinator reports transport state without owning it", () => {
  const { transport, timeline, advance } = harness();
  transport.play(advance(0));
  const state = timeline.timelineState(advance(1000));
  assert.equal(state.playing, true);
  assert.ok(Math.abs(state.position_seconds - 1.0) < 1e-6);
  assert.equal(state.position_tick, 1920);
  assert.equal(state.lesson_id, "half_steps_one_string");
  assert.equal(state.schema_version, "1.0.0");
});

test("the coordinator holds no clock of its own", () => {
  const { timeline, transport, advance } = harness();
  // Time passes but the transport is paused, so the derived position must not move.
  const before = timeline.timelineState(advance(0)).position_seconds;
  advance(5000);
  const after = timeline.timelineState().position_seconds;
  assert.equal(before, after);
  assert.equal(transport.playing, false);
});

test("playback rate changes progression speed, not musical position", () => {
  const { transport, timeline, advance } = harness();
  transport.play(advance(0));
  transport.setRate(0.5, advance(1000));
  const state = timeline.timelineState();
  // One wall second at 1.0x already elapsed; the tick for that second is fixed.
  assert.equal(state.position_tick, 1920);
  assert.equal(state.playback_rate, 0.5);
});

test("loop bounds appear only while the loop is enabled", () => {
  const { transport, timeline } = harness();
  let state = timeline.timelineState();
  assert.equal(state.loop_enabled, false);
  assert.equal(state.loop_start_tick, null);
  assert.equal(state.loop_end_seconds, null);

  transport.setLoop({ startSeconds: 1.0, endSeconds: 2.5 });
  state = timeline.timelineState();
  assert.equal(state.loop_enabled, true);
  assert.equal(state.loop_start_tick, 1920);
  assert.equal(state.loop_end_tick, 4800);

  transport.clearLoop();
  state = timeline.timelineState();
  assert.equal(state.loop_enabled, false);
  assert.equal(state.loop_start_tick, null);
});

test("the playhead carries projection event IDs, deduplicated and in order", () => {
  const { timeline } = harness();
  timeline.setActiveEventIds(["evt-2", "evt-1", "evt-2", "", null, "evt-3"]);
  const playhead = timeline.playheadState();
  assert.deepEqual([...playhead.active_event_ids], ["evt-2", "evt-1", "evt-3"]);
});

test("the playhead carries no canonical_revision_id", () => {
  const { timeline } = harness();
  const playhead = timeline.playheadState();
  assert.ok(!("canonical_revision_id" in playhead));
});

test("silence between notes is a valid playhead state", () => {
  const { timeline } = harness();
  timeline.setActiveEventIds([]);
  assert.deepEqual([...timeline.playheadState().active_event_ids], []);
});

test("followers receive derived state on every transport event", () => {
  const { transport, timeline, advance } = harness();
  const seen = [];
  timeline.addFollower({
    id: "probe",
    onTimeline: (state, reason) => seen.push([reason, state.playing]),
  });
  transport.play(advance(0));
  transport.pause(advance(500));
  assert.deepEqual(
    seen.map(([reason]) => reason),
    ["play", "pause"],
  );
  assert.deepEqual(
    seen.map(([, playing]) => playing),
    [true, false],
  );
});

test("a follower that throws does not stop the others", () => {
  const { transport, timeline, advance } = harness();
  const reached = [];
  timeline.addFollower({
    id: "broken",
    onTimeline: () => {
      throw new Error("render failed");
    },
    onError: (error) => reached.push(`broken:${error.message}`),
  });
  timeline.addFollower({
    id: "healthy",
    onTimeline: () => reached.push("healthy"),
  });
  transport.play(advance(0));
  assert.ok(reached.includes("healthy"));
  assert.ok(reached.includes("broken:render failed"));
  // The music kept going.
  assert.equal(transport.playing, true);
});

test("sequence increases monotonically so consumers can order snapshots", () => {
  const { transport, timeline, advance } = harness();
  const sequences = [];
  timeline.addFollower({
    id: "probe",
    onTimeline: (state) => sequences.push(state.sequence),
  });
  transport.play(advance(0));
  transport.seek(1.0, advance(100));
  transport.pause(advance(200));
  assert.deepEqual(sequences, [...sequences].sort((a, b) => a - b));
  assert.equal(new Set(sequences).size, sequences.length);
});

test("switching lessons clears stale timeline state", () => {
  const { timeline } = harness();
  timeline.setActiveEventIds(["evt-1"]);
  const cleared = [];
  timeline.addFollower({ id: "probe", onClear: () => cleared.push("cleared") });

  timeline.setLesson({
    lessonId: "ascending_scale",
    anchors: [
      { schema_version: "1.0.0", tick: 0, seconds: 0 },
      { schema_version: "1.0.0", tick: 9216, seconds: 4.8 },
    ],
  });

  assert.deepEqual(cleared, ["cleared"]);
  assert.equal(timeline.lessonId, "ascending_scale");
  assert.deepEqual([...timeline.playheadState().active_event_ids], []);
});

test("no lesson means no derived state rather than a fabricated one", () => {
  let now = 0;
  const transport = new Transport({ now: () => now });
  const timeline = new TeachingTimeline({ transport });
  assert.equal(timeline.ready, false);
  assert.equal(timeline.timelineState(), null);
  assert.equal(timeline.playheadState(), null);
  assert.equal(timeline.publish("manual"), null);
});

test("the coordinator refuses to be built without the shared transport", () => {
  assert.throws(() => new TeachingTimeline({}), /requires the shared Transport/);
});

test("a follower without an id is refused", () => {
  const { timeline } = harness();
  assert.throws(() => timeline.addFollower({}), /string id/);
});

test("followers can be removed and stop receiving state", () => {
  const { transport, timeline, advance } = harness();
  const seen = [];
  const remove = timeline.addFollower({
    id: "probe",
    onTimeline: () => seen.push("tick"),
  });
  transport.play(advance(0));
  remove();
  transport.pause(advance(100));
  assert.equal(seen.length, 1);
});

test("diagnostics expose enough to capture browser evidence", () => {
  const { transport, timeline, advance } = harness();
  timeline.addFollower({ id: "media" });
  transport.play(advance(0));
  const diagnostics = timeline.diagnostics(advance(500));
  assert.equal(diagnostics.ready, true);
  assert.equal(diagnostics.lessonId, "half_steps_one_string");
  assert.deepEqual(diagnostics.followers, ["media"]);
  assert.equal(diagnostics.anchorCount, 2);
  assert.ok(diagnostics.timeline.position_tick >= 0);
});

test("disposing releases the transport subscription", () => {
  const { transport, timeline, advance } = harness();
  const seen = [];
  timeline.addFollower({ id: "probe", onTimeline: () => seen.push("tick") });
  timeline.dispose();
  transport.play(advance(0));
  assert.equal(seen.length, 0);
});

// --- focus range -------------------------------------------------------------

test("focus ticks convert to transport loop seconds", () => {
  const range = resolveFocusRangeSeconds(ANCHORS, 1920, 3840);
  assert.ok(Math.abs(range.startSeconds - 1.0) < 1e-9);
  assert.ok(Math.abs(range.endSeconds - 2.0) < 1e-9);
});

test("an inverted or empty focus range is refused", () => {
  assert.throws(() => resolveFocusRangeSeconds(ANCHORS, 3840, 1920), /must exceed/);
  assert.throws(() => resolveFocusRangeSeconds(ANCHORS, 960, 960), /must exceed/);
});

test("non-integer focus ticks are refused", () => {
  assert.throws(() => resolveFocusRangeSeconds(ANCHORS, 1.5, 3840), /integers/);
});
