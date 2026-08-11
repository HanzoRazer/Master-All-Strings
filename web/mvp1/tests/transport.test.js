import assert from "node:assert/strict";
import test from "node:test";

import { PresentationTransport, Transport } from "../transport.js";

function clock() {
  let now = 0;
  return {
    now: () => now,
    advance: (milliseconds) => {
      now += milliseconds;
    },
  };
}

test("transport is the backwards-compatible shared authority", () => {
  assert.equal(PresentationTransport, Transport);
});

test("play, pause, seek, restart, and rate preserve one anchored position", () => {
  const time = clock();
  const transport = new Transport({ now: time.now });
  transport.setDuration(10);

  transport.play();
  time.advance(1000);
  assert.equal(transport.positionSeconds(), 1);
  transport.setRate(0.5);
  time.advance(1000);
  assert.equal(transport.positionSeconds(), 1.5);
  transport.pause();
  time.advance(1000);
  assert.equal(transport.positionSeconds(), 1.5);
  transport.seek(8);
  assert.equal(transport.positionSeconds(), 8);
  transport.restart();
  assert.equal(transport.positionSeconds(), 0);
  assert.equal(transport.playing, false);
});

test("supported practice rates never mutate musical duration", () => {
  const transport = new Transport({ now: () => 0 });
  transport.setDuration(12);

  for (const rate of [0.5, 0.75, 1, 1.5]) {
    transport.setRate(rate);
    assert.equal(transport.durationSeconds, 12);
  }
  assert.throws(() => transport.setRate(2), /rate must be one of/);
});

test("subscribers receive immutable command snapshots and can unsubscribe", () => {
  const transport = new Transport({ now: () => 0 });
  const events = [];
  const unsubscribe = transport.subscribe((event) => events.push(event));
  transport.setDuration(4);
  transport.play();
  unsubscribe();
  transport.pause();

  assert.deepEqual(events.map((event) => event.type), ["duration", "play"]);
  assert.equal(Object.isFrozen(events[0]), true);
});

test("loop configuration validates canonical-derived seconds", () => {
  const transport = new Transport({ now: () => 0 });
  transport.setDuration(4);
  transport.setLoop({ startSeconds: 1, endSeconds: 3, targetRepetitions: 3 });
  assert.deepEqual(transport.loop, {
    enabled: true,
    startSeconds: 1,
    endSeconds: 3,
    targetRepetitions: 3,
  });
  assert.throws(
    () => transport.setLoop({ startSeconds: 3, endSeconds: 2 }),
    /start < end/,
  );
  transport.clearLoop();
  assert.equal(transport.loop, null);
});

test("duration and seek reject invalid numbers and clamp valid positions", () => {
  const transport = new Transport({ now: () => 0 });
  assert.throws(() => transport.setDuration(-1), /duration/);
  transport.setDuration(5);
  transport.seek(-2);
  assert.equal(transport.positionSeconds(), 0);
  transport.seek(20);
  assert.equal(transport.positionSeconds(), 5);
  assert.throws(() => transport.seek(Number.NaN), /finite/);
});

test("loop wraps visual and audio consumers through one position", () => {
  const time = clock();
  const transport = new Transport({ now: time.now });
  const events = [];
  transport.subscribe((event) => events.push(event.type));
  transport.setDuration(10);
  transport.setLoop({ startSeconds: 2, endSeconds: 3 });
  transport.seek(2);
  transport.play();

  for (let repetition = 1; repetition <= 3; repetition += 1) {
    time.advance(1000);
    assert.equal(transport.positionSeconds(), 2);
    assert.equal(transport.repetitionCount, repetition);
  }
  assert.equal(events.filter((type) => type === "loop-wrap").length, 3);
});

test("loop catches up deterministically without accumulating frame deltas", () => {
  const time = clock();
  const transport = new Transport({ now: time.now });
  transport.setDuration(10);
  transport.setLoop({ startSeconds: 2, endSeconds: 3 });
  transport.seek(2);
  transport.play();
  time.advance(3500);

  assert.equal(transport.positionSeconds(), 2.5);
  assert.equal(transport.repetitionCount, 3);
});

test("target repetitions stop at the loop end", () => {
  const time = clock();
  const transport = new Transport({ now: time.now });
  transport.setDuration(10);
  transport.setLoop({ startSeconds: 2, endSeconds: 3, targetRepetitions: 3 });
  transport.seek(2);
  transport.play();
  time.advance(3000);

  assert.equal(transport.positionSeconds(), 3);
  assert.equal(transport.repetitionCount, 3);
  assert.equal(transport.playing, false);
});

test("pause inside a loop freezes the shared position", () => {
  const time = clock();
  const transport = new Transport({ now: time.now });
  transport.setDuration(10);
  transport.setLoop({ startSeconds: 2, endSeconds: 4 });
  transport.seek(2);
  transport.play();
  time.advance(500);
  transport.pause();
  time.advance(5000);
  assert.equal(transport.positionSeconds(), 2.5);
});

test("natural lesson completion stops and a new play restarts", () => {
  const time = clock();
  const transport = new Transport({ now: time.now });
  transport.setDuration(1);
  transport.play();
  time.advance(1000);
  assert.equal(transport.positionSeconds(), 1);
  assert.equal(transport.playing, false);
  transport.play();
  assert.equal(transport.positionSeconds(), 0);
});
