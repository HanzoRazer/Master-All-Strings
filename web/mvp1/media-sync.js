/**
 * HTML media follower for the Teaching Timeline (DO-012 / MVP 2B).
 *
 * Turns derived timeline state into media-element commands, and reports how
 * well the element is actually keeping up. It never writes to the transport:
 * media follows music, not the other way round.
 *
 * The correction ladder mirrors `master_all_strings.presentation.synchronization`
 * and exists because the naive approach -- assigning `currentTime` every frame
 * to keep video glued to the transport -- produces visible stutter and audible
 * artifacts. Small drift is tolerated, medium drift is absorbed by nudging
 * `playbackRate`, and only large drift earns a hard seek.
 */

const SCHEMA_VERSION = "1.0.0";

export const DRIFT_SYNCED_THRESHOLD_MS = 40;
export const DRIFT_HARD_SEEK_THRESHOLD_MS = 150;

/**
 * After a hard seek the element needs time to actually get there. Measuring
 * during that window would read the pre-seek position and trigger another seek,
 * which is exactly the thrashing D12 forbids.
 */
export const HARD_SEEK_SETTLE_MS = 250;

/** How hard RESAMPLE nudges playback rate. Small enough to be imperceptible. */
const RESAMPLE_NUDGE = 0.05;

export const SyncMode = Object.freeze({
  DETACHED: "detached",
  SYNCHRONIZED: "synchronized",
});

export const SyncStatus = Object.freeze({
  SYNCED: "synced",
  DRIFTING: "drifting",
  CORRECTING: "correcting",
  DEGRADED: "degraded",
  DETACHED: "detached",
  UNAVAILABLE: "unavailable",
  OUT_OF_BINDING_RANGE: "out_of_binding_range",
});

export const SyncCorrection = Object.freeze({
  NONE: "none",
  RESAMPLE: "resample",
  HARD_SEEK: "hard_seek",
});

export function calculateDriftMs(expectedSeconds, actualSeconds) {
  return (actualSeconds - expectedSeconds) * 1000;
}

export function classifySyncHealth(driftMs) {
  const magnitude = Math.abs(driftMs);
  if (magnitude <= DRIFT_SYNCED_THRESHOLD_MS) return SyncStatus.SYNCED;
  if (magnitude <= DRIFT_HARD_SEEK_THRESHOLD_MS) return SyncStatus.DRIFTING;
  return SyncStatus.CORRECTING;
}

export function chooseSyncCorrection(driftMs) {
  const magnitude = Math.abs(driftMs);
  if (magnitude <= DRIFT_SYNCED_THRESHOLD_MS) return SyncCorrection.NONE;
  if (magnitude <= DRIFT_HARD_SEEK_THRESHOLD_MS) return SyncCorrection.RESAMPLE;
  return SyncCorrection.HARD_SEEK;
}

/**
 * Map lesson time to media time, or null outside the binding range.
 *
 * null is the explicit out-of-range answer. Extrapolating instead would let the
 * follower seek to a position the binding never claimed -- which is exactly how
 * a 3.0s clip would appear to keep answering for a 4.5s lesson.
 */
export function lessonTimeToMediaTime(binding, lessonSeconds) {
  if (!binding || binding.sync_mode !== SyncMode.SYNCHRONIZED) return null;
  if (lessonSeconds < binding.lesson_anchor_seconds) return null;
  if (
    binding.lesson_end_seconds !== null &&
    binding.lesson_end_seconds !== undefined &&
    lessonSeconds > binding.lesson_end_seconds
  ) {
    return null;
  }
  const mediaSeconds =
    binding.media_anchor_seconds + (lessonSeconds - binding.lesson_anchor_seconds);
  // The two ends are independently optional in MediaTimelineBindingV1, so a
  // binding may declare where the media stops without declaring where the lesson
  // stops. Checking only the lesson end would then walk the element straight
  // past the media end -- the 3.0s clip answering for a 4.5s lesson that the
  // out-of-range answer exists to prevent.
  if (
    binding.media_end_seconds !== null &&
    binding.media_end_seconds !== undefined &&
    mediaSeconds > binding.media_end_seconds
  ) {
    return null;
  }
  return mediaSeconds;
}

export class MediaSyncFollower {
  /**
   * @param {object} options
   * @param {string} options.id follower identity, used in health records
   * @param {() => (HTMLMediaElement|null)} options.getElement
   * @param {(health: object) => void} [options.onHealth]
   * @param {() => number} [options.now] injectable clock, for tests
   */
  constructor({ id = "media", getElement, onHealth, now } = {}) {
    if (typeof getElement !== "function") {
      throw new TypeError("MediaSyncFollower requires a getElement function");
    }
    this.id = id;
    this._getElement = getElement;
    this._onHealth = onHealth || (() => {});
    this._now = now || (() => (typeof performance !== "undefined" ? performance.now() : Date.now()));
    this.binding = null;
    this.mode = SyncMode.DETACHED;
    this.sequence = 0;
    this._settleUntilMs = null;
    this._lastHealth = null;
    this._hardSeekCount = 0;
  }

  /** Bind (or unbind) this follower. Passing null returns it to DETACHED. */
  setBinding(binding) {
    this.binding = binding || null;
    this.mode = binding?.sync_mode === SyncMode.SYNCHRONIZED
      ? SyncMode.SYNCHRONIZED
      : SyncMode.DETACHED;
    this._settleUntilMs = null;
    if (this.mode === SyncMode.DETACHED) {
      this._restoreDetachedRate();
    }
    return this.mode;
  }

  /**
   * Switch modes without discarding the binding, so the browser's Sync toggle
   * can flip back and forth. Returning to DETACHED must not touch the transport.
   */
  setMode(mode) {
    if (mode === SyncMode.SYNCHRONIZED && !this.binding) {
      // Refuse rather than infer: media with no binding cannot be synchronized.
      this.mode = SyncMode.DETACHED;
      return this.mode;
    }
    this.mode = mode === SyncMode.SYNCHRONIZED ? SyncMode.SYNCHRONIZED : SyncMode.DETACHED;
    this._settleUntilMs = null;
    if (this.mode === SyncMode.DETACHED) this._restoreDetachedRate();
    return this.mode;
  }

  onLesson() {
    this.binding = null;
    this.mode = SyncMode.DETACHED;
    this._settleUntilMs = null;
    this._lastHealth = null;
    this._hardSeekCount = 0;
  }

  onClear() {
    this.onLesson();
  }

  get hardSeekCount() {
    return this._hardSeekCount;
  }

  /** Latest health record, for diagnostics and browser smoke capture. */
  health() {
    return this._lastHealth;
  }

  onTimeline(state, reason) {
    if (!state) return null;
    const health = this._apply(state, reason);
    this._lastHealth = health;
    this._onHealth(health);
    return health;
  }

  _apply(state, reason) {
    if (this.mode !== SyncMode.SYNCHRONIZED || !this.binding) {
      return this._health(SyncStatus.DETACHED, null, null, null);
    }

    const element = this._getElement();
    if (!element) {
      // Missing media is a soft failure: the lesson stays usable.
      return this._health(SyncStatus.UNAVAILABLE, null, null, null);
    }

    const expected = lessonTimeToMediaTime(this.binding, state.position_seconds);
    if (expected === null) {
      // Past (or before) what the binding claims. Stop the element where it is
      // rather than extrapolating it into territory nobody declared.
      this._safePause(element);
      return this._health(
        SyncStatus.OUT_OF_BINDING_RANGE,
        null,
        this._readCurrentTime(element),
        null,
      );
    }

    if (this._isStalled(element)) {
      // The music continues; only the media is degraded.
      return this._health(SyncStatus.DEGRADED, expected, this._readCurrentTime(element), null);
    }

    const actual = this._readCurrentTime(element);
    if (actual === null) {
      return this._health(SyncStatus.UNAVAILABLE, expected, null, null);
    }

    this._followPlayState(element, state);

    const nowMs = this._now();
    if (this._settleUntilMs !== null && nowMs < this._settleUntilMs) {
      // A seek is still landing. Suppress new commands -- re-seeking an element
      // that is already on its way is the thrashing D12 forbids -- but report
      // what is actually measured rather than an unconditional CORRECTING.
      //
      // The status must stay measurement-derived. Reporting CORRECTING for the
      // whole window described the command we issued, not the element: once the
      // seek has landed the drift is zero and the record said otherwise, and
      // `last_correction: HARD_SEEK` was repeated every frame although only one
      // seek was ever issued.
      const settlingDriftMs = calculateDriftMs(expected, actual);
      const settlingStatus = classifySyncHealth(settlingDriftMs);
      if (settlingStatus === SyncStatus.SYNCED) {
        // Converged ahead of the deadline: end the window rather than staying
        // deaf to real drift for the rest of it.
        this._settleUntilMs = null;
      }
      return this._health(settlingStatus, expected, actual, SyncCorrection.NONE);
    }
    this._settleUntilMs = null;

    // Explicit repositioning events always earn a hard seek: after a seek or a
    // loop wrap the element is not "drifting", it is simply in the wrong place.
    const forcedSeek = reason === "seek" || reason === "loop-wrap" || reason === "restart";
    const seekable = this._canSeekTo(element, expected);

    if (forcedSeek) {
      if (!seekable) {
        // Nothing to be done: the element will not go where the lesson is.
        return this._health(SyncStatus.DEGRADED, expected, actual, null);
      }
      this._hardSeek(element, expected, state, nowMs);
      return this._health(SyncStatus.CORRECTING, expected, actual, SyncCorrection.HARD_SEEK);
    }

    const driftMs = calculateDriftMs(expected, actual);
    const correction = chooseSyncCorrection(driftMs);

    if (correction === SyncCorrection.HARD_SEEK) {
      if (!seekable) {
        // Reporting DEGRADED once beats re-issuing a seek the element ignores.
        return this._health(SyncStatus.DEGRADED, expected, actual, null);
      }
      this._hardSeek(element, expected, state, nowMs);
    } else if (correction === SyncCorrection.RESAMPLE) {
      // Nudge toward alignment: ahead means slow down, behind means speed up.
      const direction = driftMs > 0 ? -1 : 1;
      this._setRate(element, state.playback_rate * (1 + direction * RESAMPLE_NUDGE));
    } else {
      this._setRate(element, state.playback_rate);
    }

    return this._health(classifySyncHealth(driftMs), expected, actual, correction);
  }

  _followPlayState(element, state) {
    try {
      if (state.playing && element.paused) {
        const result = element.play();
        // A rejected play() (autoplay policy) must not throw into the timeline.
        if (result && typeof result.catch === "function") result.catch(() => {});
      } else if (!state.playing && !element.paused) {
        element.pause();
      }
    } catch (_) {
      /* media control failure is reported through health, never thrown */
    }
  }

  /**
   * Whether the element can actually be seeked to `seconds`.
   *
   * A media element can be fully buffered and still report an empty seekable
   * range -- the bundled DO-011 placeholder clip does exactly that. Seeking it
   * is a no-op, so without this check the follower would detect the same drift
   * and re-issue the same futile seek forever.
   */
  _canSeekTo(element, seconds) {
    const seekable = element.seekable;
    // A stub or an element that has not reported ranges yet: assume it can.
    if (!seekable || typeof seekable.length !== "number") return true;
    if (seekable.length === 0) return false;
    for (let index = 0; index < seekable.length; index += 1) {
      if (seconds >= seekable.start(index) && seconds <= seekable.end(index)) return true;
    }
    return false;
  }

  _hardSeek(element, expectedSeconds, state, nowMs) {
    try {
      element.currentTime = expectedSeconds;
      this._setRate(element, state.playback_rate);
      this._hardSeekCount += 1;
      this._settleUntilMs = nowMs + HARD_SEEK_SETTLE_MS;
    } catch (_) {
      /* an element that refuses a seek is reported, not thrown */
    }
  }

  _setRate(element, rate) {
    try {
      if (element.playbackRate !== rate) element.playbackRate = rate;
    } catch (_) {
      /* ignore */
    }
  }

  _restoreDetachedRate() {
    const element = this._getElement();
    if (!element) return;
    this._setRate(element, 1);
  }

  _safePause(element) {
    try {
      if (!element.paused) element.pause();
    } catch (_) {
      /* ignore */
    }
  }

  _readCurrentTime(element) {
    const value = element.currentTime;
    return Number.isFinite(value) ? value : null;
  }

  _isStalled(element) {
    // HAVE_CURRENT_DATA. Below this the element has no frame for its position.
    return typeof element.readyState === "number" && element.readyState < 2;
  }

  _health(status, expectedSeconds, actualSeconds, correction) {
    this.sequence += 1;
    const measured =
      status === SyncStatus.SYNCED ||
      status === SyncStatus.DRIFTING ||
      status === SyncStatus.CORRECTING;
    return Object.freeze({
      schema_version: SCHEMA_VERSION,
      follower_id: this.id,
      sequence: this.sequence,
      status,
      expected_time_seconds: expectedSeconds,
      actual_time_seconds: actualSeconds,
      // An unmeasurable status reports no drift rather than a comfortable zero:
      // "no measurement" and "perfectly in sync" are different claims.
      drift_ms: measured ? calculateDriftMs(expectedSeconds, actualSeconds) : null,
      last_correction: measured ? correction : null,
    });
  }
}
