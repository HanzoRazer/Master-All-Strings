/**
 * Wiring between the score views and the surfaces that already exist
 * (DO-013C Stage 6).
 *
 * This module holds no score state. It connects authorities that each already
 * own their piece:
 *
 *   canonical id -> coordinator's seek index -> Core-authored tick
 *                -> secondsAtTick(Core-authored anchors, tick)
 *                -> the existing Transport
 *
 * The unit conversion lives here rather than in `score-view.js` on purpose. The
 * seek index stores ticks and `Transport.seek` takes seconds, so something must
 * bridge them -- and the bridge is DO-012's `secondsAtTick`, which interpolates
 * within a table Musical Core authored rather than computing time itself.
 * Putting that call inside the coordinator would teach the score layer how
 * musical time works, which is the one thing it must not know.
 *
 * It exists as a module rather than as inline code in `app.js` so the wiring can
 * be tested in Node without a DOM.
 */

/**
 * Build the seek handler the coordinator calls when a score event is clicked.
 *
 * Receives a tick, never seconds. Returns the seconds actually sought, or null
 * when the timeline has no anchors to interpolate within -- a lesson without a
 * timeline still plays, and a click that cannot be honoured must do nothing
 * rather than guess a position.
 */
export function createScoreSeekHandler({ timeline, transport, secondsAtTick, onSeek = null }) {
  return (canonicalEventId, tick) => {
    if (!timeline?.ready || !Array.isArray(timeline.anchors)) return null;
    if (!Number.isFinite(tick)) return null;

    let seconds;
    try {
      seconds = secondsAtTick(timeline.anchors, tick);
    } catch {
      // An out-of-range tick is a bad click, not a broken lesson.
      return null;
    }
    transport.seek(seconds);
    if (typeof onSeek === "function") onSeek(canonicalEventId, tick, seconds);
    return seconds;
  };
}

/**
 * Forward a canonical event id from a fretboard click to the score views.
 *
 * Reads the id the fretboard already put in the DOM and passes it along. It
 * resolves nothing musical: an id that no score view can depict simply marks
 * nothing, which the coordinator already handles.
 */
export function createFretboardSelectionHandler({ coordinator, selector = ".note" }) {
  return (target) => {
    const element = target?.closest?.(selector);
    const canonicalEventId = element?.dataset?.eventId ?? null;
    if (!canonicalEventId) return null;
    coordinator.selectEvent(canonicalEventId);
    return canonicalEventId;
  };
}

/**
 * Observational score diagnostics.
 *
 * Every value is copied out. Nothing here is read back by a renderer, the
 * transport, the timeline, or the selection path -- diagnostics that could be
 * written to would be a control surface wearing an instrument's name.
 */
export function buildScoreDiagnostics({ coordinator, limitations = [], loopRange = null, repetitionIndex = null }) {
  const base = coordinator.diagnostics();
  return {
    status: base.status,
    reason: base.reason,
    canonicalRevisionId: base.canonicalRevisionId,
    tabLoaded: base.tabLoaded,
    notationLoaded: base.notationLoaded,
    activeEventIds: [...base.activeEventIds],
    tabActiveEventIds: [...base.tabActiveEventIds],
    notationActiveEventIds: [...base.notationActiveEventIds],
    selectedEventId: base.selectedEventId,
    lastSeekEventId: base.lastSeekEventId,
    lastSeekTick: base.lastSeekTick,
    tabDigest: base.tabDigest,
    notationDigest: base.notationDigest,
    tabError: base.tabError,
    notationError: base.notationError,
    loopRange: loopRange ? { ...loopRange } : null,
    repetitionIndex,
    limitations: [...limitations],
    guidanceStatus: base.guidanceStatus ?? "idle",
    guidanceDigest: base.guidanceDigest ?? null,
    guidedEventIds: [...(base.guidedEventIds ?? [])],
    tabGuidedEventIds: [...(base.tabGuidedEventIds ?? [])],
    notationGuidedEventIds: [...(base.notationGuidedEventIds ?? [])],
    guidanceAction: base.guidanceAction ?? null,
    guidanceRange: base.guidanceRange ? { ...base.guidanceRange } : null,
    guidanceError: base.guidanceError ?? null,
  };
}

/**
 * Present educational guidance on the score views.
 *
 * Display only. Transport is not mutated here; the learner must accept an
 * action through the existing practice-action controller.
 */
export function presentTeachingGuidance({ coordinator, renderer = null, projection = null }) {
  const applied = coordinator.applyGuidance(projection);
  if (renderer && typeof renderer.applyGuidedEventIds === "function") {
    renderer.applyGuidedEventIds(coordinator.guidedEventIds);
  }
  return applied;
}

/**
 * Explicit learner acceptance of the Educational next action.
 *
 * Showing guidance never calls this. The returned handler reuses the existing
 * practice-action / Transport seam and does not invent a clock or rate.
 */
export function createGuidanceAcceptHandler({ practiceActions, educationApi, onAccepted = null }) {
  return async (action) => {
    if (!action || !practiceActions || !educationApi) return null;
    const result = await practiceActions.apply(action, educationApi);
    if (typeof onAccepted === "function") onAccepted(action, result);
    return result;
  };
}
