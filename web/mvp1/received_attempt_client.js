/** Transport for one isolated received-lesson attempt.

Calls the four Stage 7 routes and nothing else. It does not decide whether a
document is usable, and it does not capture, pair, or evaluate notes.
*/

export const LESSON_PRACTICE_ATTEMPT_PATH = "/api/education/lesson-practice-attempts";
export const LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH = "/api/education/lesson-practice-attempt-messages";
export const LESSON_PRACTICE_ATTEMPT_FINISH_PATH = "/api/education/lesson-practice-attempt-finishes";
export const LESSON_PRACTICE_ATTEMPT_CANCELLATION_PATH =
  "/api/education/lesson-practice-attempt-cancellations";

export class ReceivedAttemptClient {
  /**
   * @param {object} [options]
   * @param {string} [options.base]
   * @param {typeof fetch} [options.fetchImpl]
   */
  constructor({ base = "", fetchImpl } = {}) {
    this.base = base.replace(/\/$/, "");
    this.fetchImpl = fetchImpl || globalThis.fetch.bind(globalThis);
  }

  /**
   * @param {object} request
   * @param {string} request.deliveryId
   * @param {string} request.artifactDigest
   * @param {string} request.behaviorDigest
   * @param {string} request.deviceId
   * @param {number} request.captureTimeNs
   */
  begin(request) {
    return this._send(LESSON_PRACTICE_ATTEMPT_PATH, {
      delivery_id: request.deliveryId,
      expected_assignment_artifact_digest: request.artifactDigest,
      expected_assignment_behavior_digest: request.behaviorDigest,
      device_id: request.deviceId,
      capture_time_ns: request.captureTimeNs,
    });
  }

  /**
   * @param {object} request
   * @param {string} request.attemptId
   * @param {number} request.sequenceNumber
   * @param {number} request.captureTimeNs
   * @param {number} request.practicePositionSeconds
   * @param {number[]} request.rawPayload
   */
  append(request) {
    return this._send(LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH, {
      attempt_id: request.attemptId,
      sequence_number: request.sequenceNumber,
      capture_time_ns: request.captureTimeNs,
      practice_position_seconds: request.practicePositionSeconds,
      raw_payload: request.rawPayload,
    });
  }

  /**
   * @param {object} request
   * @param {string} request.attemptId
   * @param {number} request.captureTimeNs
   */
  finish(request) {
    return this._send(LESSON_PRACTICE_ATTEMPT_FINISH_PATH, {
      attempt_id: request.attemptId,
      capture_time_ns: request.captureTimeNs,
    });
  }

  /**
   * @param {object} request
   * @param {string} request.attemptId
   * @param {number} request.captureTimeNs
   * @param {boolean} [request.keepalive]
   */
  cancel(request) {
    return this._send(
      LESSON_PRACTICE_ATTEMPT_CANCELLATION_PATH,
      {
        attempt_id: request.attemptId,
        capture_time_ns: request.captureTimeNs,
      },
      { keepalive: Boolean(request.keepalive) },
    );
  }

  /**
   * @param {string} path
   * @param {object} body
   * @param {{ keepalive?: boolean }} [options]
   */
  async _send(path, body, options = {}) {
    let response;
    try {
      response = await this.fetchImpl(`${this.base}${path}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
        keepalive: options.keepalive === true,
      });
    } catch {
      return { ok: false, status: 0, error: null, body: null };
    }
    const status = Number.isInteger(response.status) ? response.status : 0;
    const payload = await readObject(response);
    if (!payload) return { ok: false, status, error: null, body: null };
    const error = typeof payload.error === "string" ? payload.error : null;
    if (!response.ok || error !== null) return { ok: false, status, error, body: null };
    return { ok: true, status, error: null, body: payload };
  }
}

/**
 * @param {{ text: () => Promise<string> }} response
 */
async function readObject(response) {
  let text;
  try {
    text = await response.text();
  } catch {
    return null;
  }
  if (!text) return null;
  try {
    const value = JSON.parse(text);
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    return value;
  } catch {
    return null;
  }
}
