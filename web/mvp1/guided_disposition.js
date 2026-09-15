/** Learner Accept/Decline for a guided-practice session (DO-015 Stage 5).

Records disposition only. Does not apply Educational actions, mutate
Transport, start recording, or advance the lesson.
*/

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
  }

  reset() {
    this.session = null;
    return this.session;
  }

  async syncFromEvaluation({ evaluation, guidance }) {
    if (!evaluation || !guidance) return null;
    if (!this.session) {
      this.session = await this.api.create({
        sessionId: this.newId(),
        attemptId: this.newId(),
        evaluation,
        guidance,
      });
      return this.session;
    }
    if (this.session.status === "AWAITING_ATTEMPT") {
      this.session = await this.api.append({
        sessionId: this.session.session_id,
        attemptId: this.newId(),
        evaluation,
        guidance,
      });
      return this.session;
    }
    return this.session;
  }

  async recordDisposition(disposition) {
    if (!canRecordDisposition(this.session)) return this.session;
    this.session = await this.api.recordDisposition(this.session.session_id, disposition);
    return this.session;
  }

  async recordExecution(executionStatus, executedAction) {
    if (!canApplyGuidedAction(this.session)) return this.session;
    this.session = await this.api.recordExecution(
      this.session.session_id,
      executionStatus,
      executedAction,
    );
    return this.session;
  }
}
