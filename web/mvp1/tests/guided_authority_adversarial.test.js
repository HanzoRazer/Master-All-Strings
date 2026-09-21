/**
 * DO-015 Stage 8 gap-fill: adversarial authority cases Stage 4–7 do not own.
 *
 * Happy-path and already-locked transitions stay in those suites. This file
 * proves the cells they left open: a single pin disagreeing while the others
 * match, direct handler calls under a dead active session, a forged local
 * session that never becomes the request, history DOM that cannot rewrite the
 * record, and a second Apply that arrives while the first is still in flight.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { createGuidedApplyHandler } from "../guided-action-executor.js";
import {
  GuidedSessionController,
  canRecordDisposition,
  createGuidanceDispositionHandler,
} from "../guided_disposition.js";
import { renderGuidedSessionHistory } from "../guided-session-history.js";
import { stubElement, withStubDocument } from "./dom_stub.js";

const repoUrl = (path) => fileURLToPath(new URL(path, import.meta.url));

const ASSIGNMENT = "assignment-do015-a";
const CONTENT = "content-do015-a";
const REVISION = "revision-do015-001";

function attempt(index, actionOverrides = {}) {
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
      ...actionOverrides,
    },
  };
}

function session(overrides = {}) {
  const attempts = overrides.attempts || [attempt(0, { action_disposition: "PENDING" })];
  return {
    session_id: "session-do015-adversarial",
    assignment_id: ASSIGNMENT,
    content_id: CONTENT,
    canonical_revision_id: REVISION,
    status: "AWAITING_ACTION",
    attempts,
    current_attempt_index: attempts.length - 1,
    session_digest: "sha256:session-0",
    ...overrides,
  };
}

function recordingApi() {
  const calls = [];
  return {
    calls,
    ops: () => calls.map((call) => call.op),
    recordDisposition: async (sessionId, disposition) => {
      calls.push({ op: "disposition", sessionId, disposition });
      return session({
        status: "AWAITING_ACTION",
        attempts: [
          attempt(0, {
            action_disposition: "ACCEPTED",
            execution_status: "PENDING",
          }),
        ],
      });
    },
    recordExecution: async (sessionId, executionStatus, executedAction) => {
      calls.push({ op: "execution", sessionId, executionStatus, executedAction });
      return session();
    },
    append: async (payload) => {
      calls.push({ op: "append", payload });
      return session();
    },
    create: async (payload) => {
      calls.push({ op: "create", payload });
      return session();
    },
    transition: async (payload) => {
      calls.push({ op: "transition", payload });
      throw Object.assign(new Error("offline"), { status: 503 });
    },
  };
}

function pinContext(overrides = {}) {
  return {
    assignmentId: ASSIGNMENT,
    contentId: CONTENT,
    canonicalRevisionId: REVISION,
    ...overrides,
  };
}

function controllerOn(api, seed) {
  const controller = new GuidedSessionController({ api, newId: () => "minted" });
  controller.session = seed;
  controller.setLessonContext(pinContext());
  return controller;
}

test("assignment mismatch alone leaves the session inert", async () => {
  const api = recordingApi();
  const controller = controllerOn(api, session());
  assert.equal(canRecordDisposition(controller.session), true);
  controller.setLessonContext(pinContext({ assignmentId: "assignment-do015-b" }));
  assert.equal(controller.activeSession, null);
  assert.equal(await controller.recordDisposition("ACCEPTED"), controller.session);
  assert.equal(await controller.recordExecution("SUCCEEDED", { action_type: "slow_down" }), controller.session);
  assert.deepEqual(api.ops(), []);
});

test("content mismatch alone leaves the session inert", async () => {
  const api = recordingApi();
  const controller = controllerOn(api, session());
  controller.setLessonContext(pinContext({ contentId: "content-do015-b" }));
  assert.equal(controller.activeSession, null);
  await controller.recordDisposition("DECLINED");
  await controller.recordExecution("SUCCEEDED", null);
  assert.deepEqual(api.ops(), []);
});

test("all three pins disagreeing still cannot append or act", async () => {
  const api = recordingApi();
  const controller = controllerOn(api, session());
  const recorded = JSON.stringify(controller.session);
  controller.setLessonContext(
    pinContext({
      assignmentId: "assignment-do015-b",
      contentId: "content-do015-b",
      canonicalRevisionId: "revision-do015-002",
    }),
  );
  assert.equal(controller.activeSession, null);
  await controller.recordDisposition("ACCEPTED");
  await controller.syncFromEvaluation({
    evaluation: {
      assignment_id: "assignment-do015-b",
      content_id: "content-do015-b",
      performance_session_id: "performance-9",
      evaluation_digest: "sha256:other",
    },
    guidance: {
      canonical_revision_id: "revision-do015-002",
      performance_session_id: "performance-9",
      evaluation_digest: "sha256:other",
    },
  }).catch((error) => error);
  assert.equal(JSON.stringify(controller.session), recorded);
  assert.deepEqual(api.ops(), []);
});

test("a direct disposition handler cannot bypass an inactive session", async () => {
  const api = recordingApi();
  const controller = controllerOn(api, session());
  controller.setLessonContext(pinContext({ canonicalRevisionId: null }));
  assert.equal(controller.activeSession, null);
  const forged = session();
  assert.equal(canRecordDisposition(forged), true);
  const handler = createGuidanceDispositionHandler({
    guidedSessionApi: api,
    getSessionId: () => controller.activeSession?.session_id ?? null,
  });
  assert.equal(await handler("ACCEPTED"), null);
  assert.equal(await handler("DECLINED"), null);
  assert.deepEqual(api.ops(), []);
  assert.equal(controller.session.attempts[0].action.action_disposition, "PENDING");
});

test("the server session replaces a locally tampered recommendation", async () => {
  const api = recordingApi();
  const controller = controllerOn(api, session());
  controller.session.attempts[0].action.recommended_action = {
    action_type: "isolate_passage",
    focus_start_tick: 0,
    focus_end_tick: 10,
  };
  const updated = await controller.recordDisposition("ACCEPTED");
  assert.deepEqual(api.calls[0], {
    op: "disposition",
    sessionId: "session-do015-adversarial",
    disposition: "ACCEPTED",
  });
  assert.equal(updated.attempts[0].action.recommended_action.action_type, "slow_down");
  assert.equal(controller.session, updated);
});

test("a failed transition's preserved session ignores direct learner calls", async () => {
  const api = recordingApi();
  const seed = session({ status: "AWAITING_ACTION" });
  const controller = controllerOn(api, seed);
  await assert.rejects(() =>
    controller.transitionForLessonChange({
      nextAssignmentId: "assignment-do015-b",
      nextContentId: "content-do015-b",
    }),
  );
  controller.setLessonContext(
    pinContext({
      assignmentId: "assignment-do015-b",
      contentId: "content-do015-b",
      canonicalRevisionId: REVISION,
    }),
  );
  const recorded = JSON.stringify(controller.session);
  const apply = createGuidedApplyHandler({
    getSession: () => controller.activeSession,
    execute: () => {
      throw new Error("runtime must not run");
    },
    recordExecution: async () => {
      throw new Error("execution must not be posted");
    },
  });
  assert.equal(controller.activeSession, null);
  assert.equal(await controller.recordDisposition("ACCEPTED"), controller.session);
  assert.equal(await apply(), null);
  assert.equal(JSON.stringify(controller.session), recorded);
  assert.deepEqual(
    api.ops().filter((op) => op !== "transition"),
    [],
  );
});

test("overlapping Apply calls actuate runtime once", async () => {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  let runtimeCalls = 0;
  let posts = 0;
  const sessionState = session({
    attempts: [
      attempt(0, {
        action_disposition: "ACCEPTED",
        execution_status: "PENDING",
      }),
    ],
  });
  assert.equal(sessionState.attempts[0].action.action_disposition, "ACCEPTED");
  const apply = createGuidedApplyHandler({
    getSession: () => sessionState,
    execute: () => {
      runtimeCalls += 1;
      return {
        status: "SUCCEEDED",
        executedAction: sessionState.attempts[0].action.recommended_action,
        error: null,
      };
    },
    recordExecution: async () => {
      posts += 1;
      await gate;
      return {
        ...sessionState,
        status: "AWAITING_ATTEMPT",
        attempts: [
          {
            ...sessionState.attempts[0],
            action: {
              ...sessionState.attempts[0].action,
              execution_status: "SUCCEEDED",
            },
          },
        ],
      };
    },
  });
  const first = apply();
  const second = await apply();
  assert.equal(second, null);
  assert.equal(runtimeCalls, 1);
  assert.equal(posts, 1);
  release();
  await first;
  assert.equal(runtimeCalls, 1);
  assert.equal(posts, 1);
});

test("history DOM tampering does not rewrite the session", () => {
  const recorded = session({
    attempts: [
      attempt(0, {
        action_disposition: "ACCEPTED",
        execution_status: "SUCCEEDED",
        executed_action: { action_type: "slow_down", target_rate: 0.75 },
      }),
      attempt(1),
    ],
  });
  const before = JSON.stringify(recorded);
  const restore = withStubDocument();
  try {
    const container = stubElement();
    renderGuidedSessionHistory({ session: recorded, container });
    const list = container.children.find((node) => node.className === "guided-history");
    const [historical, current] = list.children;
    historical.dataset.current = "true";
    historical.dataset.actionable = "true";
    current.dataset.current = "false";
    list.children.reverse();
    historical.listeners?.click?.forEach((fn) => fn());
    assert.equal(JSON.stringify(recorded), before);
    assert.equal(recorded.current_attempt_index, 1);
    assert.equal(recorded.attempts[0].attempt_id, "attempt-0");
    assert.equal(recorded.attempts[1].action.action_disposition, "PENDING");
  } finally {
    restore();
  }
});

test("a malformed historical attempt renders without becoming actionable", () => {
  const recorded = session({
    attempts: [
      { attempt_id: "broken", action: null },
      attempt(1),
    ],
    current_attempt_index: 1,
  });
  const restore = withStubDocument();
  try {
    const container = stubElement();
    assert.doesNotThrow(() => renderGuidedSessionHistory({ session: recorded, container }));
    const list = container.children.find((node) => node.className === "guided-history");
    assert.equal(list.children[0].dataset.actionable, "false");
    assert.equal(list.children[0].dataset.current, "false");
    assert.equal(list.children[1].dataset.current, "true");
    assert.equal(recorded.attempts[1].action.action_disposition, "PENDING");
  } finally {
    restore();
  }
});

test("stage 6 and stage 7 presentation modules do not take each other's authority", () => {
  const strip = (source) =>
    source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  const executor = strip(readFileSync(repoUrl("../guided-action-executor.js"), "utf-8"));
  const history = strip(readFileSync(repoUrl("../guided-session-history.js"), "utf-8"));
  assert.doesNotMatch(executor, /buildTeachingGuidance|choose_primary_next_action|PracticeSessionHistory/);
  assert.match(executor, /action\.action_type !== recommended\.action_type/);
  assert.doesNotMatch(history, /executeGuidedAction|createGuidedApplyHandler|setRate|setLoop/);
  assert.match(executor, /from "\.\/guided_disposition\.js"/);
  assert.equal(
    executor.match(/from "\.\/[^"]+"/g)?.length,
    1,
  );
});
