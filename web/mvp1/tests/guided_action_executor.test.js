import assert from "node:assert/strict";
import test from "node:test";

import { canApplyGuidedAction } from "../guided_disposition.js";
import {
  applyControlState,
  createGuidedApplyHandler,
  executeGuidedAction,
} from "../guided-action-executor.js";
import { PracticeActionController } from "../practice_actions.js";
import { resolveFocusRangeSeconds, secondsAtTick } from "../teaching-timeline.js";
import { Transport } from "../transport.js";

const ANCHORS = [
  { schema_version: "1.0.0", tick: 0, seconds: 0.0 },
  { schema_version: "1.0.0", tick: 8640, seconds: 4.5 },
];

function acceptedSession(recommended, overrides = {}) {
  return {
    session_id: "session-do015-exec",
    status: "AWAITING_ACTION",
    canonical_revision_id: "revision-do015-001",
    current_attempt_index: 0,
    attempts: [
      {
        attempt_id: "attempt-0",
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

function pendingSession(recommended = { action_type: "slow_down", target_rate: 0.75 }) {
  return acceptedSession(recommended, {
    attempts: [
      {
        attempt_id: "attempt-0",
        action: {
          recommended_action: recommended,
          action_disposition: "PENDING",
          execution_status: "NOT_REQUESTED",
        },
      },
    ],
  });
}

function declinedSession(recommended = { action_type: "slow_down", target_rate: 0.75 }) {
  return acceptedSession(recommended, {
    status: "AWAITING_ATTEMPT",
    attempts: [
      {
        attempt_id: "attempt-0",
        action: {
          recommended_action: recommended,
          action_disposition: "DECLINED",
          execution_status: "NOT_REQUESTED",
        },
      },
    ],
  });
}

function isolateController() {
  const transport = new Transport();
  transport.setDuration(4.5);
  const tickCalls = [];
  const actions = new PracticeActionController({
    transport,
    resolveFocusRange: (startTick, endTick) => {
      tickCalls.push([startTick, endTick]);
      return resolveFocusRangeSeconds(ANCHORS, startTick, endTick);
    },
    targetRepetitions: () => 3,
  });
  return { transport, actions, tickCalls };
}

const SLOW_DOWN = {
  action_type: "slow_down",
  target_rate: 0.5,
  message_key: "action.slow_down",
};

const ISOLATE = {
  action_type: "isolate_passage",
  focus_start_tick: 1920,
  focus_end_tick: 3840,
  message_key: "action.isolate_passage",
};

const REPEAT = { action_type: "repeat", message_key: "action.repeat" };
const CONTINUE = { action_type: "continue", message_key: "action.continue" };
const VIEW_ONE = { action_type: "view_one_string", message_key: "action.view_one_string" };
const ZONE = { action_type: "enable_zone_view", message_key: "action.enable_zone_view" };

test("SLOW_DOWN uses the exact recommended target on the existing rate seam", () => {
  const transport = new Transport();
  const rates = [];
  const original = transport.setRate.bind(transport);
  transport.setRate = (rate, ...rest) => {
    rates.push(rate);
    return original(rate, ...rest);
  };
  const result = executeGuidedAction({
    session: acceptedSession(SLOW_DOWN),
    action: SLOW_DOWN,
    transport,
  });
  assert.equal(result.status, "SUCCEEDED");
  assert.equal(result.executedAction.action_type, "slow_down");
  assert.equal(result.executedAction.target_rate, 0.5);
  assert.deepEqual(rates, [0.5]);
  assert.equal(transport.playbackRate, 0.5);
  assert.equal(transport.loop, null);
});

test("SLOW_DOWN does not invent a rate when target_rate is missing", () => {
  const transport = new Transport();
  const session = acceptedSession({ action_type: "slow_down", message_key: "action.slow_down" });
  const result = executeGuidedAction({ session, transport });
  assert.equal(result.status, "FAILED");
  assert.equal(transport.playbackRate, 1);
  assert.match(result.error, /target_rate/);
});

test("SLOW_DOWN runtime failure does not claim success", () => {
  const transport = new Transport();
  transport.setRate = () => {
    throw new Error("rate seam refused");
  };
  const result = executeGuidedAction({
    session: acceptedSession(SLOW_DOWN),
    transport,
  });
  assert.equal(result.status, "FAILED");
  assert.match(result.error, /rate seam refused/);
  assert.equal(result.executedAction.action_type, "slow_down");
});

test("ISOLATE_PASSAGE feeds authoritative ticks through secondsAtTick into setLoop", () => {
  const { transport, actions, tickCalls } = isolateController();
  const expectedStart = secondsAtTick(ANCHORS, 1920);
  const expectedEnd = secondsAtTick(ANCHORS, 3840);
  const result = executeGuidedAction({
    session: acceptedSession(ISOLATE),
    action: ISOLATE,
    transport,
    applyIsolatePassage: (action) => actions.applyIsolatePassage(action),
  });
  assert.equal(result.status, "SUCCEEDED");
  assert.deepEqual(tickCalls, [[1920, 3840]]);
  assert.equal(transport.loop.startSeconds, expectedStart);
  assert.equal(transport.loop.endSeconds, expectedEnd);
  assert.equal(transport.loop.targetRepetitions, 3);
  assert.equal(transport.playbackRate, 1);
});

test("ISOLATE_PASSAGE loop bounds ignore selection and notation focus", () => {
  const { transport, actions, tickCalls } = isolateController();
  const selection = { selectedEventId: "ev-other", tabFocus: "measure-9", notation: "bar-2" };
  void selection;
  executeGuidedAction({
    session: acceptedSession(ISOLATE),
    action: ISOLATE,
    transport,
    applyIsolatePassage: (action) => actions.applyIsolatePassage(action),
  });
  const first = { ...transport.loop };
  const { transport: transport2, actions: actions2, tickCalls: tickCalls2 } = isolateController();
  executeGuidedAction({
    session: acceptedSession(ISOLATE),
    action: ISOLATE,
    transport: transport2,
    applyIsolatePassage: (action) => actions2.applyIsolatePassage(action),
  });
  assert.deepEqual(tickCalls, tickCalls2);
  assert.equal(transport2.loop.startSeconds, first.startSeconds);
  assert.equal(transport2.loop.endSeconds, first.endSeconds);
});

test("ISOLATE_PASSAGE runtime failure is FAILED", () => {
  const transport = new Transport();
  const result = executeGuidedAction({
    session: acceptedSession(ISOLATE),
    transport,
    applyIsolatePassage: () => false,
  });
  assert.equal(result.status, "FAILED");
  assert.equal(transport.loop, null);
});

test("REPEAT succeeds without changing rate, loop, or starting capture", () => {
  const transport = new Transport();
  transport.setRate(0.75);
  transport.setDuration(4);
  transport.setLoop({ startSeconds: 0, endSeconds: 2 });
  const capture = {
    startAttemptCalls: 0,
    async startAttempt() {
      this.startAttemptCalls += 1;
    },
  };
  const rateCalls = [];
  const loopCalls = [];
  const originalRate = transport.setRate.bind(transport);
  const originalLoop = transport.setLoop.bind(transport);
  transport.setRate = (...args) => {
    rateCalls.push(args);
    return originalRate(...args);
  };
  transport.setLoop = (...args) => {
    loopCalls.push(args);
    return originalLoop(...args);
  };
  const result = executeGuidedAction({
    session: acceptedSession(REPEAT),
    transport,
    capture,
  });
  assert.equal(result.status, "SUCCEEDED");
  assert.equal(result.executedAction.action_type, "repeat");
  assert.equal(transport.playbackRate, 0.75);
  assert.equal(transport.loop.startSeconds, 0);
  assert.equal(transport.loop.endSeconds, 2);
  assert.deepEqual(rateCalls, []);
  assert.deepEqual(loopCalls, []);
  assert.equal(capture.startAttemptCalls, 0);
});

test("CONTINUE succeeds without mutating Transport or closing locally", () => {
  const transport = new Transport();
  const session = acceptedSession(CONTINUE);
  const result = executeGuidedAction({ session, transport });
  assert.equal(result.status, "SUCCEEDED");
  assert.equal(result.executedAction.action_type, "continue");
  assert.equal(transport.playbackRate, 1);
  assert.equal(transport.loop, null);
  assert.equal(session.status, "AWAITING_ACTION");
});

test("VIEW_ONE_STRING is UNSUPPORTED and does not mutate runtime", () => {
  const transport = new Transport();
  const rates = [];
  transport.setRate = (...args) => rates.push(args);
  const result = executeGuidedAction({
    session: acceptedSession(VIEW_ONE),
    transport,
    applyIsolatePassage: () => {
      throw new Error("should not isolate");
    },
  });
  assert.equal(result.status, "UNSUPPORTED");
  assert.equal(result.executedAction, null);
  assert.deepEqual(rates, []);
  assert.equal(transport.loop, null);
});

test("ENABLE_ZONE_VIEW is UNSUPPORTED and does not mutate runtime", () => {
  const transport = new Transport();
  const result = executeGuidedAction({
    session: acceptedSession(ZONE),
    transport,
    applyIsolatePassage: () => true,
  });
  assert.equal(result.status, "UNSUPPORTED");
  assert.equal(result.executedAction, null);
  assert.equal(transport.loop, null);
  assert.equal(transport.playbackRate, 1);
});

test("execution is refused before acceptance", () => {
  const transport = new Transport();
  const result = executeGuidedAction({
    session: pendingSession(SLOW_DOWN),
    transport,
  });
  assert.equal(canApplyGuidedAction(pendingSession(SLOW_DOWN)), false);
  assert.equal(result.status, "FAILED");
  assert.equal(transport.playbackRate, 1);
});

test("declined actions cannot execute", () => {
  const transport = new Transport();
  const result = executeGuidedAction({
    session: declinedSession(SLOW_DOWN),
    transport,
  });
  assert.equal(result.status, "FAILED");
  assert.equal(transport.playbackRate, 1);
});

test("a substituted action_type is refused", () => {
  const transport = new Transport();
  const result = executeGuidedAction({
    session: acceptedSession(ISOLATE),
    action: REPEAT,
    transport,
  });
  assert.equal(result.status, "FAILED");
  assert.equal(transport.loop, null);
  assert.match(result.error, /must match/);
});

test("Apply control is enabled only for ACCEPTED / PENDING", () => {
  assert.equal(applyControlState(pendingSession()).applyDisabled, true);
  assert.equal(applyControlState(pendingSession()).applyHidden, true);
  assert.equal(applyControlState(declinedSession()).applyDisabled, true);
  const ready = applyControlState(acceptedSession(SLOW_DOWN));
  assert.equal(ready.applyDisabled, false);
  assert.equal(ready.applyHidden, false);
  const done = applyControlState(
    acceptedSession(SLOW_DOWN, {
      attempts: [
        {
          attempt_id: "attempt-0",
          action: {
            recommended_action: SLOW_DOWN,
            action_disposition: "ACCEPTED",
            execution_status: "SUCCEEDED",
          },
        },
      ],
    }),
  );
  assert.equal(done.applyDisabled, true);
  assert.equal(done.applyHidden, false);
});

test("createGuidedApplyHandler is exported for integration wiring", () => {
  assert.equal(typeof createGuidedApplyHandler, "function");
});
