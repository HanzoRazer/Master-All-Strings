import assert from "node:assert/strict";
import test from "node:test";

import { AudioScheduler } from "../audio_scheduler.js";
import { Transport } from "../transport.js";

function harness(events = []) {
  let nowMs = 0;
  const transport = new Transport({ now: () => nowMs });
  transport.setDuration(4);
  const synth = {
    context: { currentTime: 10 },
    readiness: "ready",
    calls: [],
    panics: 0,
    scheduleNote(...args) { this.calls.push(args); },
    panic() { this.panics += 1; },
  };
  const diagnostics = [];
  const scheduler = new AudioScheduler({
    transport,
    synth,
    lookaheadSeconds: 0.2,
    onDiagnostic: (item) => diagnostics.push(item),
  });
  scheduler.loadPlan({
    schema_version: "1.0.0",
    assignment_id: "assignment-1",
    content_id: "content-1",
    total_seconds: 4,
    events,
  });
  return {
    transport,
    synth,
    scheduler,
    diagnostics,
    advance(milliseconds) { nowMs += milliseconds; },
  };
}

const melody = [
  { event_id: "a", midi_note: 60, velocity: 64, onset_seconds: 0, release_seconds: 0.5 },
  { event_id: "b", midi_note: 62, velocity: 96, onset_seconds: 1, release_seconds: 1.5 },
];

test("play schedules canonical events inside the lookahead window", () => {
  const { transport, synth, scheduler, diagnostics } = harness(melody);
  transport.play();

  assert.equal(synth.calls.length, 1);
  assert.deepEqual(synth.calls[0][0], {
    eventId: "a", midiNote: 60, velocity: 64, centsOffset: undefined,
  });
  assert.equal(synth.calls[0][1], 10);
  assert.equal(synth.calls[0][2], 10.5);
  assert.equal(diagnostics.at(-1).eventId, "a");
  scheduler.destroy();
});

test("practice rate scales schedule time but never pitch", () => {
  const { transport, synth, scheduler } = harness(melody);
  transport.setRate(0.5);
  transport.play();
  assert.equal(synth.calls[0][0].midiNote, 60);
  assert.equal(synth.calls[0][2], 11);

  transport.setRate(1.5);
  assert.ok(synth.panics >= 2);
  scheduler.tick();
  assert.equal(synth.calls.at(-1)[0].midiNote, 60);
  scheduler.destroy();
});

test("pause, seek, restart, rate, and lesson changes panic stale voices", () => {
  const { transport, synth, scheduler } = harness(melody);
  transport.play();
  const baseline = synth.panics;
  transport.pause();
  transport.seek(1);
  transport.setRate(0.75);
  transport.restart();
  scheduler.loadPlan({
    schema_version: "1.0.0", total_seconds: 1, events: [melody[0]],
  });
  assert.equal(synth.panics, baseline + 5);
  assert.equal(scheduler.scheduled.size, 0);
  scheduler.destroy();
});

test("seeking into an active note schedules only its remaining duration", () => {
  const { transport, synth, scheduler } = harness(melody);
  transport.seek(0.25);
  transport.play();
  assert.equal(synth.calls[0][1], 10);
  assert.equal(synth.calls[0][2], 10.25);
  scheduler.destroy();
});

test("spatially unplayable pitches need no special scheduler path", () => {
  const low = [
    { event_id: "low", midi_note: 20, velocity: 80, onset_seconds: 0, release_seconds: 1 },
  ];
  const { transport, synth, scheduler } = harness(low);
  transport.play();
  assert.equal(synth.calls[0][0].midiNote, 20);
  scheduler.destroy();
});

test("disabled sound and stopped scheduler produce no notes", () => {
  const { transport, synth, scheduler } = harness(melody);
  scheduler.setEnabled(false);
  transport.play();
  assert.equal(synth.calls.length, 0);
  scheduler.start();
  scheduler.stop();
  assert.ok(synth.panics >= 2);
  scheduler.destroy();
});

test("invalid playback plans are rejected", () => {
  const { scheduler } = harness();
  assert.throws(() => scheduler.loadPlan({}), /unsupported/);
  assert.throws(
    () => scheduler.loadPlan({
      schema_version: "1.0.0",
      total_seconds: 1,
      events: [
        { event_id: "bad", onset_seconds: 1, release_seconds: 1 },
      ],
    }),
    /positive durations/,
  );
  scheduler.destroy();
});
