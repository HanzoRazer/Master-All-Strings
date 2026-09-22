/**
 * The reproducible certification witness, asserted rather than just captured.
 *
 * `do015_certification_capture.mjs` writes evidence; this runs the same flow
 * and states what the evidence has to say. Keeping them one scenario means the
 * artifact in docs cannot drift away from what the suite proves.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { runCertification } from "./do015_certification_capture.mjs";

const certification = await runCertification();
const step = (label) => certification.steps.find((item) => item.label === label);

test("the certified flow reaches every lifecycle state through the page", () => {
  assert.deepEqual(certification.legs_served, [
    "attempt_0_slow_down",
    "attempt_1_isolate",
    "attempt_2_continue",
    "lesson_switch_witness",
  ]);
  assert.equal(certification.final_status, "CLOSED");
  assert.equal(certification.attempt_ids.length, 3);
  assert.equal(new Set(certification.attempt_ids).size, 3, "attempt ids must be distinct");
});

test("Accept records a disposition and touches no runtime", () => {
  for (const leg of ["attempt_0_slow_down", "attempt_1_isolate", "attempt_2_continue"]) {
    const accepted = step(`${leg}:accepted`);
    assert.equal(accepted.action_disposition, "ACCEPTED");
    assert.equal(accepted.execution_status, "PENDING");
    assert.equal(accepted.transport_untouched_by_accept, true, leg);
  }
});

test("Apply executes the accepted action on its own runtime seam", () => {
  const slowDown = step("attempt_0_slow_down:applied");
  assert.equal(slowDown.execution_status, "SUCCEEDED");
  assert.equal(slowDown.transport_rate, 0.75);
  assert.equal(slowDown.transport_loop, null, "SLOW_DOWN must not set a loop");

  const isolate = step("attempt_1_isolate:applied");
  assert.equal(isolate.execution_status, "SUCCEEDED");
  assert.notEqual(isolate.transport_loop, null, "ISOLATE_PASSAGE must set a loop");
  assert.equal(isolate.transport_rate, 0.75, "ISOLATE must not change the rate");
});

test("CONTINUE closes the session and claims nothing more", () => {
  const closed = step("attempt_2_continue:applied");
  assert.equal(closed.session_status, "CLOSED");
  assert.equal(closed.execution_status, "SUCCEEDED");
  const text = JSON.stringify(certification).toLowerCase();
  for (const forbidden of ["mastered", "course complete", "lesson passed"]) {
    assert.equal(text.includes(forbidden), false, forbidden);
  }
});

test("each attempt appends and the history renders every one", () => {
  assert.equal(step("attempt_0_slow_down:evaluated").attempt_count, 1);
  assert.equal(step("attempt_1_isolate:evaluated").attempt_count, 2);
  assert.equal(step("attempt_2_continue:evaluated").attempt_count, 3);
  for (const [label, rendered] of [
    ["attempt_0_slow_down:evaluated", 1],
    ["attempt_1_isolate:evaluated", 2],
    ["attempt_2_continue:evaluated", 3],
  ]) {
    assert.equal(step(label).history_rendered, rendered, label);
  }
});

test("an attempt that is no longer current never changes again", () => {
  assert.equal(certification.attempt_0_immutable.length, 2);
  for (const record of certification.attempt_0_immutable) {
    assert.equal(record.attempt_0_unchanged, true, `after attempt ${record.after_attempt}`);
  }
});

test("every attempt carries the evaluator's own identity chain", () => {
  assert.equal(certification.identity_chain.length, 3);
  for (const attempt of certification.identity_chain) {
    assert.equal(attempt.matches_guidance_performance, true, attempt.attempt_id);
    assert.equal(attempt.matches_evaluation_digest, true, attempt.attempt_id);
    assert.equal(attempt.matches_guidance_digest, true, attempt.attempt_id);
  }
  const performances = certification.identity_chain.map((item) => item.performance_session_id);
  assert.equal(new Set(performances).size, 3, "attempts must not share a performance");
  const revisions = new Set(certification.identity_chain.map((item) => item.canonical_revision_id));
  assert.equal(revisions.size, 1, "one session is pinned to one canonical revision");
});

test("a re-cut revision leaves the recorded session inert", () => {
  const failClosed = certification.revision_fail_closed;
  assert.equal(failClosed.session_preserved, true);
  assert.equal(failClosed.active_session, null);
  assert.equal(failClosed.accept_enabled, false);
  assert.equal(failClosed.apply_enabled, false);
  assert.equal(failClosed.history_rendered, 0);
});

test("a lesson switch transitions the open session and starts the next clean", () => {
  const transition = certification.lesson_transition;
  assert.equal(transition.previous_session_status, "TRANSITIONED");
  assert.equal(transition.new_lesson_session, null);
  assert.equal(transition.history_rendered, 0);
});

test("the flow produced no console errors", () => {
  assert.deepEqual(certification.console_errors, []);
});
