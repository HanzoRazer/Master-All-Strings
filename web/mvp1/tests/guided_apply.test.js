import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { createGuidanceDispositionHandler } from "../guided_disposition.js";
import { createGuidedApplyHandler, executeGuidedAction } from "../guided-action-executor.js";
import { PracticeActionController } from "../practice_actions.js";
import { executionCopy, renderResultsPanel } from "../results.js";
import { stubElement, withStubDocument } from "./dom_stub.js";
import { resolveFocusRangeSeconds, secondsAtTick } from "../teaching-timeline.js";
import { Transport } from "../transport.js";

const repoUrl = (path) => fileURLToPath(new URL(path, import.meta.url));

const ANCHORS = [
  { schema_version: "1.0.0", tick: 0, seconds: 0.0 },
  { schema_version: "1.0.0", tick: 8640, seconds: 4.5 },
];

function acceptedSession(recommended, overrides = {}) {
  return {
    session_id: "session-do015-apply",
    status: "AWAITING_ACTION",
    canonical_revision_id: "revision-do015-001",
    current_attempt_index: 0,
    attempts: [
      {
        attempt_id: "attempt-0",
        canonical_revision_id: "revision-do015-001",
        performance_session_id: "performance-session-0",
        evaluation_digest: "sha256:eval",
        guidance_digest: "sha256:guide",
        action: {
          recommended_action: recommended,
          action_disposition: "ACCEPTED",
          execution_status: "PENDING",
          executed_action: null,
        },
      },
    ],
    ...overrides,
  };
}

const SLOW_DOWN = {
  action_type: "slow_down",
  target_rate: 0.5,
  message_key: "action.slow_down",
  reason_finding_ids: ["finding-1"],
};
const ISOLATE = {
  action_type: "isolate_passage",
  focus_start_tick: 1920,
  focus_end_tick: 3840,
  message_key: "action.isolate_passage",
};
const CONTINUE = { action_type: "continue", message_key: "action.continue" };
const VIEW_ONE = { action_type: "view_one_string", message_key: "action.view_one_string" };

function spyTransport() {
  const transport = new Transport();
  transport.setDuration(4.5);
  const order = [];
  const originalRate = transport.setRate.bind(transport);
  const originalLoop = transport.setLoop.bind(transport);
  transport.setRate = (...args) => {
    order.push({ seam: "setRate", args });
    return originalRate(...args);
  };
  transport.setLoop = (...args) => {
    order.push({ seam: "setLoop", args });
    return originalLoop(...args);
  };
  return { transport, order };
}

function applyHarness({
  recommended = SLOW_DOWN,
  sessionOverrides = {},
  record = null,
  execute = executeGuidedAction,
  getRuntime = null,
} = {}) {
  const { transport, order } = spyTransport();
  const actions = new PracticeActionController({
    transport,
    resolveFocusRange: (startTick, endTick) =>
      resolveFocusRangeSeconds(ANCHORS, startTick, endTick),
  });
  let session = acceptedSession(recommended, sessionOverrides);
  const posts = [];
  const diagnostics = [];
  const apply = createGuidedApplyHandler({
    getSession: () => session,
    setSession: (next) => {
      session = next;
    },
    execute,
    recordExecution: async (sessionId, executionStatus, executedAction) => {
      order.push({ seam: "recordExecution", executionStatus, executedAction });
      posts.push({ sessionId, executionStatus, executedAction });
      if (typeof record === "function") {
        return record(sessionId, executionStatus, executedAction, session);
      }
      return {
        ...session,
        status:
          recommended.action_type === "continue" && executionStatus === "SUCCEEDED"
            ? "CLOSED"
            : "AWAITING_ATTEMPT",
        attempts: [
          {
            ...session.attempts[0],
            canonical_revision_id: session.attempts[0].canonical_revision_id,
            performance_session_id: session.attempts[0].performance_session_id,
            evaluation_digest: session.attempts[0].evaluation_digest,
            guidance_digest: session.attempts[0].guidance_digest,
            action: {
              ...session.attempts[0].action,
              execution_status: executionStatus,
              executed_action: executedAction,
            },
          },
        ],
      };
    },
    getRuntime:
      getRuntime ||
      (() => ({
        transport,
        applySlowDown: (action) => actions.applySlowDown(action),
        applyIsolatePassage: (action) => actions.applyIsolatePassage(action),
      })),
    onDiagnostics: (item) => diagnostics.push(item),
  });
  return { apply, getSession: () => session, transport, order, posts, diagnostics, actions };
}

test("Apply is a no-op before acceptance: no runtime and no execution POST", async () => {
  const harness = applyHarness({
    sessionOverrides: {
      attempts: [
        {
          attempt_id: "attempt-0",
          action: {
            recommended_action: SLOW_DOWN,
            action_disposition: "PENDING",
            execution_status: "NOT_REQUESTED",
          },
        },
      ],
    },
  });
  const result = await harness.apply();
  assert.equal(result, null);
  assert.deepEqual(harness.posts, []);
  assert.equal(harness.transport.playbackRate, 1);
  assert.equal(
    harness.order.some((item) => item.seam === "setRate" || item.seam === "recordExecution"),
    false,
  );
});

test("declined actions cannot apply", async () => {
  const harness = applyHarness({
    sessionOverrides: {
      status: "AWAITING_ATTEMPT",
      attempts: [
        {
          attempt_id: "attempt-0",
          action: {
            recommended_action: SLOW_DOWN,
            action_disposition: "DECLINED",
            execution_status: "NOT_REQUESTED",
          },
        },
      ],
    },
  });
  await harness.apply();
  assert.deepEqual(harness.posts, []);
  assert.equal(harness.transport.playbackRate, 1);
});

test("runtime mutation precedes SUCCEEDED evidence POST", async () => {
  const harness = applyHarness();
  const session = await harness.apply();
  assert.deepEqual(
    harness.order.map((item) => item.seam),
    ["setRate", "recordExecution"],
  );
  assert.equal(harness.posts[0].executionStatus, "SUCCEEDED");
  assert.equal(harness.posts[0].executedAction.action_type, "slow_down");
  assert.equal(harness.posts[0].executedAction.target_rate, 0.5);
  assert.equal(session.status, "AWAITING_ATTEMPT");
  assert.equal(session.attempts[0].action.execution_status, "SUCCEEDED");
  assert.equal(harness.transport.playbackRate, 0.5);
});

test("runtime failure posts FAILED and never SUCCEEDED", async () => {
  const harness = applyHarness({
    execute: () => ({
      status: "FAILED",
      executedAction: SLOW_DOWN,
      error: "rate seam refused",
    }),
  });
  const session = await harness.apply();
  assert.equal(harness.posts.length, 1);
  assert.equal(harness.posts[0].executionStatus, "FAILED");
  assert.equal(
    harness.posts.filter((post) => post.executionStatus === "SUCCEEDED").length,
    0,
  );
  assert.equal(session.attempts[0].action.action_disposition, "ACCEPTED");
  assert.equal(session.attempts[0].action.execution_status, "FAILED");
});

test("a second Apply after final execution does not run runtime or POST", async () => {
  const harness = applyHarness();
  await harness.apply();
  const afterFirst = harness.order.length;
  const afterFirstPosts = harness.posts.length;
  await harness.apply();
  assert.equal(harness.order.length, afterFirst);
  assert.equal(harness.posts.length, afterFirstPosts);
  assert.equal(harness.transport.playbackRate, 0.5);
});

test("runtime success with evidence write failure is reported honestly", async () => {
  const harness = applyHarness({
    record: async () => {
      throw new Error("guided session store unavailable");
    },
  });
  const before = harness.getSession();
  const result = await harness.apply();
  assert.equal(result, null);
  assert.equal(harness.getSession(), before);
  assert.equal(harness.getSession().attempts[0].action.execution_status, "PENDING");
  assert.equal(harness.transport.playbackRate, 0.5);
  const last = harness.diagnostics[harness.diagnostics.length - 1];
  assert.equal(last.runtimeStatus, "SUCCEEDED");
  assert.equal(last.evidenceStatus, "FAILED");
  await harness.apply();
  assert.equal(harness.posts.length, 1);
  assert.equal(harness.order.filter((item) => item.seam === "setRate").length, 1);
});

test("CONTINUE close status comes from the server response", async () => {
  const harness = applyHarness({ recommended: CONTINUE });
  const session = await harness.apply();
  assert.equal(session.status, "CLOSED");
  assert.equal(harness.transport.playbackRate, 1);
  assert.equal(harness.transport.loop, null);
  assert.equal(
    harness.order.some((item) => item.seam === "setRate" || item.seam === "setLoop"),
    false,
  );
});

test("VIEW_ONE_STRING records UNSUPPORTED with a null executed_action", async () => {
  const harness = applyHarness({ recommended: VIEW_ONE });
  const session = await harness.apply();
  assert.equal(harness.posts[0].executionStatus, "UNSUPPORTED");
  assert.equal(harness.posts[0].executedAction, null);
  assert.equal(session.attempts[0].action.execution_status, "UNSUPPORTED");
  assert.equal(harness.transport.playbackRate, 1);
  assert.equal(harness.transport.loop, null);
});

test("ISOLATE_PASSAGE uses secondsAtTick of the recommended ticks only", async () => {
  const harness = applyHarness({ recommended: ISOLATE });
  const session = await harness.apply();
  const loopEvent = harness.order.find((item) => item.seam === "setLoop");
  assert.ok(loopEvent);
  assert.equal(loopEvent.args[0].startSeconds, secondsAtTick(ANCHORS, 1920));
  assert.equal(loopEvent.args[0].endSeconds, secondsAtTick(ANCHORS, 3840));
  assert.ok(harness.order.findIndex((item) => item.seam === "setLoop") <
    harness.order.findIndex((item) => item.seam === "recordExecution"));
  assert.equal(session.status, "AWAITING_ATTEMPT");
});

test("execution preserves evidence identities", async () => {
  const harness = applyHarness();
  const before = harness.getSession();
  const session = await harness.apply();
  assert.equal(session.canonical_revision_id, before.canonical_revision_id);
  assert.equal(
    session.attempts[0].performance_session_id,
    before.attempts[0].performance_session_id,
  );
  assert.equal(session.attempts[0].evaluation_digest, before.attempts[0].evaluation_digest);
  assert.equal(session.attempts[0].guidance_digest, before.attempts[0].guidance_digest);
});

test("rendered session status is the server value, not a client inference", async () => {
  const harness = applyHarness({
    record: async (_id, executionStatus, executedAction, session) => ({
      ...session,
      status: "UNEXPECTED_FROM_SERVER",
      attempts: [
        {
          ...session.attempts[0],
          action: {
            ...session.attempts[0].action,
            execution_status: executionStatus,
            executed_action: executedAction,
          },
        },
      ],
    }),
  });
  const session = await harness.apply();
  assert.equal(session.status, "UNEXPECTED_FROM_SERVER");
  const restore = withStubDocument();
  try {
    const root = stubElement();
    renderResultsPanel(
      root,
      {
        evaluation: {
          findings: [],
          summary: { actionable_finding_count: 0 },
          primary_next_action: { action_type: "slow_down", message_key: "action.slow_down" },
        },
        messages: { "action.slow_down": "Slow down" },
      },
      session,
    );
    assert.equal(root.children[0].dataset.sessionStatus, "UNEXPECTED_FROM_SERVER");
    assert.equal(executionCopy(session), "Applied");
  } finally {
    restore();
  }
});

test("Accept still posts disposition without Transport or execution", async () => {
  const transport = new Transport();
  const calls = [];
  const accept = createGuidanceDispositionHandler({
    guidedSessionApi: {
      recordDisposition: async (sessionId, disposition) => {
        calls.push({ sessionId, disposition });
        return acceptedSession(SLOW_DOWN, { session_id: sessionId });
      },
      recordExecution: async () => {
        throw new Error("execution must not run on accept");
      },
    },
    getSessionId: () => "session-do015-accept",
  });
  await accept("ACCEPTED");
  assert.deepEqual(calls, [{ sessionId: "session-do015-accept", disposition: "ACCEPTED" }]);
  assert.equal(transport.playbackRate, 1);
  assert.equal(transport.loop, null);
});

test("executor and app still do not convert ticks themselves", () => {
  const executor = readFileSync(repoUrl("../guided-action-executor.js"), "utf-8");
  const app = readFileSync(repoUrl("../app.js"), "utf-8");
  assert.doesNotMatch(executor, /secondsAtTick/);
  assert.doesNotMatch(executor, /tickAtSeconds/);
  assert.equal((app.match(/secondsAtTick/g) || []).length, 2);
  assert.doesNotMatch(executor, /SUPPORTED_PRACTICE_RATES/);
  assert.doesNotMatch(app, /practiceActions\.apply\(/);
});
