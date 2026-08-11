/**
 * Presentation clock only. Musical timing arrives as seconds in the projection.
 * Position is always anchor-derived — never accumulated from frame deltas.
 */

export class PresentationTransport {
  constructor() {
    this.playing = false;
    this.baseSeconds = 0;
    this.anchorWallMs = null;
    this.playbackRate = 1;
    this.durationSeconds = 0;
  }

  setDuration(seconds) {
    this.durationSeconds = Math.max(0, Number(seconds) || 0);
  }

  play(nowMs = performance.now()) {
    if (this.playing) return;
    this.playing = true;
    this.anchorWallMs = nowMs;
  }

  pause(nowMs = performance.now()) {
    if (!this.playing) return;
    this.baseSeconds = this.positionSeconds(nowMs);
    this.playing = false;
    this.anchorWallMs = null;
  }

  restart() {
    this.playing = false;
    this.baseSeconds = 0;
    this.anchorWallMs = null;
  }

  seek(seconds) {
    const clamped = Math.min(Math.max(0, seconds), this.durationSeconds || seconds);
    this.baseSeconds = clamped;
    if (this.playing) {
      this.anchorWallMs = performance.now();
    }
  }

  setRate(rate, nowMs = performance.now()) {
    const next = Number(rate);
    if (!Number.isFinite(next) || next <= 0) return;
    if (this.playing) {
      this.baseSeconds = this.positionSeconds(nowMs);
      this.anchorWallMs = nowMs;
    }
    this.playbackRate = next;
  }

  positionSeconds(nowMs = performance.now()) {
    if (!this.playing || this.anchorWallMs == null) {
      return this.baseSeconds;
    }
    const elapsed = ((nowMs - this.anchorWallMs) / 1000) * this.playbackRate;
    const position = this.baseSeconds + elapsed;
    if (this.durationSeconds > 0) {
      return Math.min(position, this.durationSeconds);
    }
    return position;
  }
}
