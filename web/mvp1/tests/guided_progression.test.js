import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  GuidedProgressionError,
  GuidedSessionController,
  canApplyGuidedAction,
  canRecordDisposition,
  guidedSessionPinMismatch,
  isTerminalSession,
} from "../guided_disposition.js";
import { LocalGuidedSessionApi } from "../guided_session_api.js";
import { Transport } from "../transport.js";

const repoUrl = (path) => fileURLToPath(new URL(path, import.meta.url));

const ASSIGNMENT = "assignment-do015-a";
const CONTENT = "content-do015-a";
const REVISION = "revision-do015-001";

function attempt(index, overrides = {}) {
  return {
    attempt_id: `attempt-${index}`,
    attempt_index: index,
    assignment_id: ASSIGNMENT,
    content_id: CONTENT,
    canonical_revision_id: REVISION,
    performance_session_id: `performance-${index}`,
    evaluation_digest: `sha256:eval-${index}`,
    guidance_digest: `sha256:guide-${index}`,
    action: {
      recommended_action: { action_type: "slow_down", target_rate: 0.75 },
      action_disposition: "PENDING",
      execution_status: "NOT_REQUESTED",
      executed_action: null,
    },
    ...overrides,
  };
}

function session(overrides = {}) {
  return {
    session_id: "session-do015-progression",
    assignment_id: ASSIGNMENT,
    content_id: CONTENT,
    canonical_revision_id: REVISION,
    status: "AWAITING_ATTEMPT",
    attempts: [attempt(0)],
    current_attempt_index: 0,
    session_digest: "sha256:session-0",
    ...overrides,
  };
}

function evidence(n = 1, overrides = {}) {
  return {
    evaluation: {
      assignment_id: ASSIGNMENT,
      content_id: CONTENT,
      performance_session_id: `performance-${n}`,
      evaluation_digest: `sha256:eval-${n}`,
      ...(overrides.evaluation || {}),
    },
    guidance: {
      canonical_revision_id: REVISION,
      guidance_digest: `sha256:guide-${n}`,
      performance_session_id: `performance-${n}`,
      next_action: { action_type: "repeat" },
      ...(overrides.guidance || {}),
    },
  };
}

/**
 * A guided-session API double that records every call.
 *
 * `fail` injects the server rejections that matter here -- a refused append or
 * transition -- so the controller's promise to leave recorded history alone can
 * be observed rather than assumed.
 */
function fakeApi({ fail = {}, appendResult = null, transitionResult = null } = {}) {
  const calls = [];
  const reject = (op) => {
    const failure = fail[op];
    if (!failure) return null;
    const error = new Error(failure.message || `${op} rejected`);
    error.status = failure.status || 409;
    return error;
  };
  return {
    calls,
    ops: () => calls.map((call) => call.op),
    create: async (payload) => {
      calls.push({ op: "create", payload });
      const error = reject("create");
      if (error) throw error;
      return session({
        session_id: payload.sessionId,
        status: "AWAITING_ACTION",
        attempts: [attempt(0, { attempt_id: payload.attemptId })],
      });
    },
    append: async (payload) => {
      calls.push({ op: "append", payload });
      const error = reject("append");
      if (error) throw error;
      if (appendResult) return appendResult(payload);
      return session({
        status: "AWAITING_ACTION",
        attempts: [attempt(0), attempt(1, { attempt_id: payload.attemptId })],
        current_attempt_index: 1,
        session_digest: "sha256:session-1",
      });
    },
    transition: async (payload) => {
      calls.push({ op: "transition", payload });
      const error = reject("transition");
      if (error) throw error;
      if (transitionResult) return transitionResult(payload);
      return session({ status: "TRANSITIONED" });
    },
    recordDisposition: async (sessionId, disposition) => {
      calls.push({ op: "disposition", sessionId, disposition });
      return session({ status: "AWAITING_ATTEMPT" });
    },
    recordExecution: async (sessionId, executionStatus) => {
      calls.push({ op: "execution", sessionId, executionStatus });
      return session({ status: "AWAITING_ATTEMPT" });
    },
  };
}

function controllerWith(api, { seed = null, ids = null } = {}) {
  let n = 0;
  const controller = new GuidedSessionController({
    api,
    newId: ids ? () => ids.shift() : () => `minted-${n++}`,
  });
  if (seed) controller.session = seed;
  return controller;
}

test("a completed attempt appends to the open session and keeps its identity", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, { seed: session(), ids: ["attempt-1"] });
  const before = controller.session;
  const updated = await controller.syncFromEvaluation(evidence(1));
  assert.deepEqual(api.ops(), ["append"]);
  assert.equal(api.calls[0].payload.sessionId, before.session_id);
  assert.equal(api.calls[0].payload.attemptId, "attempt-1");
  assert.equal(updated.session_id, before.session_id);
  assert.equal(updated.attempts.length, 2);
  assert.equal(updated.current_attempt_index, 1);
  assert.equal(updated.status, "AWAITING_ACTION");
});

test("the appended attempt carries the evidence it was built from, unaltered", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, { seed: session() });
  const chain = evidence(1);
  await controller.syncFromEvaluation(chain);
  // The browser forwards the authoritative evidence chain; it does not compose
  // a new one, and it does not mint performance or digest identities.
  assert.equal(api.calls[0].payload.evaluation, chain.evaluation);
  assert.equal(api.calls[0].payload.guidance, chain.guidance);
});

test("the new attempt gets a fresh opaque id and leaves recorded ids alone", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, { seed: session(), ids: ["attempt-fresh"] });
  const updated = await controller.syncFromEvaluation(evidence(1));
  assert.notEqual(api.calls[0].payload.attemptId, "attempt-0");
  assert.equal(updated.attempts[0].attempt_id, "attempt-0");
  assert.equal(updated.attempts[1].attempt_id, "attempt-fresh");
});

test("attempt ids are minted by the caller, never derived from array position", async () => {
  const api = fakeApi();
  const controller = new GuidedSessionController({ api });
  controller.session = session();
  // The default minter is crypto.randomUUID; assert only that it is opaque and
  // is not the index or count it sits next to.
  await controller.syncFromEvaluation(evidence(1));
  const minted = api.calls[0].payload.attemptId;
  assert.equal(typeof minted, "string");
  assert.equal(minted.length > 8, true);
  assert.notEqual(minted, "1");
  assert.notEqual(minted, String(controller.session.attempts.length));
});

test("evidence without guidance is not enough to append", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, { seed: session() });
  assert.equal(await controller.syncFromEvaluation({ evaluation: {}, guidance: null }), null);
  assert.equal(await controller.syncFromEvaluation({ evaluation: null, guidance: {} }), null);
  assert.deepEqual(api.ops(), []);
});

test("AWAITING_ACTION does not append: the recommendation is still unanswered", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, {
    seed: session({ status: "AWAITING_ACTION" }),
  });
  const result = await controller.syncFromEvaluation(evidence(1));
  assert.deepEqual(api.ops(), []);
  assert.equal(result.attempts.length, 1);
});

test("a CLOSED session accepts no further attempt", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, { seed: session({ status: "CLOSED" }) });
  const result = await controller.syncFromEvaluation(evidence(1));
  assert.deepEqual(api.ops(), []);
  assert.equal(result.status, "CLOSED");
  assert.equal(result.attempts.length, 1);
  assert.equal(isTerminalSession(result), true);
});

test("a TRANSITIONED session accepts no further attempt", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, {
    seed: session({ status: "TRANSITIONED" }),
  });
  const result = await controller.syncFromEvaluation(evidence(1));
  assert.deepEqual(api.ops(), []);
  assert.equal(result.attempts.length, 1);
});

test("a failed append leaves the recorded session exactly as it was", async () => {
  const api = fakeApi({ fail: { append: { message: "append rejected", status: 409 } } });
  const seed = session();
  const controller = controllerWith(api, { seed });
  const before = JSON.stringify(controller.session);
  await assert.rejects(
    () => controller.syncFromEvaluation(evidence(1)),
    (error) => {
      assert.equal(error instanceof GuidedProgressionError, true);
      assert.equal(error.phase, "append");
      assert.equal(error.sessionPreserved, true);
      assert.equal(error.message, "append rejected");
      return true;
    },
  );
  assert.equal(controller.session, seed);
  assert.equal(JSON.stringify(controller.session), before);
  assert.equal(controller.session.attempts.length, 1);
});

test("a failed first creation reports that there was nothing to preserve", async () => {
  const api = fakeApi({ fail: { create: { message: "create rejected", status: 400 } } });
  const controller = controllerWith(api);
  await assert.rejects(
    () => controller.syncFromEvaluation(evidence(0)),
    (error) => {
      assert.equal(error.phase, "create");
      assert.equal(error.sessionPreserved, false);
      return true;
    },
  );
  assert.equal(controller.session, null);
});

test("a duplicate attempt id is the server's refusal, and history survives it", async () => {
  const api = fakeApi({
    fail: { append: { message: "duplicate attempt_id", status: 409 } },
  });
  const controller = controllerWith(api, { seed: session(), ids: ["attempt-0"] });
  await assert.rejects(() => controller.syncFromEvaluation(evidence(1)));
  assert.equal(controller.session.attempts.length, 1);
  assert.equal(controller.session.attempts[0].attempt_id, "attempt-0");
});

test("a duplicate performance identity is refused without touching history", async () => {
  const api = fakeApi({
    fail: {
      append: { message: "performance_session_id must be unique per attempt", status: 409 },
    },
  });
  const controller = controllerWith(api, { seed: session() });
  await assert.rejects(() => controller.syncFromEvaluation(evidence(0)));
  assert.equal(controller.session.attempts.length, 1);
  assert.equal(controller.session.attempts[0].performance_session_id, "performance-0");
});

test("evidence against another canonical revision is refused, not re-pinned", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, { seed: session() });
  await assert.rejects(
    () =>
      controller.syncFromEvaluation(
        evidence(1, { guidance: { canonical_revision_id: "revision-do015-002" } }),
      ),
    (error) => {
      assert.match(error.message, /canonical_revision_id/);
      assert.equal(error.sessionPreserved, true);
      return true;
    },
  );
  assert.deepEqual(api.ops(), []);
  assert.equal(controller.session.canonical_revision_id, REVISION);
  assert.equal(controller.session.attempts.length, 1);
});

test("evidence from another assignment or content never reaches the append route", async () => {
  for (const override of [
    { evaluation: { assignment_id: "assignment-do015-b" } },
    { evaluation: { content_id: "content-do015-b" } },
  ]) {
    const api = fakeApi();
    const controller = controllerWith(api, { seed: session() });
    await assert.rejects(() => controller.syncFromEvaluation(evidence(1, override)));
    assert.deepEqual(api.ops(), []);
    assert.equal(controller.session.attempts.length, 1);
  }
});

test("pin mismatch reports the first pin that disagrees", () => {
  const open = session();
  assert.equal(guidedSessionPinMismatch(open, evidence(1).evaluation, evidence(1).guidance), null);
  assert.equal(
    guidedSessionPinMismatch(open, { assignment_id: "other", content_id: CONTENT }, {
      canonical_revision_id: REVISION,
    }),
    "assignment_id",
  );
});

test("the server's session wins over anything the browser could have guessed", async () => {
  const api = fakeApi({
    appendResult: () =>
      session({
        status: "CLOSED",
        attempts: [attempt(0), attempt(1)],
        current_attempt_index: 1,
      }),
  });
  const controller = controllerWith(api, { seed: session() });
  const updated = await controller.syncFromEvaluation(evidence(1));
  // AWAITING_ACTION would have been the obvious local guess. The response said
  // otherwise, so the response is what the controller holds.
  assert.equal(updated.status, "CLOSED");
  assert.equal(controller.session.status, "CLOSED");
});

test("a lesson switch transitions the open session through the service", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, { seed: session() });
  const transitioned = await controller.transitionForLessonChange({
    nextAssignmentId: "assignment-do015-b",
    nextContentId: "content-do015-b",
  });
  assert.deepEqual(api.ops(), ["transition"]);
  assert.deepEqual(api.calls[0].payload, {
    sessionId: "session-do015-progression",
    nextAssignmentId: "assignment-do015-b",
    nextContentId: "content-do015-b",
    reason: null,
  });
  assert.equal(transitioned.status, "TRANSITIONED");
  // The old session is terminal and kept; the new lesson has none yet.
  assert.equal(controller.terminalSession.status, "TRANSITIONED");
  assert.equal(controller.session, null);
});

test("the transitioned session keeps its own lesson pins", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, { seed: session() });
  const transitioned = await controller.transitionForLessonChange({
    nextAssignmentId: "assignment-do015-b",
    nextContentId: "content-do015-b",
  });
  assert.equal(transitioned.assignment_id, ASSIGNMENT);
  assert.equal(transitioned.content_id, CONTENT);
  assert.equal(transitioned.canonical_revision_id, REVISION);
});

test("the new lesson's first evaluated attempt creates its own session", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, { seed: session(), ids: ["session-b", "attempt-b"] });
  await controller.transitionForLessonChange({
    nextAssignmentId: "assignment-do015-b",
    nextContentId: "content-do015-b",
  });
  await controller.syncFromEvaluation(evidence(0));
  assert.deepEqual(api.ops(), ["transition", "create"]);
  assert.equal(api.calls[1].payload.sessionId, "session-b");
});

test("a failed transition keeps the old session instead of discarding it", async () => {
  const api = fakeApi({
    fail: { transition: { message: "transition rejected", status: 409 } },
  });
  const seed = session();
  const controller = controllerWith(api, { seed });
  await assert.rejects(
    () =>
      controller.transitionForLessonChange({
        nextAssignmentId: "assignment-do015-b",
        nextContentId: "content-do015-b",
      }),
    (error) => {
      assert.equal(error.phase, "transition");
      assert.equal(error.sessionPreserved, true);
      return true;
    },
  );
  assert.equal(controller.session, seed);
  assert.equal(controller.session.status, "AWAITING_ATTEMPT");
  assert.equal(controller.terminalSession, null);
});

test("after a failed transition the stale session cannot act on the new lesson", async () => {
  const api = fakeApi({ fail: { transition: { message: "offline", status: 503 } } });
  const controller = controllerWith(api, {
    seed: session({ status: "AWAITING_ACTION" }),
  });
  await assert.rejects(() =>
    controller.transitionForLessonChange({
      nextAssignmentId: "assignment-do015-b",
      nextContentId: "content-do015-b",
    }),
  );
  controller.setLessonContext({
    assignmentId: "assignment-do015-b",
    contentId: "content-do015-b",
  });
  // The record survives, but it belongs to lesson A: nothing on lesson B's
  // screen may drive it.
  assert.notEqual(controller.session, null);
  assert.equal(controller.activeSession, null);
  assert.equal(canRecordDisposition(controller.activeSession), false);
  assert.equal(canApplyGuidedAction(controller.activeSession), false);
});

test("a stale session refuses the new lesson's evidence at the pin", async () => {
  const api = fakeApi({ fail: { transition: { message: "offline", status: 503 } } });
  const controller = controllerWith(api, { seed: session() });
  await assert.rejects(() =>
    controller.transitionForLessonChange({
      nextAssignmentId: "assignment-do015-b",
      nextContentId: "content-do015-b",
    }),
  );
  await assert.rejects(() =>
    controller.syncFromEvaluation(
      evidence(1, { evaluation: { assignment_id: "assignment-do015-b" } }),
    ),
  );
  assert.equal(api.ops().includes("append"), false);
});

test("reloading the same lesson is not a transition", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, { seed: session() });
  const result = await controller.transitionForLessonChange({
    nextAssignmentId: ASSIGNMENT,
    nextContentId: CONTENT,
  });
  assert.deepEqual(api.ops(), []);
  assert.equal(result.status, "AWAITING_ATTEMPT");
  assert.equal(controller.session.status, "AWAITING_ATTEMPT");
});

test("with no open session a lesson switch asks the service for nothing", async () => {
  const api = fakeApi();
  const controller = controllerWith(api);
  assert.equal(
    await controller.transitionForLessonChange({
      nextAssignmentId: "assignment-do015-b",
      nextContentId: "content-do015-b",
    }),
    null,
  );
  assert.deepEqual(api.ops(), []);
});

test("an already terminal session is retired locally, not transitioned again", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, { seed: session({ status: "CLOSED" }) });
  const result = await controller.transitionForLessonChange({
    nextAssignmentId: "assignment-do015-b",
    nextContentId: "content-do015-b",
  });
  assert.deepEqual(api.ops(), []);
  assert.equal(result.status, "CLOSED");
  assert.equal(controller.terminalSession.status, "CLOSED");
  assert.equal(controller.session, null);
});

test("the transition client posts the Stage 4 contract and nothing else", async () => {
  const requests = [];
  const api = new LocalGuidedSessionApi({
    fetchImpl: async (url, init) => {
      requests.push({ url, init });
      return { ok: true, status: 200, json: async () => session({ status: "TRANSITIONED" }) };
    },
  });
  await api.transition({
    sessionId: "session one",
    nextAssignmentId: "assignment-do015-b",
    nextContentId: "content-do015-b",
  });
  assert.equal(requests[0].url, "/api/education/guided-sessions/session%20one/transition");
  assert.equal(requests[0].init.method, "POST");
  assert.deepEqual(JSON.parse(requests[0].init.body), {
    next_assignment_id: "assignment-do015-b",
    next_content_id: "content-do015-b",
  });
  await api.transition({
    sessionId: "s",
    nextAssignmentId: "a",
    nextContentId: "c",
    reason: "lesson-change",
  });
  assert.equal(JSON.parse(requests[1].init.body).reason, "lesson-change");
});

test("a rejected transition surfaces the server's own refusal", async () => {
  const api = new LocalGuidedSessionApi({
    fetchImpl: async () => ({
      ok: false,
      status: 409,
      statusText: "Conflict",
      json: async () => ({ error: "transition requires an open session" }),
    }),
  });
  await assert.rejects(
    () => api.transition({ sessionId: "s", nextAssignmentId: "a", nextContentId: "c" }),
    (error) => {
      assert.equal(error.status, 409);
      assert.equal(error.message, "transition requires an open session");
      return true;
    },
  );
});

test("progression never evaluates a performance a second time", async () => {
  const api = fakeApi();
  const controller = controllerWith(api, { seed: session() });
  let evaluations = 0;
  const chain = evidence(1);
  const evaluate = () => {
    evaluations += 1;
    return chain;
  };
  await controller.syncFromEvaluation(evaluate());
  assert.equal(evaluations, 1);
  const source = readFileSync(repoUrl("../guided_disposition.js"), "utf-8");
  assert.doesNotMatch(source, /evaluate\(/);
  assert.doesNotMatch(source, /buildTeachingGuidance/);
});

test("progression touches no Transport seam", async () => {
  const api = fakeApi();
  const transport = new Transport();
  const controller = controllerWith(api, { seed: session() });
  const rate = transport.playbackRate;
  await controller.syncFromEvaluation(evidence(1));
  await controller.transitionForLessonChange({
    nextAssignmentId: "assignment-do015-b",
    nextContentId: "content-do015-b",
  });
  assert.equal(transport.playbackRate, rate);
  assert.equal(transport.loop, null);
});
