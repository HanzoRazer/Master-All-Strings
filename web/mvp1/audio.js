/** Native Web Audio adapter. It owns voices, never musical timing or fingering. */

export const AudioReadiness = Object.freeze({
  UNINITIALIZED: "uninitialized",
  INITIALIZING: "initializing",
  READY: "ready",
  SUSPENDED: "suspended",
  FAILED: "failed",
});

export class VoiceRegistry {
  constructor(maxVoices = 16) {
    if (!Number.isInteger(maxVoices) || maxVoices < 8) {
      throw new RangeError("maxVoices must be an integer of at least 8");
    }
    this.maxVoices = maxVoices;
    this.voices = new Map();
  }

  register(id, voice) {
    while (this.voices.size >= this.maxVoices) {
      const oldestId = this.voices.keys().next().value;
      this.stop(oldestId);
    }
    this.voices.set(id, voice);
  }

  stop(id, when = 0) {
    const voice = this.voices.get(id);
    if (!voice) return false;
    this.voices.delete(id);
    try {
      voice.oscillator.stop(when);
    } catch {
      // A voice may already have ended; registry state is still authoritative.
    }
    return true;
  }

  remove(id) {
    this.voices.delete(id);
  }

  panic(when = 0) {
    [...this.voices.keys()].forEach((id) => this.stop(id, when));
  }

  get size() {
    return this.voices.size;
  }
}

function defaultContextFactory() {
  const Context = globalThis.AudioContext || globalThis.webkitAudioContext;
  if (!Context) throw new Error("Web Audio API is unavailable in this browser");
  return new Context();
}

function midiFrequency(midiNote, centsOffset = 0) {
  return 440 * 2 ** ((midiNote - 69 + centsOffset / 100) / 12);
}

export class ReferenceSynth {
  constructor({ contextFactory = defaultContextFactory, maxVoices = 16 } = {}) {
    this.contextFactory = contextFactory;
    this.context = null;
    this.masterGain = null;
    this.registry = new VoiceRegistry(maxVoices);
    this.readiness = AudioReadiness.UNINITIALIZED;
    this.failure = null;
    this.volume = 0.6;
    this.muted = false;
    this._voiceSequence = 0;
  }

  async initialize() {
    if (this.readiness === AudioReadiness.READY) return this.context;
    this.readiness = AudioReadiness.INITIALIZING;
    this.failure = null;
    try {
      if (!this.context) {
        this.context = this.contextFactory();
        this.masterGain = this.context.createGain();
        this.masterGain.connect(this.context.destination);
        this._applyVolume();
      }
      if (this.context.state === "suspended") {
        this.readiness = AudioReadiness.SUSPENDED;
        await this.context.resume();
      }
      if (this.context.state !== "running") {
        throw new Error(`Audio context is ${this.context.state}`);
      }
      this.readiness = AudioReadiness.READY;
      return this.context;
    } catch (error) {
      this.readiness = AudioReadiness.FAILED;
      this.failure = error;
      throw error;
    }
  }

  setVolume(value) {
    const next = Number(value);
    if (!Number.isFinite(next) || next < 0 || next > 1) {
      throw new RangeError("volume must be between 0 and 1");
    }
    this.volume = next;
    this._applyVolume();
  }

  setMuted(muted) {
    this.muted = Boolean(muted);
    this._applyVolume();
  }

  _applyVolume() {
    if (this.masterGain) this.masterGain.gain.value = this.muted ? 0 : this.volume;
  }

  scheduleNote(note, startAt, releaseAt) {
    if (this.readiness !== AudioReadiness.READY || !this.context || !this.masterGain) {
      throw new Error("Reference Synth is not ready");
    }
    if (!Number.isFinite(startAt) || !Number.isFinite(releaseAt) || releaseAt <= startAt) {
      throw new RangeError("scheduled note release must follow onset");
    }
    if (!Number.isInteger(note.midiNote) || note.midiNote < 0 || note.midiNote > 127) {
      throw new RangeError("scheduled MIDI note must be between 0 and 127");
    }
    if (!Number.isInteger(note.velocity) || note.velocity < 0 || note.velocity > 127) {
      throw new RangeError("scheduled velocity must be between 0 and 127");
    }
    if (note.velocity === 0) return null;

    const oscillator = this.context.createOscillator();
    const voiceGain = this.context.createGain();
    const voiceId = `${note.eventId}:${this._voiceSequence++}`;
    const peak = Math.max(0.0001, note.velocity / 127);
    oscillator.type = "triangle";
    oscillator.frequency.value = midiFrequency(note.midiNote, note.centsOffset ?? 0);
    voiceGain.gain.cancelScheduledValues(startAt);
    voiceGain.gain.setValueAtTime(0.0001, startAt);
    voiceGain.gain.linearRampToValueAtTime(peak, startAt + 0.012);
    voiceGain.gain.setValueAtTime(peak, releaseAt);
    voiceGain.gain.exponentialRampToValueAtTime(0.0001, releaseAt + 0.04);
    oscillator.connect(voiceGain);
    voiceGain.connect(this.masterGain);
    oscillator.addEventListener("ended", () => this.registry.remove(voiceId), { once: true });
    this.registry.register(voiceId, { oscillator, voiceGain, eventId: note.eventId });
    oscillator.start(startAt);
    oscillator.stop(releaseAt + 0.05);
    return voiceId;
  }

  panic() {
    this.registry.panic(this.context?.currentTime ?? 0);
  }
}
