/**
 * Sole browser transport authority for visual and audible presentation.
 * Musical positions are anchor-derived and never accumulated from frame deltas.
 */

const VALID_RATES = new Set([0.5, 0.75, 1, 1.5]);

export class Transport {
  constructor({ now = () => performance.now() } = {}) {
    this._now = now;
    this.playing = false;
    this.baseSeconds = 0;
    this.anchorWallMs = null;
    this.playbackRate = 1;
    this.durationSeconds = 0;
    this.loop = null;
    this.repetitionCount = 0;
    this._listeners = new Set();
  }

  subscribe(listener) {
    if (typeof listener !== "function") {
      throw new TypeError("transport listener must be a function");
    }
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  snapshot(nowMs = this._now()) {
    return Object.freeze({
      playing: this.playing,
      positionSeconds: this.positionSeconds(nowMs),
      playbackRate: this.playbackRate,
      durationSeconds: this.durationSeconds,
      loop: this.loop ? Object.freeze({ ...this.loop }) : null,
      repetitionCount: this.repetitionCount,
    });
  }

  _emit(type, nowMs = this._now()) {
    const event = Object.freeze({ type, ...this.snapshot(nowMs) });
    this._listeners.forEach((listener) => listener(event));
  }

  setDuration(seconds, nowMs = this._now()) {
    const duration = Number(seconds);
    if (!Number.isFinite(duration) || duration < 0) {
      throw new RangeError("duration must be a non-negative finite number");
    }
    const position = this.positionSeconds(nowMs);
    this.durationSeconds = duration;
    this.baseSeconds = this._clamp(position);
    if (this.playing) this.anchorWallMs = nowMs;
    this._emit("duration", nowMs);
  }

  play(nowMs = this._now()) {
    if (this.playing) return false;
    if (this.durationSeconds > 0 && this.baseSeconds >= this.durationSeconds) {
      this.baseSeconds = this.loop?.enabled ? this.loop.startSeconds : 0;
    }
    this.playing = true;
    this.anchorWallMs = nowMs;
    this._emit("play", nowMs);
    return true;
  }

  pause(nowMs = this._now()) {
    if (!this.playing) return false;
    this.baseSeconds = this.positionSeconds(nowMs);
    this.playing = false;
    this.anchorWallMs = null;
    this._emit("pause", nowMs);
    return true;
  }

  restart(nowMs = this._now()) {
    this.playing = false;
    this.baseSeconds = 0;
    this.anchorWallMs = null;
    this.repetitionCount = 0;
    this._emit("restart", nowMs);
  }

  seek(seconds, nowMs = this._now()) {
    const next = Number(seconds);
    if (!Number.isFinite(next)) throw new RangeError("seek position must be finite");
    this.baseSeconds = this._clamp(next);
    if (this.playing) this.anchorWallMs = nowMs;
    this._emit("seek", nowMs);
  }

  setRate(rate, nowMs = this._now()) {
    const next = Number(rate);
    if (!VALID_RATES.has(next)) {
      throw new RangeError("rate must be one of 0.5, 0.75, 1, or 1.5");
    }
    if (this.playing) {
      this.baseSeconds = this.positionSeconds(nowMs);
      this.anchorWallMs = nowMs;
    }
    this.playbackRate = next;
    this._emit("rate", nowMs);
  }

  setLoop(loop, nowMs = this._now()) {
    const startSeconds = Number(loop?.startSeconds);
    const endSeconds = Number(loop?.endSeconds);
    if (
      !Number.isFinite(startSeconds) ||
      !Number.isFinite(endSeconds) ||
      startSeconds < 0 ||
      endSeconds <= startSeconds ||
      (this.durationSeconds > 0 && endSeconds > this.durationSeconds)
    ) {
      throw new RangeError("loop must satisfy 0 <= start < end <= duration");
    }
    this.loop = Object.freeze({
      enabled: loop.enabled !== false,
      startSeconds,
      endSeconds,
      targetRepetitions: loop.targetRepetitions ?? null,
    });
    this.repetitionCount = 0;
    this._emit("loop", nowMs);
  }

  clearLoop(nowMs = this._now()) {
    this.loop = null;
    this.repetitionCount = 0;
    this._emit("loop", nowMs);
  }

  positionSeconds(nowMs = this._now()) {
    if (!this.playing || this.anchorWallMs == null) return this._clamp(this.baseSeconds);
    const elapsed = ((nowMs - this.anchorWallMs) / 1000) * this.playbackRate;
    const rawPosition = this.baseSeconds + Math.max(0, elapsed);
    if (this.loop?.enabled && rawPosition >= this.loop.endSeconds) {
      return this._wrapLoop(rawPosition, nowMs);
    }
    return this._clamp(rawPosition);
  }

  _wrapLoop(rawPosition, nowMs) {
    const loopLength = this.loop.endSeconds - this.loop.startSeconds;
    const crossings = Math.floor((rawPosition - this.loop.endSeconds) / loopLength) + 1;
    const nextRepetition = this.repetitionCount + crossings;
    if (
      this.loop.targetRepetitions != null &&
      nextRepetition >= this.loop.targetRepetitions
    ) {
      this.repetitionCount = this.loop.targetRepetitions;
      this.baseSeconds = this.loop.endSeconds;
      this.playing = false;
      this.anchorWallMs = null;
      this._emit("loop-complete", nowMs);
      return this.baseSeconds;
    }
    this.repetitionCount = nextRepetition;
    this.baseSeconds =
      this.loop.startSeconds + ((rawPosition - this.loop.endSeconds) % loopLength);
    this.anchorWallMs = nowMs;
    this._emit("loop-wrap", nowMs);
    return this.baseSeconds;
  }

  _clamp(seconds) {
    const lower = Math.max(0, seconds);
    return this.durationSeconds > 0 ? Math.min(lower, this.durationSeconds) : lower;
  }
}

// Compatibility for callers and tests using the MVP-1F name.
export const PresentationTransport = Transport;
