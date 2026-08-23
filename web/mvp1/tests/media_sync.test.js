import assert from "node:assert/strict";
import test from "node:test";

import {
  DRIFT_HARD_SEEK_THRESHOLD_MS,
  DRIFT_SYNCED_THRESHOLD_MS,
  HARD_SEEK_SETTLE_MS,
  MediaSyncFollower,
  SyncCorrection,
  SyncMode,
  SyncStatus,
  calculateDriftMs,
  chooseSyncCorrection,
  classifySyncHealth,
  lessonTimeToMediaTime,
} from "../media-sync.js";

/**
 * Purpose-built media element stub. Deliberately not jsdom: the follower only
 * touches six properties, and a stub makes the seek/rate commands observable.
 */
function fakeMedia({ readyState = 4, paused = true } = {}) {
  return {
    currentTime: 0,
    playbackRate: 1,
    paused,
    readyState,
    seeks: [],
    playCalls: 0,
    pauseCalls: 0,
    play() {
      this.playCalls += 1;
      this.paused = false;
      return Promise.resolve();
    },
    pause() {
      this.pauseCalls += 1;
      this.paused = true;
    },
  };
}

const PARTIAL_BINDING = {
  schema_version: "1.0.0",
  binding_id: "binding-half-steps-demo",
  lesson_id: "half_steps_one_string",
  media_id: "half-steps-demo-video",
  sync_mode: "synchronized",
  lesson_anchor_seconds: 0,
  media_anchor_seconds: 0,
  lesson_end_seconds: 3.0,
  media_end_seconds: 3.0,
};

const OFFSET_BINDING = {
  ...PARTIAL_BINDING,
  binding_id: "binding-offset",
  lesson_anchor_seconds: 10,
  media_anchor_seconds: 3,
  lesson_end_seconds: 14,
  media_end_seconds: 7,
};

const OPEN_BINDING = {
  ...PARTIAL_BINDING,
  binding_id: "binding-open",
  lesson_end_seconds: null,
  media_end_seconds: null,
};

function timelineState(overrides = {}) {
  return {
    schema_version: "1.0.0",
    lesson_id: "half_steps_one_string",
    sequence: 1,
    position_tick: 0,
    position_seconds: 0,
    playing: true,
    playback_rate: 1,
    loop_enabled: false,
    repetition_index: 0,
    loop_start_tick: null,
    loop_end_tick: null,
    loop_start_seconds: null,
    loop_end_seconds: null,
    ...overrides,
  };
}

function follower(element, { binding = PARTIAL_BINDING, now } = {}) {
  let clock = 0;
  const f = new MediaSyncFollower({
    id: "media:test",
    getElement: () => element,
    now: now || (() => clock),
  });
  if (binding) {
    f.setBinding(binding);
  }
  return {
    follower: f,
    advance(ms) {
      clock += ms;
      return clock;
    },
  };
}

// --- pure policy -------------------------------------------------------------

test("drift keeps its sign so corrections point the right way", () => {
  assert.ok(Math.abs(calculateDriftMs(1.0, 1.05) - 50) < 1e-9);
  assert.ok(Math.abs(calculateDriftMs(1.0, 0.95) + 50) < 1e-9);
  assert.ok(calculateDriftMs(1.0, 0.95) < 0);
});

test("classification bands match the declared thresholds", () => {
  assert.equal(classifySyncHealth(0), SyncStatus.SYNCED);
  assert.equal(classifySyncHealth(DRIFT_SYNCED_THRESHOLD_MS), SyncStatus.SYNCED);
  assert.equal(classifySyncHealth(DRIFT_SYNCED_THRESHOLD_MS + 0.1), SyncStatus.DRIFTING);
  assert.equal(classifySyncHealth(DRIFT_HARD_SEEK_THRESHOLD_MS), SyncStatus.DRIFTING);
  assert.equal(classifySyncHealth(DRIFT_HARD_SEEK_THRESHOLD_MS + 0.1), SyncStatus.CORRECTING);
  assert.equal(classifySyncHealth(-250), SyncStatus.CORRECTING);
});

test("status and correction never disagree", () => {
  const pairs = {
    [SyncStatus.SYNCED]: SyncCorrection.NONE,
    [SyncStatus.DRIFTING]: SyncCorrection.RESAMPLE,
    [SyncStatus.CORRECTING]: SyncCorrection.HARD_SEEK,
  };
  for (const drift of [0, 20, 40, 40.1, 75, 150, 150.1, 5000, -5000]) {
    assert.equal(pairs[classifySyncHealth(drift)], chooseSyncCorrection(drift));
  }
});

test("zero-offset binding is identity and offset binding shifts", () => {
  assert.equal(lessonTimeToMediaTime(PARTIAL_BINDING, 2.5), 2.5);
  assert.equal(lessonTimeToMediaTime(OFFSET_BINDING, 14), 7);
});

test("out-of-range lesson time maps to null, never an extrapolation", () => {
  assert.equal(lessonTimeToMediaTime(PARTIAL_BINDING, 3.0), 3.0);
  assert.equal(lessonTimeToMediaTime(PARTIAL_BINDING, 3.1), null);
  assert.equal(lessonTimeToMediaTime(OFFSET_BINDING, 9.9), null);
});

test("an open-ended binding has no upper bound", () => {
  assert.equal(lessonTimeToMediaTime(OPEN_BINDING, 9999), 9999);
});

test("a detached binding maps nothing", () => {
  const detached = { ...PARTIAL_BINDING, sync_mode: "detached" };
  assert.equal(lessonTimeToMediaTime(detached, 1.0), null);
});

// --- follower behavior -------------------------------------------------------

test("a detached follower reports detached and issues no commands", () => {
  const media = fakeMedia();
  const { follower: f } = follower(media, { binding: null });
  const health = f.onTimeline(timelineState({ position_seconds: 1.0 }));
  assert.equal(health.status, SyncStatus.DETACHED);
  assert.equal(health.drift_ms, null);
  assert.equal(media.playCalls, 0);
  assert.deepEqual(media.seeks, []);
});

test("synchronizing without a binding is refused rather than inferred", () => {
  const media = fakeMedia();
  const { follower: f } = follower(media, { binding: null });
  assert.equal(f.setMode(SyncMode.SYNCHRONIZED), SyncMode.DETACHED);
});

test("an aligned follower is SYNCED and is left alone", () => {
  const media = fakeMedia({ paused: false });
  media.currentTime = 1.0;
  const { follower: f } = follower(media);
  const health = f.onTimeline(timelineState({ position_seconds: 1.0 }));
  assert.equal(health.status, SyncStatus.SYNCED);
  assert.equal(health.last_correction, SyncCorrection.NONE);
  assert.equal(f.hardSeekCount, 0);
});

test("medium drift nudges playback rate instead of seeking", () => {
  const media = fakeMedia({ paused: false });
  media.currentTime = 1.075; // 75 ms ahead
  const { follower: f } = follower(media);
  const health = f.onTimeline(timelineState({ position_seconds: 1.0 }));
  assert.equal(health.status, SyncStatus.DRIFTING);
  assert.equal(health.last_correction, SyncCorrection.RESAMPLE);
  assert.equal(f.hardSeekCount, 0);
  // Ahead of schedule, so it must slow down.
  assert.ok(media.playbackRate < 1);
});

test("a follower running behind is nudged faster, not slower", () => {
  const media = fakeMedia({ paused: false });
  media.currentTime = 0.925; // 75 ms behind
  const { follower: f } = follower(media);
  f.onTimeline(timelineState({ position_seconds: 1.0 }));
  assert.ok(media.playbackRate > 1);
});

test("large drift earns a hard seek to the expected position", () => {
  const media = fakeMedia({ paused: false });
  media.currentTime = 1.5; // 500 ms ahead
  const { follower: f } = follower(media);
  const health = f.onTimeline(timelineState({ position_seconds: 1.0 }));
  assert.equal(health.status, SyncStatus.CORRECTING);
  assert.equal(health.last_correction, SyncCorrection.HARD_SEEK);
  assert.equal(f.hardSeekCount, 1);
  assert.equal(media.currentTime, 1.0);
});

test("small jitter never causes a seek, however many frames pass", () => {
  const media = fakeMedia({ paused: false });
  const { follower: f } = follower(media);
  for (let frame = 0; frame < 200; frame += 1) {
    // +/- 30 ms of jitter, inside the synced band.
    media.currentTime = 1.0 + (frame % 2 === 0 ? 0.03 : -0.03);
    f.onTimeline(timelineState({ position_seconds: 1.0 }));
  }
  assert.equal(f.hardSeekCount, 0);
});

test("a hard seek settles before another can be issued", () => {
  const media = fakeMedia({ paused: false });
  const { follower: f, advance } = follower(media);

  media.currentTime = 2.0;
  f.onTimeline(timelineState({ position_seconds: 1.0 }));
  assert.equal(f.hardSeekCount, 1);

  // The element has not physically arrived yet. Measuring now would read the
  // stale position and fire another seek: that is the thrashing D12 forbids.
  media.currentTime = 2.0;
  advance(HARD_SEEK_SETTLE_MS / 2);
  const during = f.onTimeline(timelineState({ position_seconds: 1.05 }));
  assert.equal(during.status, SyncStatus.CORRECTING);
  assert.equal(f.hardSeekCount, 1);

  // Once settled and actually aligned, no further correction is needed.
  advance(HARD_SEEK_SETTLE_MS);
  media.currentTime = 1.1;
  const after = f.onTimeline(timelineState({ position_seconds: 1.1 }));
  assert.equal(after.status, SyncStatus.SYNCED);
  assert.equal(f.hardSeekCount, 1);
});

test("an explicit seek repositions the element immediately", () => {
  const media = fakeMedia({ paused: false });
  media.currentTime = 1.0;
  const { follower: f } = follower(media);
  const health = f.onTimeline(timelineState({ position_seconds: 2.0 }), "seek");
  assert.equal(health.last_correction, SyncCorrection.HARD_SEEK);
  assert.equal(media.currentTime, 2.0);
});

test("a loop wrap repositions the element immediately", () => {
  const media = fakeMedia({ paused: false });
  media.currentTime = 2.4;
  const { follower: f } = follower(media);
  f.onTimeline(timelineState({ position_seconds: 1.0 }), "loop-wrap");
  assert.equal(media.currentTime, 1.0);
});

test("play and pause follow the shared transport", () => {
  const media = fakeMedia({ paused: true });
  const { follower: f } = follower(media);
  f.onTimeline(timelineState({ position_seconds: 1.0, playing: true }));
  assert.equal(media.paused, false);
  f.onTimeline(timelineState({ position_seconds: 1.0, playing: false }));
  assert.equal(media.paused, true);
});

test("the shared playback rate is applied when aligned", () => {
  const media = fakeMedia({ paused: false });
  media.currentTime = 1.0;
  const { follower: f } = follower(media);
  f.onTimeline(timelineState({ position_seconds: 1.0, playback_rate: 0.75 }));
  assert.equal(media.playbackRate, 0.75);
});

test("past the binding range the follower stops and says so", () => {
  const media = fakeMedia({ paused: false });
  media.currentTime = 3.0;
  const { follower: f } = follower(media);
  // The golden case: a 3.0s clip against a 4.5s lesson, at lesson t=3.5s.
  const health = f.onTimeline(timelineState({ position_seconds: 3.5 }));
  assert.equal(health.status, SyncStatus.OUT_OF_BINDING_RANGE);
  assert.equal(health.drift_ms, null);
  assert.equal(health.expected_time_seconds, null);
  assert.equal(media.paused, true);
  // Crucially, it did not seek the element somewhere the binding never claimed.
  assert.equal(media.currentTime, 3.0);
});

test("a stalled element degrades without stopping anything else", () => {
  const media = fakeMedia({ readyState: 0, paused: false });
  const { follower: f } = follower(media);
  const health = f.onTimeline(timelineState({ position_seconds: 1.0 }));
  assert.equal(health.status, SyncStatus.DEGRADED);
  assert.equal(health.drift_ms, null);
  assert.equal(f.hardSeekCount, 0);
});

test("a missing element is unavailable, not an exception", () => {
  const f = new MediaSyncFollower({ id: "media:test", getElement: () => null });
  f.setBinding(PARTIAL_BINDING);
  const health = f.onTimeline(timelineState({ position_seconds: 1.0 }));
  assert.equal(health.status, SyncStatus.UNAVAILABLE);
  assert.equal(health.drift_ms, null);
});

test("an element that throws on seek is reported, not propagated", () => {
  const media = fakeMedia({ paused: false });
  media.currentTime = 5.0;
  Object.defineProperty(media, "currentTime", {
    get: () => 5.0,
    set: () => {
      throw new Error("seek refused");
    },
  });
  const { follower: f } = follower(media);
  assert.doesNotThrow(() => f.onTimeline(timelineState({ position_seconds: 1.0 })));
});

test("an element whose play() rejects does not throw into the timeline", () => {
  const media = fakeMedia({ paused: true });
  media.currentTime = 1.0;
  media.play = () => Promise.reject(new Error("autoplay blocked"));
  const { follower: f } = follower(media);
  assert.doesNotThrow(() => f.onTimeline(timelineState({ position_seconds: 1.0 })));
});

test("toggling to detached leaves the element alone afterwards", () => {
  const media = fakeMedia({ paused: false });
  media.currentTime = 5.0;
  const { follower: f } = follower(media);
  f.setMode(SyncMode.DETACHED);
  const health = f.onTimeline(timelineState({ position_seconds: 1.0 }));
  assert.equal(health.status, SyncStatus.DETACHED);
  assert.equal(media.currentTime, 5.0);
  assert.equal(f.hardSeekCount, 0);
});

test("toggling back to synchronized resumes following", () => {
  const media = fakeMedia({ paused: false });
  media.currentTime = 5.0;
  const { follower: f } = follower(media);
  f.setMode(SyncMode.DETACHED);
  f.setMode(SyncMode.SYNCHRONIZED);
  f.onTimeline(timelineState({ position_seconds: 1.0 }));
  assert.equal(media.currentTime, 1.0);
});

test("switching lessons drops the binding and returns to detached", () => {
  const media = fakeMedia({ paused: false });
  const { follower: f } = follower(media);
  f.onLesson();
  assert.equal(f.binding, null);
  assert.equal(f.mode, SyncMode.DETACHED);
  assert.equal(f.health(), null);
});

test("health records carry a monotonic sequence", () => {
  const media = fakeMedia({ paused: false });
  media.currentTime = 1.0;
  const { follower: f } = follower(media);
  const sequences = [];
  for (let i = 0; i < 5; i += 1) {
    sequences.push(f.onTimeline(timelineState({ position_seconds: 1.0 })).sequence);
  }
  assert.deepEqual(sequences, [1, 2, 3, 4, 5]);
});

test("the follower never writes to the transport", () => {
  const media = fakeMedia({ paused: false });
  const { follower: f } = follower(media);
  const state = timelineState({ position_seconds: 1.0 });
  const before = JSON.stringify(state);
  f.onTimeline(state);
  assert.equal(JSON.stringify(state), before);
});

test("constructing without getElement is refused", () => {
  assert.throws(() => new MediaSyncFollower({ id: "x" }), /getElement/);
});


// --- unseekable media --------------------------------------------------------
//
// A media element can be fully buffered and still refuse to seek: the bundled
// DO-011 placeholder clip reports seekable=[0,0] with buffered=[0,3]. Retrying
// a seek it will always ignore is the thrashing D12 forbids, just slower.

function unseekableMedia() {
  const media = fakeMedia({ paused: false });
  media.seekable = { length: 0, start: () => 0, end: () => 0 };
  return media;
}

function partlySeekableMedia() {
  const media = fakeMedia({ paused: false });
  media.seekable = { length: 1, start: () => 0, end: () => 1.5 };
  return media;
}

test("an unseekable element is reported DEGRADED instead of seeked forever", () => {
  const media = unseekableMedia();
  media.currentTime = 0;
  const { follower: f } = follower(media);
  for (let i = 0; i < 50; i += 1) {
    const health = f.onTimeline(timelineState({ position_seconds: 2.0 }));
    assert.equal(health.status, SyncStatus.DEGRADED);
  }
  assert.equal(f.hardSeekCount, 0);
  assert.equal(media.currentTime, 0);
});

test("an explicit seek against an unseekable element also degrades", () => {
  const media = unseekableMedia();
  const { follower: f } = follower(media);
  const health = f.onTimeline(timelineState({ position_seconds: 2.0 }), "seek");
  assert.equal(health.status, SyncStatus.DEGRADED);
  assert.equal(health.drift_ms, null);
  assert.equal(f.hardSeekCount, 0);
});

test("a position inside the seekable range is still corrected", () => {
  const media = partlySeekableMedia();
  media.currentTime = 0;
  const { follower: f } = follower(media);
  f.onTimeline(timelineState({ position_seconds: 1.0 }));
  assert.equal(f.hardSeekCount, 1);
  assert.equal(media.currentTime, 1.0);
});

test("a position outside the seekable range degrades rather than seeking", () => {
  const media = partlySeekableMedia();
  media.currentTime = 0;
  const { follower: f } = follower(media);
  const health = f.onTimeline(timelineState({ position_seconds: 2.5 }));
  assert.equal(health.status, SyncStatus.DEGRADED);
  assert.equal(f.hardSeekCount, 0);
});

test("an element that reports no seekable property at all is assumed seekable", () => {
  // Keeps the stub-friendly path working, and matches elements that have not
  // yet reported ranges.
  const media = fakeMedia({ paused: false });
  media.currentTime = 5.0;
  const { follower: f } = follower(media);
  f.onTimeline(timelineState({ position_seconds: 1.0 }));
  assert.equal(f.hardSeekCount, 1);
});

// --- settle window reports measurement, not the command that opened it -------

test("a settled element is reported as synced before the window expires", () => {
  const media = fakeMedia({ paused: false });
  const { follower: f, advance } = follower(media);

  media.currentTime = 2.0;
  f.onTimeline(timelineState({ position_seconds: 1.0 }));
  assert.equal(f.hardSeekCount, 1);

  // The seek landed early, as seeks usually do. The window must not keep
  // asserting CORRECTING over an element that is demonstrably in sync: the
  // status is a measurement, and this one measures zero drift.
  advance(HARD_SEEK_SETTLE_MS / 2);
  media.currentTime = 1.05;
  const health = f.onTimeline(timelineState({ position_seconds: 1.05 }));
  assert.equal(health.status, SyncStatus.SYNCED);
  assert.ok(Math.abs(health.drift_ms) <= 40);
  // No command was issued this cycle, so none may be reported.
  assert.equal(health.last_correction, SyncCorrection.NONE);
  assert.equal(f.hardSeekCount, 1);

  // Converging ends the window early, so real drift is acted on immediately
  // rather than being ignored for the remainder of it.
  media.currentTime = 3.0;
  const next = f.onTimeline(timelineState({ position_seconds: 1.05 }));
  assert.equal(next.status, SyncStatus.CORRECTING);
  assert.equal(f.hardSeekCount, 2);
});

test("no correction is claimed for a cycle that issued no command", () => {
  const media = fakeMedia({ paused: false });
  const { follower: f, advance } = follower(media);

  media.currentTime = 2.0;
  f.onTimeline(timelineState({ position_seconds: 1.0 }));

  // Still far out of position, still inside the window: one seek is in flight,
  // and reporting HARD_SEEK again would count a command that never happened.
  advance(HARD_SEEK_SETTLE_MS / 2);
  media.currentTime = 2.0;
  const during = f.onTimeline(timelineState({ position_seconds: 1.05 }));
  assert.equal(during.status, SyncStatus.CORRECTING);
  assert.equal(during.last_correction, SyncCorrection.NONE);
  assert.equal(f.hardSeekCount, 1);
});

// --- both ends of a binding are real bounds ----------------------------------

test("a binding bounded only on the media side still stops at the media end", () => {
  // MediaTimelineBindingV1 makes the two ends independently optional, so this
  // shape is legal: a 3.0s clip declared against a lesson with no declared end.
  const mediaOnly = {
    ...PARTIAL_BINDING,
    binding_id: "binding-media-bounded",
    lesson_end_seconds: null,
    media_end_seconds: 3.0,
  };
  assert.equal(lessonTimeToMediaTime(mediaOnly, 2.9), 2.9);
  assert.equal(lessonTimeToMediaTime(mediaOnly, 3.0), 3.0);
  // Past the clip. Answering 4.5 here is precisely the extrapolation the
  // out-of-range answer exists to refuse.
  assert.equal(lessonTimeToMediaTime(mediaOnly, 4.5), null);

  const media = fakeMedia({ paused: false });
  const { follower: f } = follower(media, { binding: mediaOnly });
  const health = f.onTimeline(timelineState({ position_seconds: 4.5 }));
  assert.equal(health.status, SyncStatus.OUT_OF_BINDING_RANGE);
  assert.equal(health.drift_ms, null);
  assert.equal(media.pauseCalls, 1);
});
