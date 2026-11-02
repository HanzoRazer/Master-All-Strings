import assert from "node:assert/strict";
import test from "node:test";

import { acceptBeginGateway, isBeginRequestId } from "../received_begin_validation.js";
import { choiceBody, previewBody } from "./lesson_practice_fixture.js";
import { beginDocument, interruptedDocument } from "./received_attempt_fixture.js";

const KEY = "abcdefab-abcd-4abc-8abc-abcdefabcdef";
const preview = previewBody();
const choice = choiceBody();

function wrapper(status, attempt) {
  return {
    schema_id: "master_all_strings.received_lesson_begin_request",
    schema_version: "1.0.0",
    begin_request_id: KEY,
    status,
    attempt,
  };
}

test("a gateway accepts started, empty, and interrupted results for the same key", () => {
  assert.equal(isBeginRequestId(KEY), true);
  assert.equal(isBeginRequestId(KEY.toUpperCase()), false);
  const started = acceptBeginGateway(wrapper("STARTED", beginDocument().preparation
    ? beginDocument()
    : null), KEY, preview, choice);
  assert.equal(started.ok, true);
  assert.equal(acceptBeginGateway(wrapper("PENDING", null), KEY, preview, choice).ok, true);
  assert.equal(acceptBeginGateway(wrapper("NO_ATTEMPT", null), KEY, preview, choice).ok, true);
  const interrupted = interruptedDocument(beginDocument());
  interrupted.observed_events = [];
  interrupted.unmatched_note_offs = [];
  interrupted.raw_capture.events = [];
  const recovered = acceptBeginGateway(wrapper("INTERRUPTED", interrupted), KEY, preview, choice);
  assert.equal(recovered.ok, true);
});

test("a gateway rejects the wrong key, status, pins, and nonempty capture", () => {
  const begun = beginDocument();
  assert.equal(acceptBeginGateway(wrapper("STARTED", begun), "other-key", preview, choice).ok, false);
  assert.equal(acceptBeginGateway(wrapper("STARTED", null), KEY, preview, choice).ok, false);
  assert.equal(acceptBeginGateway(wrapper("PENDING", begun), KEY, preview, choice).ok, false);
  const extra = wrapper("NO_ATTEMPT", null);
  extra.note = true;
  assert.equal(acceptBeginGateway(extra, KEY, preview, choice).ok, false);
  const interrupted = interruptedDocument(begun);
  interrupted.observed_events = [{ note: 1 }];
  interrupted.raw_capture.events = [];
  assert.equal(acceptBeginGateway(wrapper("INTERRUPTED", interrupted), KEY, preview, choice).ok, false);
  const otherPins = interruptedDocument(begun);
  otherPins.observed_events = [];
  otherPins.raw_capture.events = [];
  otherPins.delivery_id = "other";
  assert.equal(acceptBeginGateway(wrapper("INTERRUPTED", otherPins), KEY, preview, choice).ok, false);
});
