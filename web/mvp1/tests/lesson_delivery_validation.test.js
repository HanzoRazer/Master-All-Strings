import assert from "node:assert/strict";
import test from "node:test";

import {
  INVALID_RESPONSE,
  acceptPreparation,
  failureMessage,
  isChosen,
  isReadyPreview,
  parsePracticeSearch,
  practiceFailureMessage,
  practicePageHref,
  preparationMatches,
} from "../lesson_delivery_validation.js";

import {
  choiceBody,
  practiceNote,
  preparationBody,
  previewBody,
} from "./lesson_practice_fixture.js";

function httpOk(body) {
  return { ok: true, status: 200, error: null, body };
}

test("practice search accepts one decoded id and nothing else", () => {
  const id = "a/b c?x=1&y=2#frag";
  const href = practicePageHref(id);
  const query = href.slice(href.indexOf("?"));
  assert.equal(parsePracticeSearch(query).deliveryId, id);
  assert.equal(query.includes("#"), false);
  assert.equal(href.includes("sha256"), false);
  assert.deepEqual(parsePracticeSearch(""), { ok: false, reason: "missing" });
  assert.equal(parsePracticeSearch("?delivery_id=").ok, false);
  assert.equal(parsePracticeSearch("?delivery_id=%20").ok, false);
  assert.equal(parsePracticeSearch("?delivery_id=a&delivery_id=a").ok, false);
  assert.equal(parsePracticeSearch("?delivery_id=a&extra=1").ok, false);
  assert.equal(parsePracticeSearch("?other=a").ok, false);
  assert.equal(parsePracticeSearch("?delivery_id=a%2Fb").deliveryId, "a/b");
});

test("a closed preparation matches pins without recomputing them", () => {
  const preview = previewBody();
  const choice = choiceBody();
  const body = preparationBody();
  assert.equal(preparationMatches(body, preview, choice), true);
  body.playback.events[0].midi_note = 1;
  assert.equal(preparationMatches(body, preview, choice), true);
  assert.equal(isReadyPreview(httpOk(preview), preview.delivery_id), true);
  assert.equal(isChosen(httpOk(choice), preview), true);
});

test("preparation rejects closed-document, pin, score, and timing faults", () => {
  const preview = previewBody();
  const choice = choiceBody();
  const cases = [];
  const add = (mutate) => {
    const body = preparationBody();
    mutate(body);
    cases.push(body);
  };
  add((body) => {
    body.schema_id = "other";
  });
  add((body) => {
    body.schema_version = "1.0.1";
  });
  add((body) => {
    body.preparation_status = "READY";
  });
  add((body) => {
    body.extra = true;
  });
  add((body) => {
    delete body.score;
  });
  for (const field of [
    "delivery_id", "assignment_id", "content_id",
    "assignment_artifact_digest", "assignment_behavior_digest",
  ]) {
    add((body) => {
      body[field] = field.includes("digest") ? `sha256:${"11".repeat(32)}` : "other";
    });
  }
  add((body) => {
    body.projection.status = "partial";
  });
  add((body) => {
    body.projection.demo_id = "ascending_scale";
  });
  add((body) => {
    body.projection.behavior_digest = `sha256:${"22".repeat(32)}`;
  });
  add((body) => {
    body.projection.instrument_id = "other-instrument";
  });
  add((body) => {
    body.projection.projection.instrument.instrument_id = "other-instrument";
  });
  add((body) => {
    body.projection.projection.schema_version = "9.0.0";
  });
  add((body) => {
    body.projection.timeline_anchors = [];
  });
  add((body) => {
    body.projection.timeline_anchors = [{ tick: 1, seconds: 0 }];
  });
  add((body) => {
    body.projection.projection.notes.push(practiceNote("ev-1", 1.2));
  });
  add((body) => {
    body.playback.events[1].event_id = "";
  });
  add((body) => {
    body.playback.total_seconds = Number.NaN;
  });
  add((body) => {
    body.playback.events.reverse();
  });
  add((body) => {
    body.practice.runtime.loop_end_seconds = 9;
  });
  add((body) => {
    body.practice.runtime.loop_start_seconds = 1.5;
    body.practice.runtime.loop_end_seconds = 1;
  });
  add((body) => {
    body.practice.policy.loop.target_repetitions = 0;
  });
  add((body) => {
    body.score.tab.canonical_revision_id = "rev-other";
  });
  add((body) => {
    body.score.notation.payload.measures[0].events[1].event_kind = "note";
  });
  add((body) => {
    body.score.notation.payload.measures[0].events[0].canonical_event_id = null;
  });
  add((body) => {
    body.playback.assignment_id = "other";
  });
  add((body) => {
    body.practice.policy.content_id = "other";
  });
  for (const body of cases) {
    assert.equal(preparationMatches(body, preview, choice), false);
    const accepted = acceptPreparation(httpOk(body), preview, choice);
    assert.deepEqual(accepted, { ok: false, invalid: true });
  }
});

test("HTTP failures stay distinct from a malformed success", () => {
  const preview = previewBody();
  const choice = choiceBody();
  const stale = acceptPreparation(
    { ok: false, status: 409, error: "stale_preview", body: null },
    preview,
    choice,
  );
  assert.deepEqual(stale, { ok: false, invalid: false });
  assert.match(failureMessage(stale ? { status: 409, error: "stale_preview" } : {}), /409, stale_preview/);
  assert.equal(
    practiceFailureMessage({ status: 409, error: "stale_preview" }),
    "Request failed (409, stale_preview). Refresh the selected delivery before choosing again.",
  );
  assert.equal(practiceFailureMessage({ status: 200, error: null }, true), INVALID_RESPONSE);
  const html = acceptPreparation({ ok: false, status: 200, error: null, body: null }, preview, choice);
  assert.equal(html.invalid, false);
});
