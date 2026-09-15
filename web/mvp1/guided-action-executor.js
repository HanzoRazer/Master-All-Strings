/** Runtime adapter for accepted guided-practice actions (DO-015 Stage 6).

Validates the ACCEPTED / PENDING precondition, dispatches the session's
authoritative recommended action onto existing Transport / isolate seams, and
returns a normalized execution result. Persistence stays with the Stage 4 API.
This module does not choose Educational actions, accept recommendations, or
own guided-session lifecycle.
*/

import {
  canApplyGuidedAction,
  currentAttemptAction,
} from "./guided_disposition.js";

export const UNSUPPORTED_GUIDED_ACTIONS = Object.freeze([
  "view_one_string",
  "enable_zone_view",
]);

const UNSUPPORTED = new Set(UNSUPPORTED_GUIDED_ACTIONS);

function failed(executedAction, error) {
  return {
    status: "FAILED",
    executedAction: executedAction ?? null,
    error: error || "execution failed",
  };
}

function succeeded(executedAction) {
  return { status: "SUCCEEDED", executedAction, error: null };
}

function executeSlowDown(action, { transport, applySlowDown }) {
  if (action.target_rate == null) {
    return failed(action, "SLOW_DOWN is missing target_rate; no rate was invented");
  }
  if (typeof applySlowDown === "function") {
    const applied = applySlowDown(action);
    if (!applied) return failed(action, "SLOW_DOWN runtime seam did not apply");
    return succeeded(action);
  }
  if (!transport || typeof transport.setRate !== "function") {
    return failed(action, "SLOW_DOWN requires the existing Transport rate seam");
  }
  transport.setRate(Number(action.target_rate));
  return succeeded(action);
}

function executeIsolatePassage(action, { applyIsolatePassage }) {
  if (action.focus_start_tick == null || action.focus_end_tick == null) {
    return failed(
      action,
      "ISOLATE_PASSAGE is missing focus ticks; no range was derived",
    );
  }
  if (typeof applyIsolatePassage !== "function") {
    return failed(action, "ISOLATE_PASSAGE requires the existing isolate runtime seam");
  }
  const applied = applyIsolatePassage(action);
  if (!applied) return failed(action, "ISOLATE_PASSAGE runtime seam did not apply");
  return succeeded(action);
}

function executeRepeat(action, { transport, capture }) {
  // Readiness only: do not change rate/loop or start recording.
  void transport;
  if (capture && typeof capture.startAttempt === "function") {
    // Presence of capture is observational. REPEAT must not invoke it.
  }
  return succeeded(action);
}

function executeContinue(action) {
  // Closure is a Stage 2 lifecycle fact recorded after runtime success.
  return succeeded(action);
}

/**
 * Dispatch one accepted primary recommendation onto existing runtime seams.
 *
 * @param {object} options
 * @param {object} options.session authoritative guided session
 * @param {object} [options.action] must match the session recommendation when supplied
 * @param {object} [options.transport]
 * @param {(action: object) => boolean} [options.applySlowDown]
 * @param {(action: object) => boolean} [options.applyIsolatePassage]
 * @param {object} [options.capture]
 */
export function executeGuidedAction({
  session,
  action = null,
  transport = null,
  applySlowDown = null,
  applyIsolatePassage = null,
  capture = null,
} = {}) {
  if (!canApplyGuidedAction(session)) {
    return failed(null, "execution requires ACCEPTED disposition and PENDING execution");
  }
  const recommended = currentAttemptAction(session)?.recommended_action;
  if (!recommended?.action_type) {
    return failed(null, "session has no recommended action");
  }
  if (action && action.action_type !== recommended.action_type) {
    return failed(null, "executed action_type must match the recommended action");
  }
  const toExecute = recommended;
  const type = toExecute.action_type;
  if (UNSUPPORTED.has(type)) {
    return { status: "UNSUPPORTED", executedAction: null, error: null };
  }
  try {
    if (type === "slow_down") {
      return executeSlowDown(toExecute, { transport, applySlowDown });
    }
    if (type === "isolate_passage") {
      return executeIsolatePassage(toExecute, { applyIsolatePassage });
    }
    if (type === "repeat") {
      return executeRepeat(toExecute, { transport, capture });
    }
    if (type === "continue") {
      return executeContinue(toExecute);
    }
    return failed(toExecute, `unknown action_type ${type}`);
  } catch (error) {
    return failed(toExecute, error?.message || String(error));
  }
}

export function applyControlState(session, executionDiagnostics = null) {
  const action = currentAttemptAction(session);
  const acceptedPending = canApplyGuidedAction(session);
  const execution = action?.execution_status ?? null;
  const terminal = ["SUCCEEDED", "FAILED", "UNSUPPORTED"].includes(execution);
  const partial =
    executionDiagnostics?.runtimeStatus === "SUCCEEDED" &&
    executionDiagnostics?.evidenceStatus === "FAILED";
  const applying = executionDiagnostics?.phase === "applying";
  const applyEnabled = acceptedPending && !partial && !applying;
  return {
    applyHidden: !(applyEnabled || terminal || partial || applying),
    applyDisabled: !applyEnabled,
    applying,
    partialSuccess: Boolean(partial),
  };
}

function attemptKey(session) {
  const attempt = session?.attempts?.[session.current_attempt_index ?? 0];
  if (!session?.session_id || !attempt?.attempt_id) return null;
  return `${session.session_id}:${attempt.attempt_id}`;
}

/**
 * Apply click orchestration: runtime first, then Stage 4 execution evidence.
 *
 * A runtime success that cannot be recorded is a partial success. The local
 * session stays at the pre-execution server state, Apply is locked for this
 * attempt, and the runtime action is not retried automatically.
 */
export function createGuidedApplyHandler({
  getSession,
  setSession = null,
  execute = executeGuidedAction,
  recordExecution,
  getRuntime = () => ({}),
  onDiagnostics = null,
  onResolved = null,
} = {}) {
  let inFlight = false;
  const runtimeSucceededWithoutEvidence = new Set();

  return async () => {
    const session = typeof getSession === "function" ? getSession() : getSession;
    const key = attemptKey(session);
    if (!canApplyGuidedAction(session) || inFlight) return null;
    if (key && runtimeSucceededWithoutEvidence.has(key)) return null;

    const action = currentAttemptAction(session).recommended_action;
    inFlight = true;
    onDiagnostics?.({
      phase: "applying",
      requestedAction: action.action_type,
      runtimeStatus: null,
      evidenceStatus: null,
      error: null,
    });

    const runtime = execute({
      session,
      action,
      ...((typeof getRuntime === "function" ? getRuntime() : getRuntime) || {}),
    });

    onDiagnostics?.({
      phase: "recording",
      requestedAction: action.action_type,
      runtimeStatus: runtime.status,
      evidenceStatus: "PENDING",
      error: runtime.error,
    });

    try {
      const executedAction =
        runtime.status === "UNSUPPORTED" ? null : (runtime.executedAction ?? action);
      const updated = await recordExecution(
        session.session_id,
        runtime.status,
        executedAction,
      );
      if (typeof setSession === "function") setSession(updated);
      onDiagnostics?.({
        phase: "complete",
        requestedAction: action.action_type,
        runtimeStatus: runtime.status,
        evidenceStatus: "SUCCEEDED",
        error: runtime.error,
      });
      if (typeof onResolved === "function") onResolved(updated, runtime);
      return updated;
    } catch (error) {
      if (runtime.status === "SUCCEEDED" && key) {
        runtimeSucceededWithoutEvidence.add(key);
      }
      onDiagnostics?.({
        phase: "complete",
        requestedAction: action.action_type,
        runtimeStatus: runtime.status,
        evidenceStatus: "FAILED",
        error: error?.message || String(error),
      });
      return null;
    } finally {
      inFlight = false;
    }
  };
}
