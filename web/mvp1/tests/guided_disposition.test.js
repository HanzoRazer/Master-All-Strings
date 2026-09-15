import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  GuidedSessionController,
  applyDispositionControls,
  canApplyGuidedAction,
  canRecordDisposition,
  createGuidanceDispositionHandler,
  currentAttemptAction,
  dispositionControlState,
} from "../guided_disposition.js";
import { stubElement } from "./dom_stub.js";
import { Transport } from "../transport.js";

const repoUrl = (path) => fileURLToPath(new URL(path, import.meta.url));

function pendingSession(overrides = {}) {
  return {
    session_id: "session-do015-ui",
    status: "AWAITING_ACTION",
    current_attempt_index: 0,
    attempts: [
      {
        attempt_id: "attempt-0",
        action: {
          recommended_action: { action_type: "slow_down", target_rate: 0.75 },
          action_disposition: "PENDING",
          execution_status: "NOT_REQUESTED",
        },
      },
    ],
    ...overrides,
  };
}

function fakeApi() {
  const calls = [];
  return {
    calls,
    create: async (payload) => {
      calls.push({ op: "create", payload });
      return pendingSession({ session_id: payload.sessionId });
    },
    append: async (payload) => {
      calls.push({ op: "append", payload });
      return pendingSession({
        session_id: payload.sessionId,
        attempts: [
          pendingSession().attempts[0],
          {
            attempt_id: payload.attemptId,
            action: {
              recommended_action: { action_type: "repeat" },
              action_disposition: "PENDING",
              execution_status: "NOT_REQUESTED",
            },
          },
        ],
        current_attempt_index: 1,
      });
    },
    recordDisposition: async (sessionId, disposition) => {
      calls.push({ op: "disposition", sessionId, disposition });
      return pendingSession({
        session_id: sessionId,
        status: disposition === "DECLINED" ? "AWAITING_ATTEMPT" : "AWAITING_ACTION",
        attempts: [
          {
            attempt_id: "attempt-0",
            action: {
              recommended_action: { action_type: "slow_down", target_rate: 0.75 },
              action_disposition: disposition,
              execution_status: disposition === "ACCEPTED" ? "PENDING" : "NOT_REQUESTED",
            },
          },
        ],
      });
    },
    recordExecution: async (sessionId, executionStatus, executedAction) => {
      calls.push({ op: "execution", sessionId, executionStatus, executedAction });
      return pendingSession({
        session_id: sessionId,
        status: executionStatus === "SUCCEEDED" ? "AWAITING_ATTEMPT" : "AWAITING_ACTION",
        attempts: [
          {
            attempt_id: "attempt-0",
            action: {
              recommended_action: { action_type: "slow_down", target_rate: 0.75 },
              action_disposition: "ACCEPTED",
              execution_status: executionStatus,
              executed_action: executedAction ?? null,
            },
          },
        ],
      });
    },
  };
}

test("syncFromEvaluation creates a session from the first evidence chain", async () => {
  const api = fakeApi();
  const ids = ["session-a", "attempt-a"];
  const controller = new GuidedSessionController({
    api,
    newId: () => ids.shift(),
  });
  const session = await controller.syncFromEvaluation({
    evaluation: { evaluation_digest: "sha256:e" },
    guidance: { guidance_digest: "sha256:g" },
  });
  assert.equal(session.session_id, "session-a");
  assert.equal(api.calls[0].op, "create");
  assert.deepEqual(api.calls[0].payload, {
    sessionId: "session-a",
    attemptId: "attempt-a",
    evaluation: { evaluation_digest: "sha256:e" },
    guidance: { guidance_digest: "sha256:g" },
  });
  assert.equal(canRecordDisposition(session), true);
});

test("accept records ACCEPTED/PENDING and does not touch Transport", async () => {
  const api = fakeApi();
  const transport = new Transport();
  const controller = new GuidedSessionController({
    api,
    newId: () => "id",
  });
  await controller.syncFromEvaluation({
    evaluation: { evaluation_digest: "sha256:e" },
    guidance: { guidance_digest: "sha256:g" },
  });
  const rateBefore = transport.playbackRate;
  const session = await controller.recordDisposition("ACCEPTED");
  assert.equal(currentAttemptAction(session).action_disposition, "ACCEPTED");
  assert.equal(currentAttemptAction(session).execution_status, "PENDING");
  assert.equal(transport.playbackRate, rateBefore);
  assert.equal(transport.loop, null);
  assert.equal(api.calls.some((call) => call.op === "disposition"), true);
});

test("decline records DECLINED/NOT_REQUESTED and does not touch Transport", async () => {
  const api = fakeApi();
  const transport = new Transport();
  const controller = new GuidedSessionController({
    api,
    newId: () => "id",
  });
  await controller.syncFromEvaluation({
    evaluation: { evaluation_digest: "sha256:e" },
    guidance: { guidance_digest: "sha256:g" },
  });
  const session = await controller.recordDisposition("DECLINED");
  assert.equal(currentAttemptAction(session).action_disposition, "DECLINED");
  assert.equal(currentAttemptAction(session).execution_status, "NOT_REQUESTED");
  assert.equal(transport.playbackRate, 1);
  assert.equal(transport.loop, null);
});

test("recordExecution consumes the server-returned session", async () => {
  const api = fakeApi();
  const controller = new GuidedSessionController({
    api,
    newId: () => "id",
  });
  await controller.syncFromEvaluation({
    evaluation: { evaluation_digest: "sha256:e" },
    guidance: { guidance_digest: "sha256:g" },
  });
  await controller.recordDisposition("ACCEPTED");
  assert.equal(canApplyGuidedAction(controller.session), true);
  const session = await controller.recordExecution("SUCCEEDED", {
    action_type: "slow_down",
    target_rate: 0.75,
  });
  assert.equal(session.status, "AWAITING_ATTEMPT");
  assert.equal(currentAttemptAction(session).execution_status, "SUCCEEDED");
  assert.equal(api.calls[api.calls.length - 1].op, "execution");
  assert.equal(canApplyGuidedAction(session), false);
});

test("a resolved disposition cannot be recorded again", async () => {
  const api = fakeApi();
  const controller = new GuidedSessionController({
    api,
    newId: () => "id",
  });
  await controller.syncFromEvaluation({
    evaluation: { evaluation_digest: "sha256:e" },
    guidance: { guidance_digest: "sha256:g" },
  });
  await controller.recordDisposition("ACCEPTED");
  const before = api.calls.length;
  const session = await controller.recordDisposition("DECLINED");
  assert.equal(api.calls.length, before);
  assert.equal(currentAttemptAction(session).action_disposition, "ACCEPTED");
});

test("after decline, the next evaluation appends rather than creating a new session", async () => {
  const api = fakeApi();
  let n = 0;
  const controller = new GuidedSessionController({
    api,
    newId: () => `id-${n++}`,
  });
  await controller.syncFromEvaluation({
    evaluation: { evaluation_digest: "sha256:e0" },
    guidance: { guidance_digest: "sha256:g0" },
  });
  await controller.recordDisposition("DECLINED");
  const session = await controller.syncFromEvaluation({
    evaluation: { evaluation_digest: "sha256:e1" },
    guidance: { guidance_digest: "sha256:g1" },
  });
  assert.equal(api.calls.filter((call) => call.op === "append").length, 1);
  assert.equal(session.current_attempt_index, 1);
});

test("disposition controls enable Apply only after accept", () => {
  const accept = stubElement();
  const decline = stubElement();
  const apply = stubElement({ hidden: true, disabled: true });
  const status = stubElement();
  applyDispositionControls(
    { accept, decline, apply, status },
    pendingSession({
      attempts: [
        {
          action: {
            recommended_action: { action_type: "slow_down", target_rate: 0.75 },
            action_disposition: "ACCEPTED",
            execution_status: "PENDING",
          },
        },
      ],
    }),
  );
  assert.equal(accept.disabled, true);
  assert.equal(decline.disabled, true);
  assert.equal(apply.hidden, false);
  assert.equal(apply.disabled, false);
  assert.equal(status.textContent, "Accepted — ready to apply");
  assert.equal(status.dataset.disposition, "ACCEPTED");
  assert.equal(status.dataset.execution, "PENDING");
});

test("finalized execution disables Apply", () => {
  const apply = stubElement({ hidden: false, disabled: false });
  applyDispositionControls(
    { apply },
    pendingSession({
      attempts: [
        {
          action: {
            recommended_action: { action_type: "slow_down", target_rate: 0.75 },
            action_disposition: "ACCEPTED",
            execution_status: "SUCCEEDED",
          },
        },
      ],
    }),
  );
  assert.equal(apply.hidden, false);
  assert.equal(apply.disabled, true);
});

test("pending controls enable Accept/Decline and keep Apply unreachable", () => {
  const state = dispositionControlState(pendingSession());
  assert.equal(state.acceptEnabled, true);
  assert.equal(state.declineEnabled, true);
  assert.equal(state.applyHidden, true);
  assert.equal(state.applyDisabled, true);
});

test("the disposition handler ignores unknown values and missing sessions", async () => {
  const api = fakeApi();
  const handler = createGuidanceDispositionHandler({
    guidedSessionApi: api,
    getSessionId: () => null,
  });
  assert.equal(await handler("ACCEPTED"), null);
  assert.equal(await handler("MAYBE"), null);
  assert.equal(api.calls.length, 0);
});

test("disposition modules do not apply actions or mutate Transport", () => {
  const disposition = readFileSync(repoUrl("../guided_disposition.js"), "utf-8");
  const app = readFileSync(repoUrl("../app.js"), "utf-8");
  assert.doesNotMatch(disposition, /practiceActions\.apply/);
  assert.doesNotMatch(disposition, /createGuidanceAcceptHandler/);
  assert.doesNotMatch(disposition, /setRate/);
  assert.doesNotMatch(disposition, /setLoop/);
  assert.doesNotMatch(disposition, /executeGuidedAction/);
  assert.doesNotMatch(app, /practiceActions\.apply\(/);
  assert.doesNotMatch(app, /createGuidanceAcceptHandler/);
  assert.doesNotMatch(app, /await acceptGuidance/);
  const acceptFn = app.slice(
    app.indexOf("async function recordLearnerDisposition"),
    app.indexOf("$(\"btnAcceptGuidance\")"),
  );
  assert.doesNotMatch(acceptFn, /executeGuidedAction/);
  assert.doesNotMatch(acceptFn, /recordExecution/);
  assert.doesNotMatch(acceptFn, /setRate/);
  assert.match(app, /btnApplyPrimary"\)\.addEventListener/);
});
