/** Closed checks for one keyed Begin gateway response.

The playback and attempt documents keep their own validators. This module
checks the wrapper, the request key, and which statuses may carry an attempt.
*/

import { acceptBegin, acceptInterrupted } from "./received_attempt_validation.js";

export const BEGIN_REQUEST_SCHEMA_ID = "master_all_strings.received_lesson_begin_request";
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const WRAPPER_KEYS = ["schema_id", "schema_version", "begin_request_id", "status", "attempt"];
const NO_ATTEMPT_STATUSES = new Set(["PENDING", "NO_ATTEMPT"]);

export const NO_CREATION_ERRORS = new Set([
  "unknown_practice_choice",
  "unknown_delivery_id",
  "integrity_mismatch",
  "stale_preview",
  "unresolvable_assignment",
  "unsupported_instrument",
  "unpreparable_assignment",
]);

export function isBeginRequestId(value) {
  return typeof value === "string" && UUID_V4.test(value);
}

/**
 * @param {unknown} body
 * @param {string} key
 * @param {object} preview
 * @param {object} choice
 * @returns {{ ok: true, status: string, attempt: object|null } | { ok: false }}
 */
export function acceptBeginGateway(body, key, preview, choice) {
  if (!body || typeof body !== "object" || Array.isArray(body)) return { ok: false };
  if (Object.keys(body).length !== WRAPPER_KEYS.length) return { ok: false };
  if (!WRAPPER_KEYS.every((field) => Object.hasOwn(body, field))) return { ok: false };
  if (body.schema_id !== BEGIN_REQUEST_SCHEMA_ID || body.schema_version !== "1.0.0") {
    return { ok: false };
  }
  if (body.begin_request_id !== key || !isBeginRequestId(body.begin_request_id)) return { ok: false };
  if (body.status === "STARTED") {
    const accepted = acceptBegin(body.attempt, preview, choice);
    if (!accepted.ok) return { ok: false };
    return { ok: true, status: "STARTED", attempt: accepted.body };
  }
  if (body.status === "INTERRUPTED") {
    const attempt = body.attempt;
    const accepted = acceptInterrupted(attempt, attempt);
    if (!accepted.ok) return { ok: false };
    if (attempt.delivery_id !== preview?.delivery_id || attempt.delivery_id !== choice?.delivery_id) {
      return { ok: false };
    }
    if (attempt.assignment_artifact_digest !== preview.assignment_artifact_digest) return { ok: false };
    if (attempt.assignment_behavior_digest !== preview.assignment_behavior_digest) return { ok: false };
    if (attempt.observed_events.length !== 0 || attempt.raw_capture.events.length !== 0) {
      return { ok: false };
    }
    return { ok: true, status: "INTERRUPTED", attempt: accepted.body };
  }
  if (NO_ATTEMPT_STATUSES.has(body.status) && body.attempt === null) {
    return { ok: true, status: body.status, attempt: null };
  }
  return { ok: false };
}

export function definitiveBeginRefusal(response) {
  if (!response || response.ok) return false;
  if (response.status === 400) return true;
  return NO_CREATION_ERRORS.has(response.error);
}
