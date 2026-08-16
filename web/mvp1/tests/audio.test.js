import assert from "node:assert/strict";
import test from "node:test";

import { AudioReadiness, ReferenceSynth, VoiceRegistry } from "../audio.js";

class FakeParam {
  constructor() {
    this.value = 0;
    this.calls = [];
  }
  cancelScheduledValues(...args) { this.calls.push(["cancel", ...args]); }
  setValueAtTime(...args) { this.calls.push(["set", ...args]); }
  linearRampToValueAtTime(...args) { this.calls.push(["linear", ...args]); }
  exponentialRampToValueAtTime(...args) { this.calls.push(["exponential", ...args]); }
}

class FakeNode {
  constructor() { this.connections = []; }
  connect(node) { this.connections.push(node); }
}

class FakeOscillator extends FakeNode {
  constructor() {
    super();
    this.frequency = new FakeParam();
    this.starts = [];
    this.stops = [];
    this.listeners = new Map();
  }
  start(when) { this.starts.push(when); }
  stop(when) { this.stops.push(when); }
  addEventListener(type, listener) { this.listeners.set(type, listener); }
}

class FakeGain extends FakeNode {
  constructor() { super(); this.gain = new FakeParam(); }
}

class FakeContext {
  constructor(state = "running") {
    this.state = state;
    this.currentTime = 2;
    this.destination = {};
    this.oscillators = [];
    this.gains = [];
  }
  createOscillator() {
    const oscillator = new FakeOscillator();
    this.oscillators.push(oscillator);
    return oscillator;
  }
  createGain() {
    const gain = new FakeGain();
    this.gains.push(gain);
    return gain;
  }
  async resume() { this.state = "running"; }
}

const note = { eventId: "note-1", midiNote: 69, velocity: 64 };

test("audio readiness initializes and resumes only through explicit activation", async () => {
  const context = new FakeContext("suspended");
  const synth = new ReferenceSynth({ contextFactory: () => context });
  assert.equal(synth.readiness, AudioReadiness.UNINITIALIZED);
  await synth.initialize();
  assert.equal(synth.readiness, AudioReadiness.READY);
  assert.equal(context.state, "running");
});

test("initialization failure is explicit", async () => {
  const synth = new ReferenceSynth({ contextFactory: () => { throw new Error("blocked"); } });
  await assert.rejects(synth.initialize(), /blocked/);
  assert.equal(synth.readiness, AudioReadiness.FAILED);
});

test("reference synth schedules pitch, velocity envelope, and release", async () => {
  const context = new FakeContext();
  const synth = new ReferenceSynth({ contextFactory: () => context });
  await synth.initialize();
  const voiceId = synth.scheduleNote(note, 3, 4);
  const oscillator = context.oscillators[0];
  const voiceGain = context.gains[1];

  assert.equal(voiceId, "note-1:0");
  assert.equal(oscillator.frequency.value, 440);
  assert.deepEqual(oscillator.starts, [3]);
  assert.deepEqual(oscillator.stops, [4.05]);
  assert.ok(voiceGain.gain.calls.some((call) => call[0] === "linear" && call[1] === 64 / 127));
});

test("microtonal cents adjust pitch without any rate input", async () => {
  const context = new FakeContext();
  const synth = new ReferenceSynth({ contextFactory: () => context });
  await synth.initialize();
  synth.scheduleNote({ ...note, centsOffset: 100 }, 3, 4);
  assert.ok(Math.abs(context.oscillators[0].frequency.value - 466.1637615) < 0.0001);
});

test("volume, mute, silent velocity, and validation are deterministic", async () => {
  const context = new FakeContext();
  const synth = new ReferenceSynth({ contextFactory: () => context });
  await synth.initialize();
  synth.setVolume(0.25);
  assert.equal(synth.masterGain.gain.value, 0.25);
  synth.setMuted(true);
  assert.equal(synth.masterGain.gain.value, 0);
  assert.equal(synth.scheduleNote({ ...note, velocity: 0 }, 3, 4), null);
  assert.throws(() => synth.setVolume(2), /volume/);
  assert.throws(() => synth.scheduleNote(note, 4, 3), /release/);
});

test("panic and voice stealing leave the registry reliable", async () => {
  const context = new FakeContext();
  const synth = new ReferenceSynth({ contextFactory: () => context, maxVoices: 8 });
  await synth.initialize();
  for (let index = 0; index < 9; index += 1) {
    synth.scheduleNote({ ...note, eventId: `note-${index}` }, 3, 4);
  }
  assert.equal(synth.registry.size, 8);
  assert.equal(context.oscillators[0].stops.includes(0), true);
  synth.panic();
  assert.equal(synth.registry.size, 0);
  assert.equal(context.oscillators.at(-1).stops.includes(2), true);
});

test("voice registry enforces supported polyphony", () => {
  assert.throws(() => new VoiceRegistry(7), /at least 8/);
});
