/**
 * Teaching Timeline coordinator (DO-012 / MVP 2B).
 *
 * Observes the one musical transport and distributes derived state to
 * followers. It holds no timer, no interval, and no position of its own: every
 * value it reports is read from `Transport` at the moment it is asked.
 *
 * Ticks come from a Python-authored anchor table rather than a tick converter
 * implemented here. Musical Core owns tick-to-second conversion; a second
 * implementation in JavaScript would be free to drift from the first. Between
 * two anchors the tempo is constant by construction, so interpolating within
 * the table reproduces the canonical mapping rather than approximating it.
 *
 * Mirrors `master_all_strings.presentation.timeline`. The Python module is the
 * normative reference; these functions must stay arithmetically identical to it.
 */

const SCHEMA_VERSION = "1.0.0";

/** Match Musical Core's rounding rule, not JavaScript's Math.round. */
export function roundHalfAwayFromZero(value) {
  if (!Number.isFinite(value)) {
    throw new RangeError("value must be finite");
  }
  return value >= 0 ? Math.floor(value + 0.5) : -Math.floor(-value + 0.5);
}

function requireAnchorTable(anchors) {
  if (!Array.isArray(anchors) || anchors.length === 0) {
    throw new RangeError("anchor table must not be empty");
  }
  if (anchors[0].tick !== 0) {
    throw new RangeError("anchor table must begin at tick 0");
  }
  for (let index = 1; index < anchors.length; index += 1) {
    const previous = anchors[index - 1];
    const current = anchors[index];
    if (!(current.tick > previous.tick)) {
      throw new RangeError("anchor ticks must be strictly increasing");
    }
    if (current.seconds < previous.seconds) {
      throw new RangeError("anchor seconds must be non-decreasing");
    }
  }
  return anchors;
}

function interpolate(value, lowerIn, upperIn, lowerOut, upperOut) {
  if (upperIn === lowerIn) return lowerOut;
  const ratio = (value - lowerIn) / (upperIn - lowerIn);
  return lowerOut + ratio * (upperOut - lowerOut);
}

function finalSegment(table) {
  // A single-anchor table has no slope; treat it as its own segment so
  // extrapolation degenerates to the anchor value instead of dividing by zero.
  if (table.length < 2) return [table[0], table[0]];
  return [table[table.length - 2], table[table.length - 1]];
}

/** Seconds at `tick`. Past the last anchor, continue at the final rate. */
export function secondsAtTick(anchors, tick) {
  const table = requireAnchorTable(anchors);
  if (!Number.isFinite(tick) || tick < 0) {
    throw new RangeError("tick must be a nonnegative finite number");
  }
  if (tick <= table[0].tick) return table[0].seconds;
  for (let index = 0; index < table.length - 1; index += 1) {
    const lower = table[index];
    const upper = table[index + 1];
    if (tick <= upper.tick) {
      return interpolate(tick, lower.tick, upper.tick, lower.seconds, upper.seconds);
    }
  }
  const [lower, upper] = finalSegment(table);
  if (upper.tick === lower.tick) return upper.seconds;
  const rate = (upper.seconds - lower.seconds) / (upper.tick - lower.tick);
  return upper.seconds + (tick - upper.tick) * rate;
}

/** Tick at `seconds`, rounded the way Musical Core rounds. */
export function tickAtSeconds(anchors, seconds) {
  const table = requireAnchorTable(anchors);
  if (!Number.isFinite(seconds) || seconds < 0) {
    throw new RangeError("seconds must be a nonnegative finite number");
  }
  if (seconds <= table[0].seconds) return table[0].tick;
  for (let index = 0; index < table.length - 1; index += 1) {
    const lower = table[index];
    const upper = table[index + 1];
    if (seconds <= upper.seconds) {
      if (upper.seconds === lower.seconds) return lower.tick;
      return roundHalfAwayFromZero(
        interpolate(seconds, lower.seconds, upper.seconds, lower.tick, upper.tick),
      );
    }
  }
  const [lower, upper] = finalSegment(table);
  if (upper.seconds === lower.seconds || upper.tick === lower.tick) return upper.tick;
  const rate = (upper.tick - lower.tick) / (upper.seconds - lower.seconds);
  return roundHalfAwayFromZero(upper.tick + (seconds - upper.seconds) * rate);
}

/**
 * Convert an Educational focus range into shared-transport loop seconds.
 *
 * The ticks come from PracticeNextActionV1 and are already authoritative. This
 * only changes their unit so the existing Transport.setLoop can accept them;
 * it does not widen, snap, or reinterpret the range.
 */
export function resolveFocusRangeSeconds(anchors, startTick, endTick) {
  if (!Number.isInteger(startTick) || !Number.isInteger(endTick)) {
    throw new RangeError("focus ticks must be integers");
  }
  if (endTick <= startTick) {
    throw new RangeError("focus end_tick must exceed start_tick");
  }
  return {
    startSeconds: secondsAtTick(anchors, startTick),
    endSeconds: secondsAtTick(anchors, endTick),
  };
}

export class TeachingTimeline {
  /**
   * @param {object} options
   * @param {object} options.transport sole musical transport authority
   */
  constructor({ transport }) {
    if (!transport || typeof transport.snapshot !== "function") {
      throw new TypeError("TeachingTimeline requires the shared Transport");
    }
    this.transport = transport;
    this.lessonId = null;
    this.anchors = null;
    this.sequence = 0;
    this._followers = new Map();
    this._activeEventIds = [];
    // One subscription to the transport, for the lifetime of the coordinator.
    this._unsubscribe = transport.subscribe((event) => this._onTransportEvent(event));
  }

  /**
   * Bind to a lesson. Clearing first is deliberate: stale anchors or follower
   * state from the previous lesson would silently mis-time the new one.
   */
  setLesson({ lessonId, anchors }) {
    this.clearLesson();
    if (!lessonId) throw new TypeError("lessonId is required");
    requireAnchorTable(anchors);
    this.lessonId = lessonId;
    this.anchors = anchors;
    this._followers.forEach((follower) => {
      if (typeof follower.onLesson === "function") {
        follower.onLesson({ lessonId, anchors });
      }
    });
    this.publish("lesson");
  }

  clearLesson() {
    this.lessonId = null;
    this.anchors = null;
    this.sequence = 0;
    this._activeEventIds = [];
    this._followers.forEach((follower) => {
      if (typeof follower.onClear === "function") follower.onClear();
    });
  }

  get ready() {
    return Boolean(this.lessonId && this.anchors);
  }

  /**
   * Register a follower. Followers receive derived state; none of them may
   * write back to the transport through this seam.
   */
  addFollower(follower) {
    if (!follower || typeof follower.id !== "string" || !follower.id) {
      throw new TypeError("a follower requires a string id");
    }
    this._followers.set(follower.id, follower);
    return () => this._followers.delete(follower.id);
  }

  removeFollower(id) {
    this._followers.delete(id);
  }

  /** Event IDs currently sounding, supplied by whoever knows (the projection). */
  setActiveEventIds(eventIds) {
    this._activeEventIds = Array.isArray(eventIds) ? [...eventIds] : [];
  }

  /** A TeachingTimelineStateV1-shaped snapshot of the shared transport. */
  timelineState(nowMs) {
    if (!this.ready) return null;
    const snapshot = this.transport.snapshot(nowMs);
    const loop = snapshot.loop;
    const loopEnabled = Boolean(loop && loop.enabled);
    return Object.freeze({
      schema_version: SCHEMA_VERSION,
      lesson_id: this.lessonId,
      sequence: this.sequence,
      position_tick: tickAtSeconds(this.anchors, snapshot.positionSeconds),
      position_seconds: snapshot.positionSeconds,
      playing: snapshot.playing,
      playback_rate: snapshot.playbackRate,
      loop_enabled: loopEnabled,
      repetition_index: snapshot.repetitionCount,
      // Bounds are present if and only if the loop is enabled: stale bounds
      // beside loop_enabled=false read as an active loop to a follower.
      loop_start_tick: loopEnabled ? tickAtSeconds(this.anchors, loop.startSeconds) : null,
      loop_end_tick: loopEnabled ? tickAtSeconds(this.anchors, loop.endSeconds) : null,
      loop_start_seconds: loopEnabled ? loop.startSeconds : null,
      loop_end_seconds: loopEnabled ? loop.endSeconds : null,
    });
  }

  /** A TeachingPlayheadStateV1-shaped projection of the current position. */
  playheadState(nowMs) {
    const state = this.timelineState(nowMs);
    if (!state) return null;
    // Deduplicate without reordering: identity is the projection's, and the
    // contract requires uniqueness.
    const seen = new Set();
    const activeEventIds = [];
    for (const eventId of this._activeEventIds) {
      if (typeof eventId === "string" && eventId && !seen.has(eventId)) {
        seen.add(eventId);
        activeEventIds.push(eventId);
      }
    }
    return Object.freeze({
      schema_version: SCHEMA_VERSION,
      lesson_id: state.lesson_id,
      sequence: state.sequence,
      position_tick: state.position_tick,
      position_seconds: state.position_seconds,
      active_event_ids: Object.freeze(activeEventIds),
      repetition_index: state.repetition_index,
    });
  }

  /**
   * Emit current state to every follower.
   *
   * Called from transport events and from the render loop. A follower that
   * throws is isolated: one broken surface must not stop the others, and must
   * never stop the music.
   */
  publish(reason, nowMs) {
    if (!this.ready) return null;
    this.sequence += 1;
    const timeline = this.timelineState(nowMs);
    const playhead = this.playheadState(nowMs);
    this._followers.forEach((follower) => {
      try {
        if (typeof follower.onTimeline === "function") {
          follower.onTimeline(timeline, reason);
        }
        if (typeof follower.onPlayhead === "function") {
          follower.onPlayhead(playhead, reason);
        }
      } catch (error) {
        if (typeof follower.onError === "function") {
          try {
            follower.onError(error);
          } catch (_) {
            /* a follower's own error handler must not escalate either */
          }
        }
      }
    });
    return { timeline, playhead };
  }

  _onTransportEvent(event) {
    this.publish(event.type);
  }

  /** Structured diagnostics for tests and browser smoke capture. */
  diagnostics(nowMs) {
    return {
      ready: this.ready,
      lessonId: this.lessonId,
      anchorCount: this.anchors ? this.anchors.length : 0,
      sequence: this.sequence,
      followers: [...this._followers.keys()].sort(),
      timeline: this.timelineState(nowMs),
      playhead: this.playheadState(nowMs),
    };
  }

  dispose() {
    if (this._unsubscribe) this._unsubscribe();
    this._unsubscribe = null;
    this._followers.clear();
  }
}
