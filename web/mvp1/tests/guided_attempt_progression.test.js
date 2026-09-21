import assert from "node:assert/strict";
import test from "node:test";

import {
  GuidedSessionController,
  canApplyGuidedAction,
  canRecordDisposition,
  dispositionControlState,
} from "../guided_disposition.js";
import { createGuidedApplyHandler } from "../guided-action-executor.js";
import { guidedAttemptRows, renderGuidedSessionHistory } from "../guided-session-history.js";
import { PracticeActionController } from "../practice_actions.js";
import { resolveFocusRangeSeconds } from "../teaching-timeline.js";
import { Transport } from "../transport.js";
import { stubElement, withStubDocument } from "./dom_stub.js";

const ASSIGNMENT = "assignment-do015-a";
const CONTENT = "content-do015-a";
const REVISION = "revision-do015-001";

const ANCHORS = [
  { schema_version: "1.0.0", tick: 0, seconds: 0.0 },
  { schema_version: "1.0.0", tick: 8640, seconds: 4.5 },
];

const ACTIONS = {
  slow_down: { action_type: "slow_down", target_rate: 0.5, message_key: "action.slow_down" },
  isolate_passage: {
    action_type: "isolate_passage",
    focus_start_tick: 1920,
    focus_end_tick: 3840,
    message_key: "action.isolate_passage",
  },
  repeat: { action_type: "repeat", message_key: "action.repeat" },
  continue: { action_type: "continue", message_key: "action.continue" },
  view_one_string: { action_type: "view_one_string", message_key: "action.view_one_string" },
};

const UNSUPPORTED_ACTIONS = new Set(["view_one_string", "enable_zone_view"]);

/**
 * A guided-session server that follows the Stage 2 lifecycle.
 *
 * The Python service and its tests are the authority for these rules; this
 * mirror exists so a browser flow can be driven end to end. Where the two could
 * drift, the Python suite is what fails first.
 */
function lifecycleServer() {
  const sessions = new Map();
  const requests = [];
  const conflict = (message) => {
    const error = new Error(message);
    error.status = 409;
    return error;
  };
  const attemptFrom = (evaluation, guidance, attemptId, index) => ({
    schema_version: "1.0.0",
    attempt_id: attemptId,
    attempt_index: index,
    assignment_id: evaluation.assignment_id,
    content_id: evaluation.content_id,
    canonical_revision_id: guidance.canonical_revision_id,
    performance_session_id: evaluation.performance_session_id,
    evaluation_digest: evaluation.evaluation_digest,
    guidance_digest: guidance.guidance_digest,
    action: {
      schema_version: "1.0.0",
      recommended_action: guidance.next_action,
      action_disposition: "PENDING",
      execution_status: "NOT_REQUESTED",
      executed_action: null,
    },
    practice_context: { schema_version: "1.0.0", playback_rate: null },
  });
  const put = (session) => {
    sessions.set(session.session_id, session);
    // Hand out a copy, as an HTTP response would: the caller cannot reach back
    // into the stored record.
    return JSON.parse(JSON.stringify(session));
  };
  const withCurrent = (session, action, status) => ({
    ...session,
    status,
    attempts: [
      ...session.attempts.slice(0, -1),
      { ...session.attempts[session.attempts.length - 1], action },
    ],
  });
  return {
    requests,
    stored: (id) => sessions.get(id),
    create: async ({ sessionId, attemptId, evaluation, guidance }) => {
      requests.push({ op: "create", sessionId, attemptId });
      return put({
        schema_version: "1.0.0",
        session_id: sessionId,
        assignment_id: evaluation.assignment_id,
        content_id: evaluation.content_id,
        canonical_revision_id: guidance.canonical_revision_id,
        status: "AWAITING_ACTION",
        attempts: [attemptFrom(evaluation, guidance, attemptId, 0)],
        current_attempt_index: 0,
        session_digest: "sha256:session-0",
      });
    },
    append: async ({ sessionId, attemptId, evaluation, guidance }) => {
      requests.push({ op: "append", sessionId, attemptId });
      const session = sessions.get(sessionId);
      if (session.status !== "AWAITING_ATTEMPT") {
        throw conflict("append requires session.status AWAITING_ATTEMPT");
      }
      if (
        evaluation.assignment_id !== session.assignment_id ||
        evaluation.content_id !== session.content_id ||
        guidance.canonical_revision_id !== session.canonical_revision_id
      ) {
        throw conflict("append identity does not match session");
      }
      if (session.attempts.some((item) => item.attempt_id === attemptId)) {
        throw conflict("duplicate attempt_id");
      }
      if (
        session.attempts.some(
          (item) => item.performance_session_id === evaluation.performance_session_id,
        )
      ) {
        throw conflict("performance_session_id must be unique per attempt");
      }
      const index = session.attempts.length;
      return put({
        ...session,
        status: "AWAITING_ACTION",
        attempts: [...session.attempts, attemptFrom(evaluation, guidance, attemptId, index)],
        current_attempt_index: index,
        session_digest: `sha256:session-${index}`,
      });
    },
    recordDisposition: async (sessionId, disposition) => {
      requests.push({ op: "disposition", sessionId, disposition });
      const session = sessions.get(sessionId);
      if (session.status !== "AWAITING_ACTION") {
        throw conflict("disposition requires session.status AWAITING_ACTION");
      }
      const current = session.attempts[session.attempts.length - 1];
      if (current.action.action_disposition !== "PENDING") {
        throw conflict("action_disposition is already resolved");
      }
      if (disposition === "DECLINED") {
        return put(
          withCurrent(
            session,
            {
              ...current.action,
              action_disposition: "DECLINED",
              execution_status: "NOT_REQUESTED",
            },
            "AWAITING_ATTEMPT",
          ),
        );
      }
      return put(
        withCurrent(
          session,
          { ...current.action, action_disposition: "ACCEPTED", execution_status: "PENDING" },
          "AWAITING_ACTION",
        ),
      );
    },
    recordExecution: async (sessionId, executionStatus, executedAction) => {
      requests.push({ op: "execution", sessionId, executionStatus, executedAction });
      const session = sessions.get(sessionId);
      const current = session.attempts[session.attempts.length - 1];
      if (current.action.action_disposition !== "ACCEPTED") {
        throw conflict("execution cannot be recorded before acceptance");
      }
      if (current.action.execution_status !== "PENDING") {
        throw conflict("execution_status is already resolved");
      }
      const actionType = current.action.recommended_action.action_type;
      if (executionStatus === "SUCCEEDED" && UNSUPPORTED_ACTIONS.has(actionType)) {
        throw conflict("SUCCEEDED is not valid for unsupported Educational actions");
      }
      if (executionStatus === "UNSUPPORTED" && !UNSUPPORTED_ACTIONS.has(actionType)) {
        throw conflict("UNSUPPORTED is only valid for VIEW_ONE_STRING and ENABLE_ZONE_VIEW");
      }
      const status =
        executionStatus === "SUCCEEDED" && actionType === "continue"
          ? "CLOSED"
          : "AWAITING_ATTEMPT";
      return put(
        withCurrent(
          session,
          {
            ...current.action,
            execution_status: executionStatus,
            executed_action: executionStatus === "UNSUPPORTED" ? null : executedAction,
          },
          status,
        ),
      );
    },
    transition: async ({ sessionId, nextAssignmentId, nextContentId }) => {
      requests.push({ op: "transition", sessionId, nextAssignmentId, nextContentId });
      const session = sessions.get(sessionId);
      if (["CLOSED", "TRANSITIONED", "ABORTED"].includes(session.status)) {
        throw conflict("transition is not valid for a terminal session");
      }
      return put({ ...session, status: "TRANSITIONED" });
    },
  };
}

/** The browser side: controller, runtime seams, Apply handler, history view. */
function harness({ server = lifecycleServer() } = {}) {
  const transport = new Transport();
  transport.setDuration(4.5);
  const seams = [];
  const originalRate = transport.setRate.bind(transport);
  const originalLoop = transport.setLoop.bind(transport);
  transport.setRate = (...args) => {
    seams.push({ seam: "setRate", args });
    return originalRate(...args);
  };
  transport.setLoop = (...args) => {
    seams.push({ seam: "setLoop", args });
    return originalLoop(...args);
  };
  const actions = new PracticeActionController({
    transport,
    resolveFocusRange: (startTick, endTick) =>
      resolveFocusRangeSeconds(ANCHORS, startTick, endTick),
  });
  let minted = 0;
  const controller = new GuidedSessionController({
    api: server,
    newId: () => `opaque-${minted++}`,
  });
  const capture = {
    startCalls: 0,
    startAttempt() {
      this.startCalls += 1;
    },
  };
  const apply = createGuidedApplyHandler({
    getSession: () => controller.session,
    setSession: (session) => {
      controller.session = session;
    },
    recordExecution: (sessionId, executionStatus, executedAction) =>
      server.recordExecution(sessionId, executionStatus, executedAction),
    getRuntime: () => ({
      transport,
      applySlowDown: (action) => actions.applySlowDown(action),
      applyIsolatePassage: (action) => actions.applyIsolatePassage(action),
      capture,
    }),
  });
  let attemptNumber = 0;
  const perform = async (actionType) => {
    const n = attemptNumber++;
    return controller.syncFromEvaluation({
      evaluation: {
        assignment_id: ASSIGNMENT,
        content_id: CONTENT,
        performance_session_id: `performance-${n}`,
        evaluation_digest: `sha256:eval-${n}`,
      },
      guidance: {
        canonical_revision_id: REVISION,
        guidance_digest: `sha256:guide-${n}`,
        next_action: ACTIONS[actionType],
      },
    });
  };
  return { server, controller, transport, seams, actions, capture, apply, perform };
}

const serialize = (attempt) => JSON.stringify(attempt);

test("an accepted action applied and a second performance become two attempts", async () => {
  const h = harness();
  await h.perform("slow_down");
  await h.controller.recordDisposition("ACCEPTED");
  await h.apply();
  assert.equal(h.controller.session.status, "AWAITING_ATTEMPT");
  await h.perform("repeat");
  const session = h.controller.session;
  assert.equal(session.attempts.length, 2);
  assert.equal(session.status, "AWAITING_ACTION");
  assert.equal(session.current_attempt_index, 1);
  assert.equal(h.server.requests.filter((item) => item.op === "append").length, 1);
});

test("appending later attempts leaves the earlier ones byte-identical", async () => {
  const h = harness();
  await h.perform("slow_down");
  await h.controller.recordDisposition("ACCEPTED");
  await h.apply();
  const attemptZero = serialize(h.controller.session.attempts[0]);

  await h.perform("repeat");
  assert.equal(serialize(h.controller.session.attempts[0]), attemptZero);
  await h.controller.recordDisposition("ACCEPTED");
  await h.apply();
  const attemptOne = serialize(h.controller.session.attempts[1]);
  assert.equal(serialize(h.controller.session.attempts[0]), attemptZero);

  await h.perform("repeat");
  const session = h.controller.session;
  assert.equal(session.attempts.length, 3);
  assert.equal(serialize(session.attempts[0]), attemptZero);
  assert.equal(serialize(session.attempts[1]), attemptOne);
});

test("the session id never changes as attempts accumulate", async () => {
  const h = harness();
  await h.perform("slow_down");
  const sessionId = h.controller.session.session_id;
  await h.controller.recordDisposition("DECLINED");
  await h.perform("repeat");
  assert.equal(h.controller.session.session_id, sessionId);
  assert.equal(h.controller.session.assignment_id, ASSIGNMENT);
  assert.equal(h.controller.session.content_id, CONTENT);
  assert.equal(h.controller.session.canonical_revision_id, REVISION);
});

test("each appended attempt carries its own performance and digest identity", async () => {
  const h = harness();
  await h.perform("slow_down");
  await h.controller.recordDisposition("DECLINED");
  await h.perform("repeat");
  const [first, second] = h.controller.session.attempts;
  assert.equal(first.performance_session_id, "performance-0");
  assert.equal(second.performance_session_id, "performance-1");
  assert.equal(second.evaluation_digest, "sha256:eval-1");
  assert.equal(second.guidance_digest, "sha256:guide-1");
  assert.notEqual(first.attempt_id, second.attempt_id);
});

test("SLOW_DOWN progresses to the next attempt with the rate Stage 6 set", async () => {
  const h = harness();
  await h.perform("slow_down");
  await h.controller.recordDisposition("ACCEPTED");
  await h.apply();
  assert.deepEqual(
    h.seams.filter((item) => item.seam === "setRate").map((item) => item.args[0]),
    [0.5],
  );
  assert.equal(h.transport.playbackRate, 0.5);
  await h.perform("repeat");
  // Appending an attempt is not a runtime event: the rate Stage 6 applied is
  // still the rate.
  assert.equal(h.transport.playbackRate, 0.5);
  assert.equal(h.controller.session.attempts.length, 2);
});

test("ISOLATE_PASSAGE progresses without the loop being recomputed", async () => {
  const h = harness();
  await h.perform("isolate_passage");
  await h.controller.recordDisposition("ACCEPTED");
  await h.apply();
  const loopCalls = h.seams.filter((item) => item.seam === "setLoop");
  assert.equal(loopCalls.length, 1);
  const loopAfterApply = JSON.stringify(h.transport.loop);
  await h.perform("repeat");
  const rendered = guidedAttemptRows(h.controller.session);
  // The historical attempt shows what was recommended; rendering it does not
  // reach back into ticks, seconds, or the loop.
  assert.equal(rendered[0].actionType, "isolate_passage");
  assert.equal(h.seams.filter((item) => item.seam === "setLoop").length, 1);
  assert.equal(JSON.stringify(h.transport.loop), loopAfterApply);
});

test("REPEAT progresses without changing rate, loop, or starting a recording", async () => {
  const h = harness();
  await h.perform("repeat");
  await h.controller.recordDisposition("ACCEPTED");
  const rate = h.transport.playbackRate;
  await h.apply();
  assert.equal(h.transport.playbackRate, rate);
  assert.equal(h.transport.loop, null);
  assert.equal(h.seams.length, 0);
  assert.equal(h.capture.startCalls, 0);
  assert.equal(h.controller.session.status, "AWAITING_ATTEMPT");
  await h.perform("slow_down");
  assert.equal(h.controller.session.attempts.length, 2);
  assert.equal(h.capture.startCalls, 0);
});

test("a declined recommendation still lets the next attempt append", async () => {
  const h = harness();
  await h.perform("slow_down");
  await h.controller.recordDisposition("DECLINED");
  assert.equal(h.controller.session.status, "AWAITING_ATTEMPT");
  assert.equal(h.seams.length, 0);
  await h.perform("repeat");
  const rows = guidedAttemptRows(h.controller.session);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].disposition, "DECLINED");
  assert.equal(rows[0].execution, "NOT_REQUESTED");
  assert.equal(rows[0].isHistorical, true);
  assert.equal(rows[1].isCurrent, true);
});

test("an unsupported action is recorded as unsupported and the session moves on", async () => {
  const h = harness();
  await h.perform("view_one_string");
  await h.controller.recordDisposition("ACCEPTED");
  await h.apply();
  const [attempt] = h.controller.session.attempts;
  assert.equal(attempt.action.execution_status, "UNSUPPORTED");
  assert.equal(attempt.action.executed_action, null);
  assert.equal(h.seams.length, 0);
  assert.equal(h.controller.session.status, "AWAITING_ATTEMPT");
  await h.perform("repeat");
  assert.equal(h.controller.session.attempts.length, 2);
});

test("CONTINUE closes the session and nothing may be appended after it", async () => {
  const h = harness();
  await h.perform("continue");
  await h.controller.recordDisposition("ACCEPTED");
  await h.apply();
  assert.equal(h.controller.session.status, "CLOSED");
  const appendsBefore = h.server.requests.filter((item) => item.op === "append").length;
  const after = await h.perform("repeat");
  assert.equal(h.server.requests.filter((item) => item.op === "append").length, appendsBefore);
  assert.equal(after.attempts.length, 1);
  assert.equal(after.status, "CLOSED");
});

test("closing the guided cycle is not described as finishing anything", async () => {
  const restore = withStubDocument();
  try {
    const h = harness();
    await h.perform("continue");
    await h.controller.recordDisposition("ACCEPTED");
    await h.apply();
    const container = stubElement();
    renderGuidedSessionHistory({ container, session: h.controller.session });
    const text = JSON.stringify(container.children);
    for (const forbidden of [/master/i, /perfect/i, /course complete/i, /lesson passed/i]) {
      assert.doesNotMatch(text, forbidden);
    }
  } finally {
    restore();
  }
});

test("controls follow the current attempt and never the previous one", async () => {
  const h = harness();
  await h.perform("slow_down");
  await h.controller.recordDisposition("ACCEPTED");
  await h.apply();
  assert.equal(canRecordDisposition(h.controller.session), false);
  assert.equal(canApplyGuidedAction(h.controller.session), false);

  await h.perform("isolate_passage");
  const session = h.controller.session;
  // Attempt 1 is unanswered, so Accept/Decline are live again -- for it, not
  // for the attempt that already succeeded.
  assert.equal(canRecordDisposition(session), true);
  const state = dispositionControlState(session);
  assert.equal(state.acceptEnabled, true);
  assert.equal(state.applyDisabled, true);
  const rows = guidedAttemptRows(session);
  assert.equal(rows[0].actionable, false);
  assert.equal(rows[0].execution, "SUCCEEDED");
  assert.equal(rows[1].actionable, true);

  await h.controller.recordDisposition("ACCEPTED");
  assert.equal(canApplyGuidedAction(h.controller.session), true);
  assert.equal(
    guidedAttemptRows(h.controller.session)[0].actionable,
    false,
    "the finished attempt never becomes applicable again",
  );
});

test("applying the current attempt executes its own action, not the earlier one", async () => {
  const h = harness();
  await h.perform("slow_down");
  await h.controller.recordDisposition("ACCEPTED");
  await h.apply();
  await h.perform("isolate_passage");
  await h.controller.recordDisposition("ACCEPTED");
  await h.apply();
  const executions = h.server.requests.filter((item) => item.op === "execution");
  assert.equal(executions.length, 2);
  assert.equal(executions[0].executedAction.action_type, "slow_down");
  assert.equal(executions[1].executedAction.action_type, "isolate_passage");
  assert.equal(h.controller.session.attempts[0].action.executed_action.action_type, "slow_down");
});

test("a lesson switch ends the session and the next lesson starts empty", async () => {
  const restore = withStubDocument();
  try {
    const h = harness();
    await h.perform("slow_down");
    await h.controller.recordDisposition("ACCEPTED");
    await h.apply();
    const sessionId = h.controller.session.session_id;
    await h.controller.transitionForLessonChange({
      nextAssignmentId: "assignment-do015-b",
      nextContentId: "content-do015-b",
    });
    assert.equal(h.server.stored(sessionId).status, "TRANSITIONED");
    assert.equal(h.controller.session, null);
    assert.equal(h.controller.terminalSession.attempts.length, 1);
    const container = stubElement();
    renderGuidedSessionHistory({ container, session: h.controller.session });
    assert.equal(container.dataset.attemptCount, "0");
    // Lesson B gets a session only once it has an evaluated attempt of its own.
    assert.equal(
      h.server.requests.filter((item) => item.op === "create").length,
      1,
    );
  } finally {
    restore();
  }
});

test("the transitioned session keeps the attempts it recorded", async () => {
  const h = harness();
  await h.perform("slow_down");
  await h.controller.recordDisposition("DECLINED");
  await h.perform("repeat");
  const before = JSON.stringify(h.controller.session.attempts);
  await h.controller.transitionForLessonChange({
    nextAssignmentId: "assignment-do015-b",
    nextContentId: "content-do015-b",
  });
  assert.equal(JSON.stringify(h.controller.terminalSession.attempts), before);
  assert.equal(h.controller.terminalSession.status, "TRANSITIONED");
});

test("runtime failure keeps the acceptance and still allows the next attempt", async () => {
  const h = harness();
  await h.perform("slow_down");
  await h.controller.recordDisposition("ACCEPTED");
  // Make the rate seam refuse.
  h.actions.applySlowDown = () => false;
  await h.apply();
  const [attempt] = h.controller.session.attempts;
  assert.equal(attempt.action.action_disposition, "ACCEPTED");
  assert.equal(attempt.action.execution_status, "FAILED");
  assert.equal(h.controller.session.status, "AWAITING_ATTEMPT");
  await h.perform("repeat");
  assert.equal(h.controller.session.attempts.length, 2);
  assert.equal(
    serialize(h.controller.session.attempts[0].action),
    serialize(attempt.action),
  );
});

test("a rejected append leaves the recorded attempts and status untouched", async () => {
  const h = harness();
  await h.perform("slow_down");
  await h.controller.recordDisposition("ACCEPTED");
  await h.apply();
  const before = JSON.stringify(h.controller.session);
  // The server refuses the next attempt; the browser keeps what it had.
  const server = h.server;
  const realAppend = server.append;
  server.append = async () => {
    const error = new Error("append rejected");
    error.status = 409;
    throw error;
  };
  await assert.rejects(() => h.perform("repeat"));
  assert.equal(JSON.stringify(h.controller.session), before);
  assert.equal(h.controller.session.attempts.length, 1);
  assert.equal(h.controller.session.status, "AWAITING_ATTEMPT");
  // And the session is still able to take the attempt once the server can.
  server.append = realAppend;
  await h.perform("repeat");
  assert.equal(h.controller.session.attempts.length, 2);
});

test("the identity chain is untouched by every later attempt", async () => {
  const h = harness();
  await h.perform("slow_down");
  const first = { ...h.controller.session.attempts[0] };
  const sessionRevision = h.controller.session.canonical_revision_id;
  await h.controller.recordDisposition("ACCEPTED");
  await h.apply();
  await h.perform("repeat");
  await h.controller.recordDisposition("DECLINED");
  await h.perform("continue");
  const session = h.controller.session;
  assert.equal(session.canonical_revision_id, sessionRevision);
  assert.equal(session.attempts[0].performance_session_id, first.performance_session_id);
  assert.equal(session.attempts[0].evaluation_digest, first.evaluation_digest);
  assert.equal(session.attempts[0].guidance_digest, first.guidance_digest);
  assert.equal(session.attempts[0].attempt_id, first.attempt_id);
  assert.deepEqual(
    session.attempts.map((attempt) => attempt.attempt_index),
    [0, 1, 2],
  );
});
