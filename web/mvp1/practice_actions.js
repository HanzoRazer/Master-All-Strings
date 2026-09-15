/** Apply Educational next actions onto the existing practice shell. */

export class PracticeActionController {
  /**
   * @param {object} options
   * @param {object} options.transport sole musical transport authority
   * @param {(message: string) => void} [options.onStatus]
   * @param {(startTick: number, endTick: number) => ({startSeconds: number, endSeconds: number}|null)} [options.resolveFocusRange]
   *   DO-012: converts an Educational focus range into shared-transport
   *   seconds using the Core-authored anchor table. Absent means no anchors are
   *   available, and the loop is reported rather than applied.
   * @param {() => (number|null)} [options.targetRepetitions]
   */
  constructor({ transport, onStatus, resolveFocusRange, targetRepetitions } = {}) {
    this.transport = transport;
    this.onStatus = onStatus || (() => {});
    this.resolveFocusRange = resolveFocusRange || null;
    this.targetRepetitions = targetRepetitions || (() => null);
  }

  async apply(action, api) {
    if (!action) return null;
    const result = await api.applyAction({
      action_type: action.action_type,
      target_rate: action.target_rate,
      focus_start_tick: action.focus_start_tick,
      focus_end_tick: action.focus_end_tick,
      message_key: action.message_key,
    });
    if (action.action_type === "slow_down") {
      this.applySlowDown(action);
    } else if (action.action_type === "isolate_passage") {
      this.applyIsolatePassage(action);
    } else if (action.action_type === "repeat") {
      this.onStatus("Repeat the passage");
    } else if (action.action_type === "continue") {
      this.onStatus("Continue — no immediate repetition required under this policy");
    }
    return result;
  }

  /**
   * Runtime-only SLOW_DOWN. Uses the Educational target_rate as given.
   * Does not choose a slower rate and does not record guided-session evidence.
   *
   * @returns {boolean} whether Transport.setRate actually ran
   */
  applySlowDown(action) {
    if (action?.target_rate == null) {
      this.onStatus("Slow down (missing target_rate; rate not applied)");
      return false;
    }
    try {
      this.transport.setRate(Number(action.target_rate));
    } catch (error) {
      this.onStatus(`Slow down (${error.message})`);
      return false;
    }
    this.onStatus(`Slow down to ${action.target_rate}×`);
    return true;
  }

  /**
   * Turn ISOLATE_PASSAGE into an actual practice loop.
   *
   * The Educational Engine already chose the passage and reported authoritative
   * focus ticks; before DO-012 nothing consumed them as a loop, so the action
   * printed a status line and set a visual focus range. This adapter closes
   * that seam. It converts the unit and applies the existing
   * Transport.setLoop -- it does not widen, snap, or reinterpret the range, and
   * it makes no Educational decision of its own.
   *
   * @returns {boolean} whether a loop was actually applied
   */
  applyIsolatePassage(action) {
    const startTick = action.focus_start_tick;
    const endTick = action.focus_end_tick;
    const ticksLabel = `ticks ${startTick}–${endTick}`;

    if (startTick == null || endTick == null || endTick <= startTick) {
      // An action with no usable range is reported, not guessed at.
      this.onStatus(`Isolate passage ${ticksLabel}`);
      return false;
    }
    if (!this.resolveFocusRange) {
      this.onStatus(`Isolate passage ${ticksLabel} (no timeline anchors; loop not applied)`);
      return false;
    }

    const range = this.resolveFocusRange(startTick, endTick);
    if (!range) {
      this.onStatus(`Isolate passage ${ticksLabel} (range unresolved; loop not applied)`);
      return false;
    }

    const duration = this.transport.durationSeconds;
    const startSeconds = Math.max(0, range.startSeconds);
    // A focus range may end exactly at, or a rounding step past, the lesson end.
    // Clamping keeps a legitimate final-bar passage loopable instead of
    // rejecting it outright.
    const endSeconds = duration > 0 ? Math.min(range.endSeconds, duration) : range.endSeconds;
    if (!(endSeconds > startSeconds)) {
      this.onStatus(`Isolate passage ${ticksLabel} (range too short to loop)`);
      return false;
    }

    try {
      this.transport.setLoop({
        startSeconds,
        endSeconds,
        targetRepetitions: this.targetRepetitions(),
      });
    } catch (error) {
      // Transport validation is authoritative; a refused loop is reported.
      this.onStatus(`Isolate passage ${ticksLabel} (${error.message})`);
      return false;
    }
    this.onStatus(
      `Isolate passage ${ticksLabel} · looping ${startSeconds.toFixed(2)}s–${endSeconds.toFixed(2)}s`,
    );
    return true;
  }
}

export class LocalEducationApi {
  constructor(base = "/api/education") {
    this.base = base;
  }
  async call(path, body = {}) {
    const response = await fetch(`${this.base}/${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  }
  beginLesson = (x) => this.call("begin_lesson", x);
  evaluate = (x) => this.call("evaluate", x);
  get = () => this.call("get");
  session = () => this.call("session");
  applyAction = (x) => this.call("apply_action", x);
  goldenDemo = () => this.call("golden_demo");
}
