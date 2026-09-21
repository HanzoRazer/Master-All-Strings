import assert from "node:assert/strict";
import test from "node:test";

import { executionCopy, renderResultsPanel } from "../results.js";
import { stubElement } from "./dom_stub.js";

class FakeElement {
  constructor() {
    this.dataset = {};
    this.children = [];
    this.innerHTML = "";
    this.textContent = "";
    this.className = "";
  }
  append(...nodes) {
    this.children.push(...nodes);
  }
}

globalThis.document = {
  createElement: () => new FakeElement(),
};

function evaluationPayload() {
  return {
    evaluation: {
      findings: [],
      summary: { actionable_finding_count: 0 },
      primary_next_action: {
        action_type: "slow_down",
        message_key: "action.slow_down",
      },
    },
    messages: { "action.slow_down": "Slow down" },
    guidance: { guidance_digest: "sha256:guide", items: [] },
  };
}

/** Render the panel and its history together, as the app does. */
function renderGuidedHistoryVia(root, history, session) {
  renderResultsPanel(root, evaluationPayload(), session, null, {
    historyContainer: history,
  });
}

test("results keep recommendation separate from accepted disposition", () => {
  const root = stubElement();
  renderResultsPanel(root, evaluationPayload(), {
    current_attempt_index: 0,
    attempts: [
      {
        action: {
          action_disposition: "ACCEPTED",
          execution_status: "PENDING",
        },
      },
    ],
  });
  const summary = root.children[0];
  assert.equal(summary.dataset.action, "slow_down");
  assert.equal(summary.dataset.disposition, "ACCEPTED");
  assert.equal(summary.dataset.execution, "PENDING");
  const html = summary.innerHTML;
  assert.match(html, /Slow down/);
  assert.match(html, /Accepted — ready to apply/);
  assert.match(html, /Ready to apply/);
  assert.doesNotMatch(html, /SUCCEEDED/);
  assert.doesNotMatch(html, /Applied/);
  assert.doesNotMatch(html, /reuses the existing transport/);
});

test("results distinguish Applied from Accepted", () => {
  const root = stubElement();
  renderResultsPanel(root, evaluationPayload(), {
    status: "AWAITING_ATTEMPT",
    current_attempt_index: 0,
    attempts: [
      {
        action: {
          action_disposition: "ACCEPTED",
          execution_status: "SUCCEEDED",
        },
      },
    ],
  });
  const html = root.children[0].innerHTML;
  assert.match(html, /Applied/);
  assert.doesNotMatch(html, /Evidence recording failed/);
  assert.equal(root.children[0].dataset.sessionStatus, "AWAITING_ATTEMPT");
});

test("CONTINUE applied copy does not claim mastery", () => {
  const payload = evaluationPayload();
  payload.evaluation.primary_next_action = {
    action_type: "continue",
    message_key: "action.continue",
  };
  payload.messages = { "action.continue": "Continue under this policy." };
  const root = stubElement();
  renderResultsPanel(root, payload, {
    status: "CLOSED",
    current_attempt_index: 0,
    attempts: [
      {
        action: {
          action_disposition: "ACCEPTED",
          execution_status: "SUCCEEDED",
        },
      },
    ],
  });
  const html = root.children[0].innerHTML.toLowerCase();
  assert.match(html, /applied/);
  assert.doesNotMatch(html, /mastered/);
  assert.doesNotMatch(html, /perfect/);
  assert.doesNotMatch(html, /course complete/);
  assert.doesNotMatch(html, /lesson passed/);
  assert.equal(root.children[0].dataset.sessionStatus, "CLOSED");
});

test("partial success does not claim session-recorded success", () => {
  const root = stubElement();
  renderResultsPanel(
    root,
    evaluationPayload(),
    {
      current_attempt_index: 0,
      attempts: [
        {
          action: {
            action_disposition: "ACCEPTED",
            execution_status: "PENDING",
          },
        },
      ],
    },
    { runtimeStatus: "SUCCEEDED", evidenceStatus: "FAILED" },
  );
  const html = root.children[0].innerHTML;
  assert.match(html, /Evidence recording failed/);
  assert.doesNotMatch(html, />Applied</);
  assert.equal(root.children[0].dataset.execution, "PENDING");
  assert.equal(executionCopy(null, { phase: "applying" }), "Applying…");
});

test("declined results do not claim the action was applied", () => {
  const root = stubElement();
  renderResultsPanel(root, evaluationPayload(), {
    current_attempt_index: 0,
    attempts: [
      {
        action: {
          action_disposition: "DECLINED",
          execution_status: "NOT_REQUESTED",
        },
      },
    ],
  });
  assert.match(root.children[0].innerHTML, /Declined\. The recommendation was not applied/);
});

test("the results panel mounts the guided history beside the evaluation", () => {
  const root = stubElement();
  const history = stubElement();
  renderGuidedHistoryVia(root, history, {
    session_id: "session-results",
    status: "AWAITING_ACTION",
    current_attempt_index: 1,
    attempts: [
      {
        attempt_id: "attempt-0",
        action: {
          recommended_action: { action_type: "slow_down" },
          action_disposition: "ACCEPTED",
          execution_status: "SUCCEEDED",
          executed_action: { action_type: "slow_down" },
        },
      },
      {
        attempt_id: "attempt-1",
        action: {
          recommended_action: { action_type: "repeat" },
          action_disposition: "PENDING",
          execution_status: "NOT_REQUESTED",
        },
      },
    ],
  });
  assert.equal(history.dataset.attemptCount, "2");
  assert.equal(history.dataset.sessionId, "session-results");
  const list = history.children.find((node) => node.className === "guided-history");
  assert.equal(list.children.length, 2);
  assert.equal(list.children[0].dataset.current, "false");
  assert.equal(list.children[1].dataset.current, "true");
});

test("a lesson with no evaluation clears the guided history with it", () => {
  const root = stubElement();
  const history = stubElement();
  renderGuidedHistoryVia(root, history, {
    session_id: "session-results",
    status: "AWAITING_ACTION",
    current_attempt_index: 0,
    attempts: [{ attempt_id: "attempt-0", action: {} }],
  });
  assert.equal(history.dataset.attemptCount, "1");
  // The results panel returns early for a missing evaluation; the history must
  // still be cleared, or the previous lesson's attempts stay on screen.
  renderResultsPanel(root, null, null, null, { historyContainer: history });
  assert.equal(history.dataset.attemptCount, "0");
  assert.equal(history.dataset.sessionId, undefined);
  assert.equal(root.textContent, "No practice evaluation yet.");
});

test("an unrecorded attempt is surfaced through the results render", () => {
  const root = stubElement();
  const history = stubElement();
  renderResultsPanel(root, evaluationPayload(), null, null, {
    historyContainer: history,
    appendError: { phase: "append", status: "FAILED", error: "append rejected" },
  });
  assert.equal(history.dataset.appendStatus, "FAILED");
});
