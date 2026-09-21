/** Learner Accept/Decline and session progression for a guided-practice
session (DO-015 Stages 5 and 7).

Records evidence and asks the Stage 4 API for lifecycle changes: it does not
decide them. It does not apply Educational actions, mutate Transport, start
recording, choose what to practice, or move the learner to another lesson --
the browser tells it a lesson change happened; the service decides what that
does to the session.
*/

/** Statuses after which no further attempt may be appended. */
export const TERMINAL_SESSION_STATUSES = Object.freeze([
  "CLOSED",
  "TRANSITIONED",
  "ABORTED",
]);

export function isTerminalSession(session) {
  return TERMINAL_SESSION_STATUSES.includes(session?.status);
}

/**
 * A guided-session progression failure that says what was left standing.
 *
 * `sessionPreserved` is the part callers must honour: a failed append or
 * transition leaves the last server-returned session exactly as it was, so the
 * caller must not discard recorded attempts to recover from it.
 */
export class GuidedProgressionError extends Error {
  constructor(message, { phase, sessionPreserved, cause = null } = {}) {
    super(message);
    this.name = "GuidedProgressionError";
    this.phase = phase;
    this.sessionPreserved = sessionPreserved;
    this.cause = cause;
  }
}

/**
 * Report the first pin the incoming evidence does not match, or null.
 *
 * The session is pinned to one assignment, content, and canonical revision.
 * Evidence from anywhere else is not this session's next attempt, and the
 * answer is to refuse it -- never to re-pin the session to the new evidence.
 */
export function guidedSessionPinMismatch(session, evaluation, guidance) {
  const pins = [
    ["assignment_id", session?.assignment_id, evaluation?.assignment_id],
    ["content_id", session?.content_id, evaluation?.content_id],
    [
      "canonical_revision_id",
      session?.canonical_revision_id,
      guidance?.canonical_revision_id,
    ],
  ];
  for (const [name, pinned, incoming] of pins) {
    if (pinned == null) continue;
    if (incoming !== pinned) return name;
  }
  return null;
}

export function currentAttempt(session) {
  if (!session?.attempts?.length) return null;
  const index = session.current_attempt_index;
  if (index == null) return session.attempts[session.attempts.length - 1];
  return session.attempts[index] ?? null;
}

export function currentAttemptAction(session) {
  return currentAttempt(session)?.action ?? null;
}

export function canRecordDisposition(session) {
  const action = currentAttemptAction(session);
  return Boolean(
    session &&
      session.status === "AWAITING_ACTION" &&
      action?.action_disposition === "PENDING",
  );
}

export function canApplyGuidedAction(session) {
  const action = currentAttemptAction(session);
  return Boolean(
    session &&
      action?.action_disposition === "ACCEPTED" &&
      action?.execution_status === "PENDING",
  );
}

export function dispositionControlState(session, executionDiagnostics = null) {
  const action = currentAttemptAction(session);
  const disposition = action?.action_disposition ?? null;
  const execution = action?.execution_status ?? null;
  const pending = canRecordDisposition(session);
  const acceptedPending = canApplyGuidedAction(session);
  const terminal = ["SUCCEEDED", "FAILED", "UNSUPPORTED"].includes(execution);
  const partial =
    executionDiagnostics?.runtimeStatus === "SUCCEEDED" &&
    executionDiagnostics?.evidenceStatus === "FAILED";
  const applying = executionDiagnostics?.phase === "applying";
  const applyEnabled = acceptedPending && !partial && !applying;
  let statusText = "";
  if (applying) {
    statusText = "Applying…";
  } else if (partial) {
    statusText = "Evidence recording failed";
  } else if (session && execution === "SUCCEEDED") {
    statusText = "Applied";
  } else if (session && execution === "FAILED") {
    statusText = "Execution failed";
  } else if (session && execution === "UNSUPPORTED") {
    statusText = "Unsupported";
  } else if (session && disposition === "ACCEPTED") {
    statusText = "Accepted — ready to apply";
  } else if (session && disposition === "DECLINED") {
    statusText = "Declined. The recommendation was not applied.";
  } else if (pending) {
    statusText =
      "Accept or decline this recommendation. Accepting does not apply it.";
  }
  return {
    acceptEnabled: pending,
    declineEnabled: pending,
    applyHidden: !(applyEnabled || terminal || partial || applying),
    applyDisabled: !applyEnabled,
    statusText,
    disposition,
    executionStatus: execution,
  };
}

export function applyDispositionControls(elements, session, executionDiagnostics = null) {
  const state = dispositionControlState(session, executionDiagnostics);
  if (elements.accept) {
    elements.accept.disabled = !state.acceptEnabled;
  }
  if (elements.decline) {
    elements.decline.disabled = !state.declineEnabled;
  }
  if (elements.apply) {
    elements.apply.hidden = state.applyHidden;
    elements.apply.disabled = state.applyDisabled;
  }
  if (elements.status) {
    elements.status.textContent = state.statusText;
    if (state.disposition) {
      elements.status.dataset.disposition = state.disposition;
    } else {
      delete elements.status.dataset.disposition;
    }
    if (state.executionStatus) {
      elements.status.dataset.execution = state.executionStatus;
    } else {
      delete elements.status.dataset.execution;
    }
  }
  return state;
}

export function createGuidanceDispositionHandler({
  guidedSessionApi,
  getSessionId,
  onResolved = null,
}) {
  return async (disposition) => {
    if (disposition !== "ACCEPTED" && disposition !== "DECLINED") return null;
    const sessionId =
      typeof getSessionId === "function" ? getSessionId() : getSessionId;
    if (!sessionId || !guidedSessionApi) return null;
    const session = await guidedSessionApi.recordDisposition(sessionId, disposition);
    if (typeof onResolved === "function") onResolved(disposition, session);
    return session;
  };
}

export class GuidedSessionController {
  /**
   * @param {object} options
   * @param {import("./guided_session_api.js").LocalGuidedSessionApi} options.api
   * @param {() => string} [options.newId]
   */
  constructor({ api, newId } = {}) {
    this.api = api;
    this.newId =
      newId ||
      (() => {
        if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
          return crypto.randomUUID();
        }
        throw new Error("opaque session/attempt ids must be supplied by the caller");
      });
    this.session = null;
    // The last session the server put beyond further attempts. Kept so a
    // transitioned lesson's history is not silently thrown away.
    this.terminalSession = null;
    this.lessonContext = null;
  }

  reset() {
    this.session = null;
    this.terminalSession = null;
    return this.session;
  }

  /**
   * Pin the controller to the lesson currently loaded in the browser.
   *
   * All three pins matter, and the canonical revision is the one that is easy
   * to leave out: a session belongs to the revision its evidence was evaluated
   * against, so the same assignment and content at a different revision is a
   * different lesson as far as this session is concerned.
   *
   * `canonicalRevisionId` is null while the loaded revision is still being
   * resolved. That is not "any revision will do" -- a session carrying a
   * revision cannot match an unresolved context, so it stays inert until the
   * revision is known to agree.
   */
  setLessonContext({ assignmentId, contentId, canonicalRevisionId = null } = {}) {
    this.lessonContext = { assignmentId, contentId, canonicalRevisionId };
    return this.lessonContext;
  }

  /**
   * The session that belongs to the lesson on screen, or null.
   *
   * `session` stays as the server last returned it; `activeSession` is what may
   * drive learner controls. They differ when a lesson switch could not be
   * transitioned, and when the lesson on screen is not the one the session was
   * recorded against: the record survives either way, but it acts on nothing.
   *
   * This is the same boundary the append path enforces, applied earlier. An
   * append against the wrong revision is refused by the service; a control the
   * learner can press against the wrong revision should never have been live.
   */
  get activeSession() {
    if (!this.session || !this.lessonContext) return this.session;
    const { assignmentId, contentId, canonicalRevisionId } = this.lessonContext;
    return this.session.assignment_id === assignmentId &&
      this.session.content_id === contentId &&
      (this.session.canonical_revision_id ?? null) === (canonicalRevisionId ?? null)
      ? this.session
      : null;
  }

  async syncFromEvaluation({ evaluation, guidance }) {
    if (!evaluation || !guidance) return null;
    if (!this.session) {
      try {
        this.session = await this.api.create({
          sessionId: this.newId(),
          attemptId: this.newId(),
          evaluation,
          guidance,
        });
      } catch (error) {
        // Nothing was recorded yet, so there is nothing to preserve.
        this.session = null;
        throw new GuidedProgressionError(
          error?.message || "guided session could not be created",
          { phase: "create", sessionPreserved: false, cause: error },
        );
      }
      return this.session;
    }
    const mismatch = guidedSessionPinMismatch(this.session, evaluation, guidance);
    if (mismatch) {
      throw new GuidedProgressionError(
        `guided session ${mismatch} does not match this evidence`,
        { phase: "append", sessionPreserved: true, cause: null },
      );
    }
    if (this.session.status === "AWAITING_ATTEMPT") {
      const preserved = this.session;
      try {
        this.session = await this.api.append({
          sessionId: this.session.session_id,
          attemptId: this.newId(),
          evaluation,
          guidance,
        });
      } catch (error) {
        // A rejected append is not history: the attempts the server already
        // holds stay exactly as they were.
        this.session = preserved;
        throw new GuidedProgressionError(
          error?.message || "guided attempt could not be appended",
          { phase: "append", sessionPreserved: true, cause: error },
        );
      }
      return this.session;
    }
    return this.session;
  }

  /**
   * End an open guided session because the learner changed lesson.
   *
   * The Stage 2 service performs the transition; this only asks for it. A
   * failure keeps the old session rather than discarding it, and the new
   * lesson gets no guided session here -- its first evaluated attempt creates
   * one.
   */
  async transitionForLessonChange({ nextAssignmentId, nextContentId, reason = null } = {}) {
    const session = this.session;
    if (!session) return null;
    if (
      session.assignment_id === nextAssignmentId &&
      session.content_id === nextContentId
    ) {
      return session;
    }
    if (isTerminalSession(session)) {
      this.terminalSession = session;
      this.session = null;
      return session;
    }
    let transitioned;
    try {
      transitioned = await this.api.transition({
        sessionId: session.session_id,
        nextAssignmentId,
        nextContentId,
        reason,
      });
    } catch (error) {
      throw new GuidedProgressionError(
        error?.message || "guided session could not be transitioned",
        { phase: "transition", sessionPreserved: true, cause: error },
      );
    }
    this.terminalSession = transitioned;
    this.session = null;
    return transitioned;
  }

  async recordDisposition(disposition) {
    // Through activeSession, so a session the loaded lesson does not own cannot
    // be answered here either. One rule about what may act, not two.
    const session = this.activeSession;
    if (!canRecordDisposition(session)) return this.session;
    this.session = await this.api.recordDisposition(session.session_id, disposition);
    return this.session;
  }

  async recordExecution(executionStatus, executedAction) {
    const session = this.activeSession;
    if (!canApplyGuidedAction(session)) return this.session;
    this.session = await this.api.recordExecution(
      session.session_id,
      executionStatus,
      executedAction,
    );
    return this.session;
  }
}
