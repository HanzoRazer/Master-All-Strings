import assert from "node:assert/strict";
import test from "node:test";

import {
  LESSON_PRACTICE_ATTEMPT_CANCELLATION_PATH,
  LESSON_PRACTICE_ATTEMPT_FINISH_PATH,
  LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH,
  LESSON_PRACTICE_ATTEMPT_PATH,
  ReceivedAttemptClient,
} from "../received_attempt_client.js";

function response(status, body, ok = status >= 200 && status < 300) {
  return {
    ok,
    status,
    async text() {
      return body == null ? "" : JSON.stringify(body);
    },
  };
}

function install(handler) {
  const calls = [];
  const client = new ReceivedAttemptClient({
    base: "http://127.0.0.1:9/",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return handler(url, init, calls);
    },
  });
  return { client, calls };
}

test("the four attempt routes are the only paths", () => {
  assert.equal(LESSON_PRACTICE_ATTEMPT_PATH, "/api/education/lesson-practice-attempts");
  assert.equal(
    LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH,
    "/api/education/lesson-practice-attempt-messages",
  );
  assert.equal(
    LESSON_PRACTICE_ATTEMPT_FINISH_PATH,
    "/api/education/lesson-practice-attempt-finishes",
  );
  assert.equal(
    LESSON_PRACTICE_ATTEMPT_CANCELLATION_PATH,
    "/api/education/lesson-practice-attempt-cancellations",
  );
});

test("begin, append, finish, and cancel post the Stage 7 bodies", async () => {
  const { client, calls } = install(() => response(201, { attempt_id: "a-1" }));
  const begun = await client.begin({
    deliveryId: "delivery-001",
    artifactDigest: "sha256:aa",
    behaviorDigest: "sha256:bb",
    deviceId: "Keyboard",
    captureTimeNs: 15,
  });
  assert.equal(begun.ok, true);
  assert.equal(begun.status, 201);
  assert.equal(calls[0].url, `http://127.0.0.1:9${LESSON_PRACTICE_ATTEMPT_PATH}`);
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.keepalive, false);
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    delivery_id: "delivery-001",
    expected_assignment_artifact_digest: "sha256:aa",
    expected_assignment_behavior_digest: "sha256:bb",
    device_id: "Keyboard",
    capture_time_ns: 15,
  });

  const { client: messages, calls: messageCalls } = install(() => response(200, { ok: true }));
  await messages.append({
    attemptId: "a-1",
    sequenceNumber: 0,
    captureTimeNs: 20,
    practicePositionSeconds: 0.25,
    rawPayload: [0x90, 64, 80],
  });
  await messages.finish({ attemptId: "a-1", captureTimeNs: 30 });
  await messages.cancel({ attemptId: "a-1", captureTimeNs: 40, keepalive: true });
  assert.deepEqual(messageCalls.map((call) => call.url.split("/").at(-1)), [
    "lesson-practice-attempt-messages",
    "lesson-practice-attempt-finishes",
    "lesson-practice-attempt-cancellations",
  ]);
  assert.deepEqual(JSON.parse(messageCalls[0].init.body), {
    attempt_id: "a-1",
    sequence_number: 0,
    capture_time_ns: 20,
    practice_position_seconds: 0.25,
    raw_payload: [144, 64, 80],
  });
  assert.equal(messageCalls[0].init.keepalive, false);
  assert.equal(messageCalls[1].init.keepalive, false);
  assert.equal(messageCalls[2].init.keepalive, true);
  assert.deepEqual(JSON.parse(messageCalls[2].init.body), {
    attempt_id: "a-1",
    capture_time_ns: 40,
  });
});

test("transport failures and unusable bodies stay closed", async () => {
  const thrown = install(() => {
    throw new Error("socket");
  });
  const failed = await thrown.client.begin({
    deliveryId: "d",
    artifactDigest: "a",
    behaviorDigest: "b",
    deviceId: "k",
    captureTimeNs: 1,
  });
  assert.deepEqual(failed, { ok: false, status: 0, error: null, body: null });

  const rejected = install(() => response(409, { error: "sequence_conflict" }, false));
  const conflict = await rejected.client.append({
    attemptId: "a",
    sequenceNumber: 1,
    captureTimeNs: 2,
    practicePositionSeconds: 0,
    rawPayload: [0x80, 64, 0],
  });
  assert.equal(conflict.ok, false);
  assert.equal(conflict.status, 409);
  assert.equal(conflict.error, "sequence_conflict");
  assert.equal(conflict.body, null);

  const arrayBody = install(() => ({
    ok: true,
    status: 200,
    async text() {
      return "[1]";
    },
  }));
  const unusable = await arrayBody.client.finish({ attemptId: "a", captureTimeNs: 3 });
  assert.equal(unusable.ok, false);
  assert.equal(unusable.body, null);

  const empty = install(() => ({
    ok: true,
    status: 200,
    async text() {
      return "";
    },
  }));
  const blank = await empty.client.cancel({ attemptId: "a", captureTimeNs: 4 });
  assert.equal(blank.ok, false);
  assert.equal(blank.status, 200);
});
