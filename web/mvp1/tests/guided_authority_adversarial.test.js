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

test("a tampered history DOM cannot redirect the controls onto a finished attempt", async () => {
  // The old version of this only reasserted that a JavaScript object does not
  // change when unrelated DOM is edited, which nothing could have made false.
  // What has to hold is that the *authority path* ignores the DOM: after the
  // markup is rewritten to claim the finished attempt is current, Accept and
  // Apply must still act on the attempt the session says is current.
  const recorded = session({
    attempts: [
      attempt(0, {
        action_disposition: "ACCEPTED",
        execution_status: "SUCCEEDED",
        executed_action: { action_type: "slow_down", target_rate: 0.75 },
      }),
      attempt(1, { recommended_action: { action_type: "repeat" } }),
    ],
  });
  const before = JSON.stringify(recorded);
  const restore = withStubDocument();
  try {
    const container = stubElement();
    renderGuidedSessionHistory({ session: recorded, container });
    const list = container.children.find((node) => node.className === "guided-history");
    const [historical, current] = list.children;

    // Forge the presentation: the finished attempt claims to be current and
    // actionable, the real current attempt claims to be neither, and the
    // rendered order is reversed.
    historical.dataset.current = "true";
    historical.dataset.actionable = "true";
    historical.dataset.execution = "PENDING";
    current.dataset.current = "false";
    current.dataset.actionable = "false";
    list.children.reverse();

    // Authority path 1: the disposition handler. It reads the session, so the
    // request must carry the session id and resolve against attempt 1.
    const api = recordingApi();
    const controller = controllerOn(api, recorded);
    const accept = createGuidanceDispositionHandler({
      guidedSessionApi: api,
      getSessionId: () => controller.activeSession?.session_id ?? null,
      onResolved: (_disposition, next) => {
        controller.session = next;
      },
    });
    await accept("ACCEPTED");
    assert.deepEqual(api.ops(), ["disposition"]);
    assert.equal(api.calls[0].sessionId, "session-do015-adversarial");

    // Authority path 2: Apply. The executed action must be attempt 1's
    // recommendation -- the forged row's slow_down must not be what runs.
    const runtime = [];
    const apply = createGuidedApplyHandler({
      getSession: () => session({
        attempts: [
          recorded.attempts[0],
          attempt(1, {
            recommended_action: { action_type: "repeat" },
            action_disposition: "ACCEPTED",
            execution_status: "PENDING",
          }),
        ],
      }),
      execute: ({ action }) => {
        runtime.push(action.action_type);
        return { status: "SUCCEEDED", executedAction: action, error: null };
      },
      recordExecution: (sessionId, status, executedAction) =>
        api.recordExecution(sessionId, status, executedAction),
    });
    await apply();
    assert.deepEqual(runtime, ["repeat"]);
    const execution = api.calls.find((call) => call.op === "execution");
    assert.equal(execution.executedAction.action_type, "repeat");
    assert.notEqual(execution.executedAction.action_type, "slow_down");

    // And the finished attempt is untouched throughout.
    assert.equal(JSON.stringify(recorded), before);
    assert.equal(recorded.current_attempt_index, 1);
    assert.equal(recorded.attempts[0].action.execution_status, "SUCCEEDED");
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

test("no public history export can make a malformed historical row actionable", async () => {
  // The history module is presentation-only today, so there is no interaction
  // API to attack. Locking the surface is what keeps that true: adding an
  // export fails here, and whoever adds it has to show the guarantee below
  // still holds through it.
  const history = await import("../guided-session-history.js");
  assert.deepEqual(Object.keys(history).sort(), [
    "formatGuidedAttemptNumber",
    "getCurrentGuidedAttemptRow",
    "guidedAttemptRows",
    "isHistoricalGuidedAttempt",
    "renderGuidedSessionHistory",
  ]);

  const recorded = session({
    attempts: [
      { attempt_id: "broken", action: null },
      attempt(1, { action_disposition: "ACCEPTED", execution_status: "PENDING" }),
    ],
    current_attempt_index: 1,
  });
  const before = JSON.stringify(recorded);

  // Every export, against the malformed row: none reports it actionable, none
  // reports it current, and none writes to the session.
  assert.equal(history.isHistoricalGuidedAttempt(recorded, "broken"), true);
  const rows = history.guidedAttemptRows(recorded);
  assert.equal(rows[0].actionable, false);
  assert.equal(rows[0].isCurrent, false);
  assert.equal(rows[0].disposition, null);
  assert.equal(rows[0].execution, null);
  assert.equal(history.getCurrentGuidedAttemptRow(recorded).attemptId, "attempt-1");
  assert.equal(history.formatGuidedAttemptNumber(0), "Attempt 1");

  const restore = withStubDocument();
  try {
    const container = stubElement();
    history.renderGuidedSessionHistory({ session: recorded, container });
    const list = container.children.find((node) => node.className === "guided-history");
    assert.equal(list.children[0].dataset.actionable, "false");
    // Mutating the row a renderer produced changes nothing about the answer:
    // ask again and it is still not actionable.
    list.children[0].dataset.actionable = "true";
    assert.equal(history.guidedAttemptRows(recorded)[0].actionable, false);
  } finally {
    restore();
  }
  assert.equal(JSON.stringify(recorded), before);
});

test("the history module exports nothing that could act on a session", () => {
  const source = readFileSync(repoUrl("../guided-session-history.js"), "utf-8");
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  // A future interaction API would arrive as one of these. None is here, and
  // this is the line that has to be argued with before one is.
  assert.doesNotMatch(code, /addEventListener|onclick|dispatchEvent/);
  assert.doesNotMatch(code, /async function|await |fetch\(/);
  assert.doesNotMatch(code, /session\.[\w.]+\s*=[^=]|attempts\[[^\]]*\]\s*=[^=]/);
  const exported = code.match(/^export (?:function|const|class) (\w+)/gm) || [];
  assert.equal(exported.length, 5, exported.join(", "));
});
