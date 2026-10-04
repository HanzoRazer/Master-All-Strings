import assert from "node:assert/strict";
import test from "node:test";

import { previewBody, choiceBody } from "./lesson_practice_fixture.js";
import {
  acknowledgementDocument,
  beginDocument,
  evaluatedDocument,
  interruptedDocument,
  policyDocument,
} from "./received_attempt_fixture.js";
import {
  acceptAcknowledgement,
  acceptBegin,
  acceptEvaluated,
  acceptInterrupted,
  isSupportedNoteMessage,
  publicAttemptFailure,
} from "../received_attempt_validation.js";

const preview = previewBody();
const choice = choiceBody();

function acceptedBegin() {
  const begun = acceptBegin(beginDocument(), preview, choice);
  assert.equal(begun.ok, true);
  return begun.body;
}

test("supported note messages include velocity-zero note-on", () => {
  assert.equal(isSupportedNoteMessage([0x90, 64, 80]), true);
  assert.equal(isSupportedNoteMessage([0x80, 64, 0]), true);
  assert.equal(isSupportedNoteMessage([0x90, 64, 0]), true);
  assert.equal(isSupportedNoteMessage([0x9f, 127, 127]), true);
  assert.equal(isSupportedNoteMessage([0xb0, 7, 100]), false);
  assert.equal(isSupportedNoteMessage([0x90, 64]), false);
  assert.equal(isSupportedNoteMessage([0x90, 200, 1]), false);
  assert.equal(isSupportedNoteMessage([0x90, 64, 80, 0]), false);
  assert.equal(isSupportedNoteMessage("90"), false);
});

test("begin accepts the server snapshot, including a different revision", () => {
  const begun = acceptedBegin();
  assert.equal(begun.preparation.score.canonical_revision.revision_id, "rev-attempt");
  assert.notEqual(begun.preparation.score.canonical_revision.revision_id, "rev-received");
});

test("begin rejects schema, version, status, shape, and policy changes", () => {
  const cases = [];
  const wrongSchema = beginDocument();
  wrongSchema.schema_id = "master_all_strings.other";
  cases.push(wrongSchema);
  const wrongVersion = beginDocument();
  wrongVersion.schema_version = "9.0.0";
  cases.push(wrongVersion);
  const wrongStatus = beginDocument();
  wrongStatus.attempt_status = "EVALUATED";
  cases.push(wrongStatus);
  const extra = beginDocument();
  extra.extra = true;
  cases.push(extra);
  const missing = beginDocument();
  delete missing.capture_clock;
  cases.push(missing);
  const clock = beginDocument();
  clock.capture_clock = "utc";
  cases.push(clock);
  const boolRate = beginDocument({
    policy: { ...policyDocument(), playback_rate: true },
  });
  cases.push(boolRate);
  const looping = beginDocument({
    policy: { ...policyDocument(), looping_allowed: true },
  });
  cases.push(looping);
  for (const body of cases) {
    assert.equal(acceptBegin(body, preview, choice).ok, false, JSON.stringify(body.attempt_status));
  }
  assert.equal(acceptBegin(null, preview, choice).ok, false);
  assert.equal(acceptBegin(beginDocument(), null, choice).ok, false);
});

test("each identity pin is compared on its own", () => {
  const fields = [
    "delivery_id",
    "assignment_id",
    "content_id",
    "assignment_artifact_digest",
    "assignment_behavior_digest",
  ];
  for (const field of fields) {
    const body = beginDocument();
    body[field] = `${body[field]}-other`;
    assert.equal(acceptBegin(body, preview, choice).ok, false, field);
  }
  const minted = beginDocument({ attemptId: "attempt-from-server", captureId: "cap-2", sessionId: "ses-2" });
  assert.equal(acceptBegin(minted, preview, choice).ok, true);
  for (const field of ["attempt_id", "capture_id", "performance_session_id"]) {
    const blank = beginDocument();
    blank[field] = "  ";
    assert.equal(acceptBegin(blank, preview, choice).ok, false, field);
  }
  const trimmed = beginDocument();
  trimmed.delivery_id = `${preview.delivery_id} `;
  assert.equal(acceptBegin(trimmed, preview, choice).ok, false);
});

test("acknowledgements must stay on the same attempt and the next count", () => {
  const begin = acceptedBegin();
  assert.equal(acceptAcknowledgement(acknowledgementDocument(begin, 1), begin, 1).ok, true);
  assert.equal(acceptAcknowledgement(acknowledgementDocument(begin, 2), begin, 1).ok, false);
  const other = acknowledgementDocument(begin, 1);
  other.attempt_id = "attempt-2";
  assert.equal(acceptAcknowledgement(other, begin, 1).ok, false);
  const closed = acknowledgementDocument(begin, 1);
  closed.attempt_status = "EVALUATED";
  assert.equal(acceptAcknowledgement(closed, begin, 1).ok, false);
  const extra = acknowledgementDocument(begin, 1);
  extra.note = 64;
  assert.equal(acceptAcknowledgement(extra, begin, 1).ok, false);
});

test("evaluated feedback requires the whole evidence chain", () => {
  const begin = acceptedBegin();
  const good = evaluatedDocument(begin);
  assert.equal(acceptEvaluated(good, begin).ok, true);

  const mismatches = [];
  const push = (mutate) => {
    const copy = structuredClone(good);
    mutate(copy);
    mismatches.push(copy);
  };
  push((copy) => {
    copy.attempt_id = "other";
  });
  push((copy) => {
    copy.delivery_id = "other";
  });
  push((copy) => {
    copy.assignment_id = "other";
  });
  push((copy) => {
    copy.content_id = "other";
  });
  push((copy) => {
    copy.assignment_artifact_digest = `sha256:${"ff".repeat(32)}`;
  });
  push((copy) => {
    copy.assignment_behavior_digest = `sha256:${"ee".repeat(32)}`;
  });
  push((copy) => {
    copy.capture_id = "other-capture";
  });
  push((copy) => {
    copy.performance_session_id = "other-session";
  });
  push((copy) => {
    copy.schema_version = "0.0.1";
  });
  push((copy) => {
    copy.attempt_status = "INTERRUPTED";
  });
  push((copy) => {
    copy.raw_capture.capture_id = "other-capture";
  });
  push((copy) => {
    copy.raw_capture.session_id = "other-session";
  });
  push((copy) => {
    copy.raw_capture.completion_state = "interrupted";
  });
  push((copy) => {
    copy.observed_events[0].capture_id = "other-capture";
  });
  push((copy) => {
    copy.unmatched_note_offs[0].capture_id = "other-capture";
  });
  push((copy) => {
    copy.evaluation.assignment_id = "other";
  });
  push((copy) => {
    copy.evaluation.content_id = "other";
  });
  push((copy) => {
    copy.evaluation.performance_session_id = "other-session";
  });
  push((copy) => {
    copy.evaluation.evaluation_digest = "sha256:short";
  });
  push((copy) => {
    copy.guidance.canonical_revision_id = "rev-other";
  });
  push((copy) => {
    copy.guidance.performance_session_id = "other-session";
  });
  push((copy) => {
    copy.guidance.evaluation_digest = `sha256:${"33".repeat(32)}`;
  });
  push((copy) => {
    copy.hardware_status.midi_input = "CERTIFIED";
  });
  push((copy) => {
    copy.messages.missing = "";
  });
  push((copy) => {
    copy.extra = true;
  });
  push((copy) => {
    delete copy.guidance;
  });
  push((copy) => {
    copy.evaluation.summary.matched_count = 1.5;
  });
  push((copy) => {
    copy.evaluation.summary.missing_count = -1;
  });
  for (const body of mismatches) {
    assert.equal(acceptEvaluated(body, begin).ok, false);
  }
});

test("interruption keeps evidence and has no evaluation", () => {
  const begin = acceptedBegin();
  assert.equal(acceptInterrupted(interruptedDocument(begin), begin).ok, true);
  const evaluated = interruptedDocument(begin);
  evaluated.evaluation = {};
  assert.equal(acceptInterrupted(evaluated, begin).ok, false);
  const complete = interruptedDocument(begin);
  complete.raw_capture.completion_state = "complete";
  assert.equal(acceptInterrupted(complete, begin).ok, false);
  const otherSession = interruptedDocument(begin);
  otherSession.raw_capture.session_id = "nope";
  assert.equal(acceptInterrupted(otherSession, begin).ok, false);
  const extra = interruptedDocument(begin);
  extra.guidance = {};
  assert.equal(acceptInterrupted(extra, begin).ok, false);
});

test("public failures stay short and do not pass a traceback", () => {
  assert.equal(publicAttemptFailure({ status: 409, error: "sequence_conflict" }), "sequence_conflict");
  assert.equal(publicAttemptFailure({ status: 0, error: null }), "The attempt request did not finish.");
  assert.equal(publicAttemptFailure({ status: 500, error: null }), "The attempt request was rejected.");
  assert.equal(
    publicAttemptFailure({ status: 500, error: "Traceback (most recent call last)" }),
    "The attempt request was rejected.",
  );
  assert.equal(publicAttemptFailure({ status: 400, error: "" }), "The attempt request was rejected.");
});
