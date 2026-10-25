/** Shared Stage 7 documents for browser tests. Not a product module. */

import { preparationBody, previewBody } from "./lesson_practice_fixture.js";

export const EVAL_DIGEST = `sha256:${"11".repeat(32)}`;
export const GUIDE_DIGEST = `sha256:${"22".repeat(32)}`;

export function policyDocument() {
  return {
    schema_version: "1.0.0",
    pass_count: 1,
    playback_rate: 1,
    looping_allowed: false,
    seeking_allowed: false,
    lesson_switching_allowed: false,
    reference_sound: "independent_of_capture",
  };
}

export function hardwareStatus() {
  return {
    midi_input: "UNVERIFIED_PHYSICAL_MIDI_INPUT",
    audio_output: "UNVERIFIED_AUDIO_OUTPUT",
  };
}

/**
 * @param {object} preparation
 * @param {string} revisionId
 */
export function withRevision(preparation, revisionId) {
  const copy = structuredClone(preparation);
  copy.score.canonical_revision.revision_id = revisionId;
  copy.playback.canonical_revision_id = revisionId;
  copy.score.tab.canonical_revision_id = revisionId;
  copy.score.tab.payload.canonical_revision_id = revisionId;
  copy.score.notation.canonical_revision_id = revisionId;
  copy.score.notation.payload.canonical_revision_id = revisionId;
  return copy;
}

/**
 * @param {object} [options]
 */
export function beginDocument(options = {}) {
  const preview = options.preview ?? previewBody(options.deliveryId);
  const preparation = withRevision(
    options.preparation ?? preparationBody(preview.delivery_id),
    options.revisionId ?? "rev-attempt",
  );
  return {
    schema_id: "master_all_strings.received_lesson_attempt",
    schema_version: "1.0.0",
    attempt_id: options.attemptId ?? "attempt-1",
    capture_id: options.captureId ?? "capture-1",
    performance_session_id: options.sessionId ?? "session-1",
    delivery_id: preview.delivery_id,
    assignment_id: preview.assignment_id,
    content_id: preview.content_id,
    assignment_artifact_digest: preview.assignment_artifact_digest,
    assignment_behavior_digest: preview.assignment_behavior_digest,
    capture_clock: "browser_performance_time",
    attempt_status: "CAPTURING",
    preparation,
    attempt_policy: options.policy ?? policyDocument(),
  };
}

/**
 * @param {object} begin
 */
export function identityOf(begin) {
  return {
    schema_id: begin.schema_id,
    schema_version: begin.schema_version,
    attempt_id: begin.attempt_id,
    capture_id: begin.capture_id,
    performance_session_id: begin.performance_session_id,
    delivery_id: begin.delivery_id,
    assignment_id: begin.assignment_id,
    content_id: begin.content_id,
    assignment_artifact_digest: begin.assignment_artifact_digest,
    assignment_behavior_digest: begin.assignment_behavior_digest,
    capture_clock: begin.capture_clock,
  };
}

/**
 * @param {object} begin
 * @param {number} count
 */
export function acknowledgementDocument(begin, count) {
  return {
    ...identityOf(begin),
    attempt_status: "CAPTURING",
    accepted_event_count: count,
  };
}

/**
 * @param {object} begin
 * @param {object} [options]
 */
export function evaluatedDocument(begin, options = {}) {
  const digest = options.digest ?? EVAL_DIGEST;
  const revision = begin.preparation.score.canonical_revision.revision_id;
  return {
    ...identityOf(begin),
    attempt_status: "EVALUATED",
    raw_capture: {
      capture_id: begin.capture_id,
      session_id: begin.performance_session_id,
      completion_state: "complete",
      warnings: options.warnings ?? ["<script>alert(1)</script>"],
    },
    observed_events: options.observed ?? [{ capture_id: begin.capture_id, midi_note: 64 }],
    unmatched_note_offs: options.unmatched ?? [{ capture_id: begin.capture_id, midi_note: 70 }],
    evaluation: {
      schema_version: "1.0.0",
      assignment_id: begin.assignment_id,
      content_id: begin.content_id,
      performance_session_id: begin.performance_session_id,
      evaluation_policy_id: "policy-1",
      evaluation_policy_version: "1.0.0",
      findings: options.findings ?? [{
        finding_type: "missing_note",
        message_key: "missing",
      }],
      summary: options.summary ?? { matched_count: 1, missing_count: 2, extra_count: 1 },
      primary_next_action: options.action ?? { action_type: "continue", message_key: "next" },
      secondary_actions: [],
      provenance: { source: "server" },
      evaluation_digest: digest,
    },
    messages: options.messages ?? {
      missing: "<img src=x onerror=alert(1)>",
      next: "Go on.",
    },
    guidance: {
      schema_version: "1.0.0",
      canonical_revision_id: options.guidanceRevision ?? revision,
      performance_session_id: options.guidanceSession ?? begin.performance_session_id,
      evaluation_digest: options.guidanceDigest ?? digest,
      policy_version: "1.0.0",
      items: [{ canonical_event_id: "ev-1" }],
      next_action: { action_type: "continue", message_key: "next" },
      guidance_digest: GUIDE_DIGEST,
      provenance: { source: "server" },
    },
    hardware_status: options.hardware ?? hardwareStatus(),
  };
}

/**
 * @param {object} begin
 */
export function interruptedDocument(begin) {
  return {
    ...identityOf(begin),
    attempt_status: "INTERRUPTED",
    raw_capture: {
      capture_id: begin.capture_id,
      session_id: begin.performance_session_id,
      completion_state: "interrupted",
      warnings: ["capture stopped"],
    },
    observed_events: [{ capture_id: begin.capture_id }],
    unmatched_note_offs: [{ capture_id: begin.capture_id, midi_note: 64 }],
    hardware_status: hardwareStatus(),
  };
}
