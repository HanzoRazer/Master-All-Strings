import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  LESSON_DELIVERY_LIST_PATH,
  LESSON_DELIVERY_PREVIEW_PATH,
  LESSON_PRACTICE_CHOICE_PATH,
  LESSON_PRACTICE_PREPARATION_PATH,
  LessonDeliveryClient,
  lessonDeliveryQuery,
} from "../lesson_delivery_client.js";

const source = readFileSync(
  fileURLToPath(new URL("../lesson_delivery_client.js", import.meta.url)),
  "utf8",
);

function fakeFetch(handler) {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url, options });
    return handler(url, options);
  };
  return { calls, fetchImpl };
}

function jsonResponse(status, payload) {
  const text = JSON.stringify(payload);
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
  };
}

function textResponse(status, text) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
  };
}

test("list GETs the delivery collection and no query", async () => {
  const { calls, fetchImpl } = fakeFetch(() =>
    jsonResponse(200, { recipient_ref: null, count: 0, deliveries: [] }),
  );
  const client = new LessonDeliveryClient({ fetchImpl });
  const result = await client.list();
  assert.equal(result.ok, true);
  assert.equal(result.status, 200);
  assert.equal(result.error, null);
  assert.deepEqual(result.body.deliveries, []);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, LESSON_DELIVERY_LIST_PATH);
  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[0].options.body, undefined);
  assert.equal(calls[0].url.includes("?"), false);
});

test("preview and choice GET encode the delivery id once", async () => {
  const ids = ["100%", "a/b", "a b", "a#b", "a?b", "a&b", "a%2Fb"];
  const expected = [
    "100%25",
    "a%2Fb",
    "a%20b",
    "a%23b",
    "a%3Fb",
    "a%26b",
    "a%252Fb",
  ];
  for (let index = 0; index < ids.length; index += 1) {
    const id = ids[index];
    const encoded = expected[index];
    const { calls, fetchImpl } = fakeFetch(() => jsonResponse(200, { delivery_id: id }));
    const client = new LessonDeliveryClient({ fetchImpl });
    await client.preview(id);
    await client.getChoice(id);
    assert.equal(
      calls[0].url,
      lessonDeliveryQuery(LESSON_DELIVERY_PREVIEW_PATH, id),
    );
    assert.equal(calls[0].url, `${LESSON_DELIVERY_PREVIEW_PATH}?delivery_id=${encoded}`);
    assert.equal(
      calls[1].url,
      `${LESSON_PRACTICE_CHOICE_PATH}?delivery_id=${encoded}`,
    );
    assert.equal(calls[0].options.method, "GET");
    assert.equal(calls[1].options.method, "GET");
  }
});

test("choose POSTs the three body fields and no query", async () => {
  const id = "a%2Fb";
  const artifact = `sha256:${"ab".repeat(32)}`;
  const behavior = `sha256:${"cd".repeat(32)}`;
  const { calls, fetchImpl } = fakeFetch(() =>
    jsonResponse(201, { choice_status: "CHOSEN_FOR_PRACTICE", delivery_id: id }),
  );
  const client = new LessonDeliveryClient({ fetchImpl });
  const result = await client.choose(id, artifact, behavior);
  assert.equal(result.ok, true);
  assert.equal(result.status, 201);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, LESSON_PRACTICE_CHOICE_PATH);
  assert.equal(calls[0].url.includes("?"), false);
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers["content-type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    delivery_id: id,
    expected_assignment_artifact_digest: artifact,
    expected_assignment_behavior_digest: behavior,
  });
});

test("a base prefix is joined without a second encoding", async () => {
  const { calls, fetchImpl } = fakeFetch(() => jsonResponse(200, { deliveries: [] }));
  const client = new LessonDeliveryClient({
    base: "http://127.0.0.1:8765/",
    fetchImpl,
  });
  await client.preview("a b");
  assert.equal(
    calls[0].url,
    `http://127.0.0.1:8765${LESSON_DELIVERY_PREVIEW_PATH}?delivery_id=a%20b`,
  );
});

test("public error codes survive and extra fields do not", async () => {
  const cases = [
    [404, "unknown_practice_choice"],
    [404, "unknown_delivery_id"],
    [409, "integrity_mismatch"],
    [409, "stale_preview"],
    [409, "choice_conflict"],
    [422, "unresolvable_assignment"],
    [500, "internal server error"],
  ];
  for (const [status, error] of cases) {
    const { fetchImpl } = fakeFetch(() =>
      jsonResponse(status, {
        error,
        title: "PARTIAL_TITLE",
        detail: "INTERNAL_EXCEPTION_TEXT",
        assignment_artifact_digest: `sha256:${"ab".repeat(32)}`,
      }),
    );
    const client = new LessonDeliveryClient({ fetchImpl });
    const result = await client.preview("delivery-001");
    assert.equal(result.ok, false);
    assert.equal(result.status, status);
    assert.equal(result.error, error);
    assert.equal(result.body, null);
    assert.equal(JSON.stringify(result).includes("PARTIAL_TITLE"), false);
    assert.equal(JSON.stringify(result).includes("INTERNAL_EXCEPTION_TEXT"), false);
    assert.equal("choosable" in result, false);
  }
});

test("malformed JSON and a rejected fetch stay unavailable", async () => {
  const html = fakeFetch(() => textResponse(500, "<html>secret traceback</html>"));
  const htmlClient = new LessonDeliveryClient({ fetchImpl: html.fetchImpl });
  const htmlResult = await htmlClient.getChoice("delivery-001");
  assert.deepEqual(htmlResult, { ok: false, status: 500, error: null, body: null });
  assert.equal(JSON.stringify(htmlResult).includes("secret traceback"), false);

  const empty = fakeFetch(() => textResponse(200, ""));
  const emptyResult = await new LessonDeliveryClient({ fetchImpl: empty.fetchImpl }).list();
  assert.deepEqual(emptyResult, { ok: false, status: 200, error: null, body: null });

  const list = fakeFetch(() => textResponse(200, "[1,2]"));
  const listResult = await new LessonDeliveryClient({ fetchImpl: list.fetchImpl }).list();
  assert.equal(listResult.ok, false);
  assert.equal(listResult.body, null);

  const broken = fakeFetch(() => ({
    ok: false,
    status: 502,
    text: async () => {
      throw new Error("socket reset INTERNAL_EXCEPTION_TEXT");
    },
  }));
  const brokenResult = await new LessonDeliveryClient({ fetchImpl: broken.fetchImpl }).list();
  assert.deepEqual(brokenResult, { ok: false, status: 502, error: null, body: null });

  const rejected = fakeFetch(() => {
    throw new Error("network down INTERNAL_EXCEPTION_TEXT");
  });
  const rejectedResult = await new LessonDeliveryClient({
    fetchImpl: rejected.fetchImpl,
  }).choose("delivery-001", "sha256:ab", "sha256:cd");
  assert.deepEqual(rejectedResult, { ok: false, status: 0, error: null, body: null });
  assert.equal(JSON.stringify(rejectedResult).includes("INTERNAL_EXCEPTION_TEXT"), false);
});

test("prepare POSTs the three preview pins and no query", async () => {
  const id = "a/b c?x=1";
  const artifact = `sha256:${"ab".repeat(32)}`;
  const behavior = `sha256:${"cd".repeat(32)}`;
  const { calls, fetchImpl } = fakeFetch(() => jsonResponse(200, { preparation_status: "PREPARED" }));
  const client = new LessonDeliveryClient({ fetchImpl });
  const result = await client.prepare(id, artifact, behavior);
  assert.equal(result.ok, true);
  assert.equal(result.status, 200);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, LESSON_PRACTICE_PREPARATION_PATH);
  assert.equal(calls[0].url.includes("?"), false);
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    delivery_id: id,
    expected_assignment_artifact_digest: artifact,
    expected_assignment_behavior_digest: behavior,
  });

  const failed = fakeFetch(() => jsonResponse(409, { error: "stale_preview", detail: "SECRET" }));
  const failure = await new LessonDeliveryClient({ fetchImpl: failed.fetchImpl }).prepare(
    id, artifact, behavior,
  );
  assert.deepEqual(failure, { ok: false, status: 409, error: "stale_preview", body: null });

  const rejected = fakeFetch(() => {
    throw new Error("network down");
  });
  const network = await new LessonDeliveryClient({ fetchImpl: rejected.fetchImpl }).prepare(
    id, artifact, behavior,
  );
  assert.deepEqual(network, { ok: false, status: 0, error: null, body: null });
});

test("the client does not decode ids or decide choosability", () => {
  assert.equal(source.includes("decodeURIComponent"), false);
  assert.equal(source.includes("innerHTML"), false);
  assert.equal(source.includes("localStorage"), false);
  assert.equal(source.includes("choosable"), false);
  assert.equal(source.includes("CHOSEN_FOR_PRACTICE"), false);
});
