import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  GUIDED_SESSION_API_PREFIX,
  LocalGuidedSessionApi,
} from "../guided_session_api.js";

const repoUrl = (path) => fileURLToPath(new URL(path, import.meta.url));

function fakeFetch(handler) {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url, options });
    return handler(url, options);
  };
  return { calls, fetchImpl };
}

function jsonResponse(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 || status === 201 ? "OK" : "Error",
    json: async () => payload,
  };
}

test("create posts caller-supplied ids and evidence to the Stage 4 prefix", async () => {
  const { calls, fetchImpl } = fakeFetch(() =>
    jsonResponse(201, { session_id: "session-1", status: "AWAITING_ACTION" }),
  );
  const api = new LocalGuidedSessionApi({ fetchImpl });
  const session = await api.create({
    sessionId: "session-1",
    attemptId: "attempt-1",
    evaluation: { evaluation_digest: "sha256:e" },
    guidance: { guidance_digest: "sha256:g" },
  });
  assert.equal(session.session_id, "session-1");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `${GUIDED_SESSION_API_PREFIX}`);
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    session_id: "session-1",
    attempt_id: "attempt-1",
    evaluation: { evaluation_digest: "sha256:e" },
    guidance: { guidance_digest: "sha256:g" },
  });
});

test("recordDisposition posts ACCEPTED or DECLINED only", async () => {
  const { calls, fetchImpl } = fakeFetch(() =>
    jsonResponse(200, {
      session_id: "session-1",
      attempts: [
        { action: { action_disposition: "ACCEPTED", execution_status: "PENDING" } },
      ],
    }),
  );
  const api = new LocalGuidedSessionApi({ fetchImpl });
  await api.recordDisposition("session-1", "ACCEPTED");
  assert.equal(calls[0].url, `${GUIDED_SESSION_API_PREFIX}/session-1/disposition`);
  assert.deepEqual(JSON.parse(calls[0].options.body), { disposition: "ACCEPTED" });
});

test("recordExecution posts the Stage 4 execution payload", async () => {
  const recommended = {
    action_type: "slow_down",
    target_rate: 0.5,
    message_key: "action.slow_down",
  };
  const { calls, fetchImpl } = fakeFetch(() =>
    jsonResponse(200, {
      session_id: "session-1",
      status: "AWAITING_ATTEMPT",
      attempts: [
        {
          action: {
            action_disposition: "ACCEPTED",
            execution_status: "SUCCEEDED",
            executed_action: recommended,
          },
        },
      ],
    }),
  );
  const api = new LocalGuidedSessionApi({ fetchImpl });
  await api.recordExecution("session-1", "SUCCEEDED", recommended);
  assert.equal(calls[0].url, `${GUIDED_SESSION_API_PREFIX}/session-1/execution`);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    execution_status: "SUCCEEDED",
    executed_action: recommended,
  });
});

test("recordExecution posts null executed_action for UNSUPPORTED", async () => {
  const { calls, fetchImpl } = fakeFetch(() =>
    jsonResponse(200, {
      session_id: "session-1",
      attempts: [
        { action: { action_disposition: "ACCEPTED", execution_status: "UNSUPPORTED" } },
      ],
    }),
  );
  const api = new LocalGuidedSessionApi({ fetchImpl });
  await api.recordExecution("session-1", "UNSUPPORTED", null);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    execution_status: "UNSUPPORTED",
    executed_action: null,
  });
});

test("client source does not mention Transport or apply_action", () => {
  const source = readFileSync(repoUrl("../guided_session_api.js"), "utf-8");
  for (const token of ["setRate", "setLoop", "apply_action", "practiceActions"]) {
    assert.doesNotMatch(source, new RegExp(token));
  }
});
