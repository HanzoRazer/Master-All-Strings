/** Guided-practice attempt history (DO-015 Stage 7).

Presentation only. This module reads `session.attempts[]` -- the one guided
history there is -- and says what was recommended, what the learner chose, and
what executing it did. It holds no state, introduces no second history model,
and decides nothing: it does not reach Transport, evaluate a performance, build
guidance, choose an action, or append an attempt.

It also declines to read anything into the sequence. Later is not better, and
three attempts are not progress; the contract says what happened on each, and
that is all this renders.
*/

import { canApplyGuidedAction, canRecordDisposition } from "./guided_disposition.js";

const ACTION_LABELS = {
  slow_down: "Slow down",
  isolate_passage: "Isolate passage",
  repeat: "Repeat",
  continue: "Continue",
  view_one_string: "One-string view",
  enable_zone_view: "Zone view",
};

const DISPOSITION_LABELS = {
  PENDING: "Not answered yet",
  ACCEPTED: "Accepted",
  DECLINED: "Declined",
};

const EXECUTION_LABELS = {
  NOT_REQUESTED: "Not applied",
  PENDING: "Ready to apply",
  SUCCEEDED: "Applied",
  FAILED: "Execution failed",
  UNSUPPORTED: "Not supported yet",
};

/** The label a learner reads. Identity stays with `attempt_id`. */
export function formatGuidedAttemptNumber(index) {
  return `Attempt ${index + 1}`;
}

function actionLabel(actionType) {
  if (!actionType) return "None recorded";
  return ACTION_LABELS[actionType] || actionType;
}

/**
 * The attempts in the order the session recorded them.
 *
 * Never sorted: array order is the authoritative sequence, and
 * `current_attempt_index` -- not "the last one" -- says which attempt is
 * current.
 */
export function guidedAttemptRows(session) {
  const attempts = session?.attempts ?? [];
  const currentIndex = session?.current_attempt_index ?? null;
  // Lifecycle decides whether the current attempt can still be acted on; an
  // attempt in a closed or transitioned session is history like the rest.
  const live = canRecordDisposition(session) || canApplyGuidedAction(session);
  return attempts.map((attempt, index) => {
    const action = attempt?.action ?? null;
    const isCurrent = currentIndex === index;
    return {
      index,
      attemptId: attempt?.attempt_id ?? null,
      label: formatGuidedAttemptNumber(index),
      isCurrent,
      isHistorical: !isCurrent,
      actionable: isCurrent && live,
      actionType: action?.recommended_action?.action_type ?? null,
      recommendationText: actionLabel(action?.recommended_action?.action_type),
      disposition: action?.action_disposition ?? null,
      dispositionText: DISPOSITION_LABELS[action?.action_disposition] || "Not answered yet",
      execution: action?.execution_status ?? null,
      executionText: EXECUTION_LABELS[action?.execution_status] || "Not applied",
      performanceSessionId: attempt?.performance_session_id ?? null,
    };
  });
}

export function isHistoricalGuidedAttempt(session, attemptId) {
  const row = guidedAttemptRows(session).find((item) => item.attemptId === attemptId);
  return row ? row.isHistorical : false;
}

export function getCurrentGuidedAttemptRow(session) {
  return guidedAttemptRows(session).find((row) => row.isCurrent) ?? null;
}

function line(className, text) {
  const node = document.createElement("p");
  node.className = className;
  node.textContent = text;
  return node;
}

/**
 * Render the guided-session history into `container`.
 *
 * `appendError` is the attempt that was played but not recorded. It is shown as
 * exactly that -- an attempt missing from the record -- rather than being drawn
 * into the list as though the server had accepted it.
 */
export function renderGuidedSessionHistory({ session, container, appendError = null } = {}) {
  if (!container) return null;
  container.replaceChildren();
  const rows = guidedAttemptRows(session);
  container.dataset.attemptCount = String(rows.length);
  if (session?.session_id) container.dataset.sessionId = session.session_id;
  else delete container.dataset.sessionId;
  if (session?.status) container.dataset.sessionStatus = session.status;
  else delete container.dataset.sessionStatus;

  if (!rows.length) {
    container.append(line("hint subtle", "No guided attempts yet."));
  } else {
    const heading = document.createElement("h3");
    heading.textContent = "Guided practice";
    container.append(heading);
    const list = document.createElement("ol");
    list.className = "guided-history";
    for (const row of rows) {
      const item = document.createElement("li");
      item.className = row.isCurrent ? "guided-attempt current" : "guided-attempt";
      item.dataset.attemptIndex = String(row.index);
      if (row.attemptId) item.dataset.attemptId = row.attemptId;
      item.dataset.current = String(row.isCurrent);
      item.dataset.actionable = String(row.actionable);
      if (row.actionType) item.dataset.action = row.actionType;
      if (row.disposition) item.dataset.disposition = row.disposition;
      if (row.execution) item.dataset.execution = row.execution;
      item.append(
        line(
          "guided-attempt-label",
          row.isCurrent ? `${row.label} — Current` : row.label,
        ),
        line("guided-attempt-recommendation", `Recommendation: ${row.recommendationText}`),
        line("guided-attempt-disposition", `Learner: ${row.dispositionText}`),
        line("guided-attempt-execution", `Execution: ${row.executionText}`),
      );
      list.append(item);
    }
    container.append(list);
  }

  if (appendError) {
    const notice = line(
      "guided-history-error",
      appendError.error || "This attempt was not recorded in the guided session.",
    );
    notice.dataset.appendStatus = appendError.status || "FAILED";
    if (appendError.phase) notice.dataset.progressionPhase = appendError.phase;
    container.dataset.appendStatus = appendError.status || "FAILED";
    container.append(notice);
  } else {
    delete container.dataset.appendStatus;
  }
  return container;
}
