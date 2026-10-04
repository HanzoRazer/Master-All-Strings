/** Closed checks for Stage 7 attempt documents.

Compares identities and pins exactly. It does not trim them, and it does not
score notes or convert tempo.
*/

import { preparationMatches } from "./lesson_delivery_validation.js";

export const ATTEMPT_SCHEMA_ID = "master_all_strings.received_lesson_attempt";
export const ATTEMPT_SCHEMA_VERSION = "1.0.0";
export const CAPTURE_CLOCK = "browser_performance_time";

const IDENTITY_KEYS = [
  "schema_id",
  "schema_version",
  "attempt_id",
  "capture_id",
  "performance_session_id",
  "delivery_id",
  "assignment_id",
  "content_id",
  "assignment_artifact_digest",
  "assignment_behavior_digest",
  "capture_clock",
];

const BEGIN_KEYS = [...IDENTITY_KEYS, "attempt_status", "preparation", "attempt_policy"];
const MESSAGE_KEYS = [...IDENTITY_KEYS, "attempt_status", "accepted_event_count"];
const EVALUATED_KEYS = [
  ...IDENTITY_KEYS,
  "attempt_status",
  "raw_capture",
  "observed_events",
  "unmatched_note_offs",
  "evaluation",
  "messages",
  "guidance",
  "hardware_status",
];
const INTERRUPTED_KEYS = [
  ...IDENTITY_KEYS,
  "attempt_status",
  "raw_capture",
  "observed_events",
  "unmatched_note_offs",
  "hardware_status",
];
const POLICY_KEYS = [
  "schema_version",
  "pass_count",
  "playback_rate",
  "looping_allowed",
  "seeking_allowed",
  "lesson_switching_allowed",
  "reference_sound",
];
const HARDWARE_KEYS = ["midi_input", "audio_output"];
const EVALUATION_KEYS = [
  "schema_version",
  "assignment_id",
  "content_id",
  "performance_session_id",
  "evaluation_policy_id",
  "evaluation_policy_version",
  "findings",
  "summary",
  "primary_next_action",
  "secondary_actions",
  "provenance",
  "evaluation_digest",
];
const GUIDANCE_KEYS = [
  "schema_version",
  "canonical_revision_id",
  "performance_session_id",
  "evaluation_digest",
  "policy_version",
  "items",
  "next_action",
  "guidance_digest",
  "provenance",
];

const DIGEST = /^sha256:[0-9a-f]{64}$/;

/**
 * A complete three-byte note-on or note-off, including velocity-zero note-on.
 *
 * @param {unknown} payload
 */
export function isSupportedNoteMessage(payload) {
  if (!Array.isArray(payload) || payload.length !== 3) return false;
  const [status, data1, data2] = payload;
  if (!midiByte(status) || !dataByte(data1) || !dataByte(data2)) return false;
  const kind = status & 0xf0;
  return kind === 0x80 || kind === 0x90;
}

/**
 * @param {unknown} body
 * @param {object} preview
 * @param {object} choice
 * @returns {{ ok: true, body: object } | { ok: false }}
 */
export function acceptBegin(body, preview, choice) {
  if (!exactKeys(body, BEGIN_KEYS)) return { ok: false };
  if (!identityOk(body, preview, choice)) return { ok: false };
  if (body.attempt_status !== "CAPTURING") return { ok: false };
  if (!policyOk(body.attempt_policy)) return { ok: false };
  if (!preparationMatches(body.preparation, preview, choice)) return { ok: false };
  const revision = body.preparation.score?.canonical_revision?.revision_id;
  if (!nonblank(revision)) return { ok: false };
  return { ok: true, body };
}

/**
 * @param {unknown} body
 * @param {object} begin
 * @param {number} expectedCount
 * @returns {{ ok: true, body: object } | { ok: false }}
 */
export function acceptAcknowledgement(body, begin, expectedCount) {
  if (!exactKeys(body, MESSAGE_KEYS)) return { ok: false };
  if (!sameAttempt(body, begin)) return { ok: false };
  if (body.attempt_status !== "CAPTURING") return { ok: false };
  if (!Number.isInteger(expectedCount) || body.accepted_event_count !== expectedCount) {
    return { ok: false };
  }
  return { ok: true, body };
}

/**
 * @param {unknown} body
 * @param {object} begin
 * @returns {{ ok: true, body: object } | { ok: false }}
 */
export function acceptEvaluated(body, begin) {
  if (!exactKeys(body, EVALUATED_KEYS)) return { ok: false };
  if (!sameAttempt(body, begin) || body.attempt_status !== "EVALUATED") return { ok: false };
  if (!captureOk(body, begin, "complete")) return { ok: false };
  if (!evaluationOk(body.evaluation, begin)) return { ok: false };
  if (!guidanceOk(body.guidance, begin, body.evaluation)) return { ok: false };
  if (!messagesOk(body.messages)) return { ok: false };
  if (!hardwareOk(body.hardware_status)) return { ok: false };
  return { ok: true, body };
}

/**
 * @param {unknown} body
 * @param {object} begin
 * @returns {{ ok: true, body: object } | { ok: false }}
 */
export function acceptInterrupted(body, begin) {
  if (!exactKeys(body, INTERRUPTED_KEYS)) return { ok: false };
  if (!sameAttempt(body, begin) || body.attempt_status !== "INTERRUPTED") return { ok: false };
  if (!captureOk(body, begin, "interrupted")) return { ok: false };
  if (!hardwareOk(body.hardware_status)) return { ok: false };
  if ("evaluation" in body || "guidance" in body) return { ok: false };
  return { ok: true, body };
}

/**
 * A short sentence. Server codes stay text. Tracebacks and empty failures do not.
 *
 * @param {{ status?: number, error?: string|null }} result
 */
export function publicAttemptFailure(result) {
  const error = result?.error;
  if (typeof error === "string" && error.length > 0 && error.length <= 160 && !/traceback/i.test(error)) {
    return error;
  }
  if (result?.status === 0) return "The attempt request did not finish.";
  return "The attempt request was rejected.";
}

/**
 * @param {object} body
 * @param {object} preview
 * @param {object} choice
 */
function identityOk(body, preview, choice) {
  if (!preview || !choice) return false;
  if (body.schema_id !== ATTEMPT_SCHEMA_ID || body.schema_version !== ATTEMPT_SCHEMA_VERSION) {
    return false;
  }
  if (body.capture_clock !== CAPTURE_CLOCK) return false;
  if (!nonblank(body.attempt_id) || !nonblank(body.capture_id) || !nonblank(body.performance_session_id)) {
    return false;
  }
  const pins = [
    "delivery_id",
    "assignment_id",
    "content_id",
    "assignment_artifact_digest",
    "assignment_behavior_digest",
  ];
  return pins.every((field) => (
    body[field] === preview[field] && body[field] === choice[field] && nonblank(body[field])
  ));
}

/**
 * @param {object} body
 * @param {object} begin
 */
function sameAttempt(body, begin) {
  if (!begin) return false;
  if (body.schema_id !== ATTEMPT_SCHEMA_ID || body.schema_version !== ATTEMPT_SCHEMA_VERSION) {
    return false;
  }
  if (body.capture_clock !== CAPTURE_CLOCK) return false;
  return IDENTITY_KEYS.every((field) => body[field] === begin[field]);
}

/**
 * @param {unknown} policy
 */
function policyOk(policy) {
  if (!exactKeys(policy, POLICY_KEYS)) return false;
  return policy.schema_version === ATTEMPT_SCHEMA_VERSION &&
    policy.pass_count === 1 &&
    typeof policy.pass_count === "number" &&
    policy.playback_rate === 1 &&
    typeof policy.playback_rate === "number" &&
    policy.looping_allowed === false &&
    policy.seeking_allowed === false &&
    policy.lesson_switching_allowed === false &&
    policy.reference_sound === "independent_of_capture";
}

/**
 * @param {object} body
 * @param {object} begin
 * @param {string} completion
 */
function captureOk(body, begin, completion) {
  const capture = body.raw_capture;
  if (!isRecord(capture)) return false;
  if (capture.capture_id !== begin.capture_id) return false;
  if (capture.session_id !== begin.performance_session_id) return false;
  if (capture.completion_state !== completion) return false;
  if (!evidenceList(body.observed_events, begin.capture_id)) return false;
  return evidenceList(body.unmatched_note_offs, begin.capture_id);
}

/**
 * @param {unknown} evaluation
 * @param {object} begin
 */
function evaluationOk(evaluation, begin) {
  if (!isRecord(evaluation)) return false;
  for (const key of EVALUATION_KEYS) {
    if (!Object.hasOwn(evaluation, key)) return false;
  }
  if (evaluation.schema_version !== ATTEMPT_SCHEMA_VERSION) return false;
  if (evaluation.assignment_id !== begin.assignment_id) return false;
  if (evaluation.content_id !== begin.content_id) return false;
  if (evaluation.performance_session_id !== begin.performance_session_id) return false;
  if (!DIGEST.test(evaluation.evaluation_digest)) return false;
  if (!Array.isArray(evaluation.findings) || !Array.isArray(evaluation.secondary_actions)) return false;
  if (!isRecord(evaluation.summary) || !isRecord(evaluation.primary_next_action)) return false;
  if (!isRecord(evaluation.provenance)) return false;
  return countOk(evaluation.summary);
}

/**
 * @param {unknown} guidance
 * @param {object} begin
 * @param {object} evaluation
 */
function guidanceOk(guidance, begin, evaluation) {
  if (!isRecord(guidance)) return false;
  for (const key of GUIDANCE_KEYS) {
    if (!Object.hasOwn(guidance, key)) return false;
  }
  const revision = begin.preparation?.score?.canonical_revision?.revision_id;
  if (!nonblank(revision) || guidance.canonical_revision_id !== revision) return false;
  if (guidance.performance_session_id !== begin.performance_session_id) return false;
  if (guidance.evaluation_digest !== evaluation.evaluation_digest) return false;
  if (!DIGEST.test(guidance.guidance_digest)) return false;
  if (guidance.schema_version !== ATTEMPT_SCHEMA_VERSION) return false;
  if (!Array.isArray(guidance.items) || !isRecord(guidance.next_action)) return false;
  return isRecord(guidance.provenance) && nonblank(guidance.policy_version);
}

/**
 * @param {unknown} messages
 */
function messagesOk(messages) {
  if (!isRecord(messages)) return false;
  return Object.values(messages).every((value) => typeof value === "string" && value.length > 0);
}

/**
 * @param {unknown} hardware
 */
function hardwareOk(hardware) {
  if (!exactKeys(hardware, HARDWARE_KEYS)) return false;
  return hardware.midi_input === "UNVERIFIED_PHYSICAL_MIDI_INPUT" &&
    hardware.audio_output === "UNVERIFIED_AUDIO_OUTPUT";
}

/**
 * @param {unknown} items
 * @param {string} captureId
 */
function evidenceList(items, captureId) {
  if (!Array.isArray(items)) return false;
  return items.every((item) => isRecord(item) && item.capture_id === captureId);
}

/**
 * @param {object} summary
 */
function countOk(summary) {
  return ["matched_count", "missing_count", "extra_count"].every((key) => (
    Number.isInteger(summary[key]) && summary[key] >= 0
  ));
}

/**
 * @param {unknown} value
 * @param {string[]} keys
 */
function exactKeys(value, keys) {
  if (!isRecord(value)) return false;
  const actual = Object.keys(value);
  if (actual.length !== keys.length) return false;
  return keys.every((key) => Object.hasOwn(value, key));
}

/**
 * @param {unknown} value
 */
function midiByte(value) {
  return Number.isInteger(value) && value >= 0 && value <= 255;
}

/**
 * @param {unknown} value
 */
function dataByte(value) {
  return Number.isInteger(value) && value >= 0 && value <= 127;
}

/**
 * @param {unknown} value
 */
function nonblank(value) {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * @param {unknown} value
 * @returns {value is Record<string, unknown>}
 */
function isRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
