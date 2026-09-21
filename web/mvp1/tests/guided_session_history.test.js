import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  formatGuidedAttemptNumber,
  getCurrentGuidedAttemptRow,
  guidedAttemptRows,
  isHistoricalGuidedAttempt,
  renderGuidedSessionHistory,
} from "../guided-session-history.js";
import { stubElement, withStubDocument } from "./dom_stub.js";

const repoUrl = (path) => fileURLToPath(new URL(path, import.meta.url));

function attempt(index, action, overrides = {}) {
  return {
    attempt_id: `attempt-${index}`,
    attempt_index: index,
    performance_session_id: `performance-${index}`,
    evaluation_digest: `sha256:eval-${index}`,
    guidance_digest: `sha256:guide-${index}`,
    action: {
      recommended_action: { action_type: "slow_down", target_rate: 0.75 },
      action_disposition: "PENDING",
      execution_status: "NOT_REQUESTED",
      executed_action: null,
      ...action,
    },
    ...overrides,
  };
}

const APPLIED = {
  action_disposition: "ACCEPTED",
  execution_status: "SUCCEEDED",
  executed_action: { action_type: "slow_down", target_rate: 0.75 },
};

function session(attempts, overrides = {}) {
  return {
    session_id: "session-do015-history",
    assignment_id: "assignment-do015-a",
    content_id: "content-do015-a",
    canonical_revision_id: "revision-do015-001",
    status: "AWAITING_ACTION",
    attempts,
    current_attempt_index: attempts.length - 1,
    ...overrides,
  };
}

/** Render into a stub container and hand back what was built. */
function render(args) {
  const restore = withStubDocument();
  try {
    const container = stubElement();
    renderGuidedSessionHistory({ container, ...args });
    const list = container.children.find((node) => node.className === "guided-history");
    return { container, list, items: list?.children ?? [] };
  } finally {
    restore();
  }
}

test("a single-attempt session renders exactly one attempt", () => {
  const { container, items } = render({ session: session([attempt(0)]) });
  assert.equal(items.length, 1);
  assert.equal(container.dataset.attemptCount, "1");
  assert.equal(container.dataset.sessionId, "session-do015-history");
  assert.equal(container.dataset.sessionStatus, "AWAITING_ACTION");
  assert.equal(items[0].dataset.attemptId, "attempt-0");
  assert.equal(items[0].dataset.action, "slow_down");
  assert.equal(items[0].dataset.disposition, "PENDING");
  assert.equal(items[0].dataset.execution, "NOT_REQUESTED");
});

test("attempts render in the session's own order", () => {
  const rows = guidedAttemptRows(
    session([
      attempt(0, APPLIED),
      attempt(1, { action_disposition: "DECLINED", execution_status: "NOT_REQUESTED" }),
      attempt(2),
    ]),
  );
  assert.deepEqual(
    rows.map((row) => row.attemptId),
    ["attempt-0", "attempt-1", "attempt-2"],
  );
  assert.deepEqual(
    rows.map((row) => row.index),
    [0, 1, 2],
  );
});

test("order comes from the array, not from status, digest, or id", () => {
  // Every sortable key here disagrees with the recorded order.
  const out = session([
    attempt(0, APPLIED, { attempt_id: "zzz", evaluation_digest: "sha256:z" }),
    attempt(1, {}, { attempt_id: "aaa", evaluation_digest: "sha256:a" }),
  ]);
  const { items } = render({ session: out });
  assert.deepEqual(
    items.map((item) => item.dataset.attemptId),
    ["zzz", "aaa"],
  );
});

test("the attempt number is a label; identity stays with attempt_id", () => {
  assert.equal(formatGuidedAttemptNumber(0), "Attempt 1");
  assert.equal(formatGuidedAttemptNumber(2), "Attempt 3");
  const { items } = render({ session: session([attempt(0, APPLIED), attempt(1)]) });
  const labels = items.map((item) => item.children[0].textContent);
  assert.deepEqual(labels, ["Attempt 1", "Attempt 2 — Current"]);
  // The label never becomes the identity.
  assert.equal(items[1].dataset.attemptId, "attempt-1");
  assert.notEqual(items[1].dataset.attemptId, "Attempt 2");
});

test("earlier attempts are historical and not actionable", () => {
  const open = session([attempt(0, APPLIED), attempt(1)]);
  const { items } = render({ session: open });
  assert.equal(items[0].dataset.current, "false");
  assert.equal(items[0].dataset.actionable, "false");
  assert.equal(items[1].dataset.current, "true");
  assert.equal(items[1].dataset.actionable, "true");
  assert.equal(isHistoricalGuidedAttempt(open, "attempt-0"), true);
  assert.equal(isHistoricalGuidedAttempt(open, "attempt-1"), false);
});

test("the current attempt is the contract's index, not the last array entry", () => {
  const out = session([attempt(0), attempt(1)], { current_attempt_index: 0 });
  const rows = guidedAttemptRows(out);
  assert.equal(rows[0].isCurrent, true);
  assert.equal(rows[1].isCurrent, false);
  assert.equal(getCurrentGuidedAttemptRow(out).attemptId, "attempt-0");
});

test("an accepted attempt awaiting Apply is the actionable one", () => {
  const out = session([
    attempt(0, APPLIED),
    attempt(1, { action_disposition: "ACCEPTED", execution_status: "PENDING" }),
  ]);
  const { items } = render({ session: out });
  assert.equal(items[1].dataset.actionable, "true");
  assert.equal(items[1].dataset.disposition, "ACCEPTED");
  assert.equal(items[1].dataset.execution, "PENDING");
});

test("a finalized current attempt is no longer actionable", () => {
  const out = session([attempt(0, APPLIED)], { status: "AWAITING_ATTEMPT" });
  const { items } = render({ session: out });
  assert.equal(items[0].dataset.current, "true");
  assert.equal(items[0].dataset.actionable, "false");
});

test("a closed session is entirely read-only and its history stays", () => {
  const out = session(
    [
      attempt(0, APPLIED),
      attempt(1, {
        recommended_action: { action_type: "continue" },
        action_disposition: "ACCEPTED",
        execution_status: "SUCCEEDED",
        executed_action: { action_type: "continue" },
      }),
    ],
    { status: "CLOSED" },
  );
  const { container, items } = render({ session: out });
  assert.equal(container.dataset.sessionStatus, "CLOSED");
  assert.equal(items.length, 2);
  assert.equal(items.every((item) => item.dataset.actionable === "false"), true);
});

test("a transitioned session is read-only too", () => {
  const out = session([attempt(0, APPLIED)], { status: "TRANSITIONED" });
  const { items } = render({ session: out });
  assert.equal(items[0].dataset.actionable, "false");
});

test("what happened is stated, not judged", () => {
  const out = session([
    attempt(0, APPLIED),
    attempt(1, { action_disposition: "DECLINED", execution_status: "NOT_REQUESTED" }),
    attempt(2, {
      recommended_action: { action_type: "view_one_string" },
      action_disposition: "ACCEPTED",
      execution_status: "UNSUPPORTED",
    }),
  ]);
  const { items } = render({ session: out });
  const text = items
    .flatMap((item) => item.children.map((child) => child.textContent))
    .join(" | ");
  assert.match(text, /Recommendation: Slow down/);
  assert.match(text, /Learner: Accepted/);
  assert.match(text, /Execution: Applied/);
  assert.match(text, /Learner: Declined/);
  assert.match(text, /Execution: Not supported yet/);
  for (const forbidden of [
    /master/i,
    /perfect/i,
    /improv/i,
    /better/i,
    /worse/i,
    /\bbad\b/i,
    /progress/i,
    /course complete/i,
    /lesson passed/i,
    /%/,
  ]) {
    assert.doesNotMatch(text, forbidden);
  }
});

test("a continue attempt that closed the session claims nothing more", () => {
  const out = session(
    [
      attempt(0, {
        recommended_action: { action_type: "continue" },
        action_disposition: "ACCEPTED",
        execution_status: "SUCCEEDED",
        executed_action: { action_type: "continue" },
      }),
    ],
    { status: "CLOSED" },
  );
  const { items } = render({ session: out });
  const text = items[0].children.map((child) => child.textContent).join(" | ");
  assert.match(text, /Recommendation: Continue/);
  assert.match(text, /Execution: Applied/);
  assert.doesNotMatch(text, /complete/i);
  assert.doesNotMatch(text, /master/i);
  assert.doesNotMatch(text, /passed/i);
});

test("no session and no attempts render an empty, honest panel", () => {
  const empty = render({ session: null });
  assert.equal(empty.container.dataset.attemptCount, "0");
  assert.equal(empty.container.children[0].textContent, "No guided attempts yet.");
  assert.equal(empty.container.dataset.sessionId, undefined);
  const zero = render({ session: session([]) });
  assert.equal(zero.container.dataset.attemptCount, "0");
});

test("rendering replaces the previous list rather than appending to it", () => {
  const restore = withStubDocument();
  try {
    const container = stubElement();
    const out = session([attempt(0, APPLIED), attempt(1)]);
    renderGuidedSessionHistory({ container, session: out });
    renderGuidedSessionHistory({ container, session: out });
    const lists = container.children.filter((node) => node.className === "guided-history");
    assert.equal(lists.length, 1);
    assert.equal(lists[0].children.length, 2);
  } finally {
    restore();
  }
});

test("an unrecorded attempt is reported as missing, never drawn into the list", () => {
  const { container, items } = render({
    session: session([attempt(0, APPLIED)], { status: "AWAITING_ATTEMPT" }),
    appendError: { phase: "append", status: "FAILED", error: "append rejected" },
  });
  assert.equal(items.length, 1);
  assert.equal(container.dataset.attemptCount, "1");
  assert.equal(container.dataset.appendStatus, "FAILED");
  const notice = container.children.find(
    (node) => node.className === "guided-history-error",
  );
  assert.equal(notice.textContent, "append rejected");
  assert.equal(notice.dataset.progressionPhase, "append");
});

test("a later clean render clears the append error", () => {
  const restore = withStubDocument();
  try {
    const container = stubElement();
    const out = session([attempt(0, APPLIED)]);
    renderGuidedSessionHistory({
      container,
      session: out,
      appendError: { status: "FAILED", error: "append rejected" },
    });
    assert.equal(container.dataset.appendStatus, "FAILED");
    renderGuidedSessionHistory({ container, session: out });
    assert.equal(container.dataset.appendStatus, undefined);
    assert.equal(
      container.children.some((node) => node.className === "guided-history-error"),
      false,
    );
  } finally {
    restore();
  }
});

test("a missing container is not an error", () => {
  assert.equal(renderGuidedSessionHistory({ session: null, container: null }), null);
  assert.equal(renderGuidedSessionHistory(), null);
});

test("the history renderer reaches no runtime, evaluator, or evaluator input", () => {
  const source = readFileSync(repoUrl("../guided-session-history.js"), "utf-8");
  // The guard is about code, so comments are stripped first: naming Transport
  // in a sentence that says this module does not touch it is not a call.
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  // Presentation only: no Transport seam, no Educational decision, and above
  // all not PracticeSessionHistory, which is the evaluator's input and not
  // this history.
  assert.doesNotMatch(code, /PracticeSessionHistory/);
  assert.doesNotMatch(code, /practice_session_history/);
  assert.doesNotMatch(code, /transport/i);
  assert.doesNotMatch(code, /setRate/);
  assert.doesNotMatch(code, /setLoop/);
  assert.doesNotMatch(code, /secondsAtTick/);
  assert.doesNotMatch(code, /practiceActions/);
  assert.doesNotMatch(code, /evaluate\(/);
  assert.doesNotMatch(code, /guidance_policy|buildTeachingGuidance|presentTeachingGuidance/);
  assert.doesNotMatch(code, /recordDisposition|recordExecution/);
  // It renders attempts; it never records one. (`container.append` is the DOM.)
  assert.doesNotMatch(code, /api\.append|syncFromEvaluation|GuidedSessionController/);
  assert.doesNotMatch(code, /attempts\.push|attempts\.splice|current_attempt_index\s*=[^=]/);
  // Its only import is the shared read-only session predicates.
  const imports = [...code.matchAll(/^import .*?from "(.+?)";$/gm)].map((m) => m[1]);
  assert.deepEqual(imports, ["./guided_disposition.js"]);
});

test("the renderer keeps no state between calls", () => {
  const restore = withStubDocument();
  try {
    const first = stubElement();
    const second = stubElement();
    renderGuidedSessionHistory({ container: first, session: session([attempt(0), attempt(1)]) });
    renderGuidedSessionHistory({ container: second, session: session([attempt(0)]) });
    assert.equal(first.dataset.attemptCount, "2");
    assert.equal(second.dataset.attemptCount, "1");
  } finally {
    restore();
  }
});
