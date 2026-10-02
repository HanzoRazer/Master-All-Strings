/** HTTP client for the local lesson inbox and practice page.

Transport only. This module calls the Stage 1 list, Stage 2 preview, Stage 3
choice, and Stage 5 preparation routes. It preserves the HTTP status and the
public error code. It does not decide whether a document is usable, and it
does not preview, choose, prepare, or start a lesson.
*/

export const LESSON_DELIVERY_LIST_PATH = "/api/education/lesson-deliveries";
export const LESSON_DELIVERY_PREVIEW_PATH = "/api/education/lesson-delivery-preview";
export const LESSON_PRACTICE_CHOICE_PATH = "/api/education/lesson-practice-choices";
export const LESSON_PRACTICE_PREPARATION_PATH = "/api/education/lesson-practice-preparations";

/**
 * One `delivery_id` query, encoded once.
 *
 * `encodeURIComponent` leaves the value intact for the server's single
 * percent-decode. A second encode, or splitting on `/`, would change ids
 * that contain `%`, `/`, space, `#`, `?`, or `&`.
 *
 * @param {string} path
 * @param {string} deliveryId
 */
export function lessonDeliveryQuery(path, deliveryId) {
  return `${path}?delivery_id=${encodeURIComponent(deliveryId)}`;
}

/**
 * @typedef {object} LessonHttpResult
 * @property {boolean} ok
 * @property {number} status  HTTP status, or 0 when the transport rejected.
 * @property {string|null} error  Public `error` string, otherwise null.
 * @property {object|null} body  Success document, otherwise null.
 */

export class LessonDeliveryClient {
  /**
   * @param {object} [options]
   * @param {string} [options.base]
   * @param {typeof fetch} [options.fetchImpl]
   */
  constructor({ base = "", fetchImpl } = {}) {
    this.base = base.replace(/\/$/, "");
    this.fetchImpl = fetchImpl || globalThis.fetch.bind(globalThis);
  }

  /** @returns {Promise<LessonHttpResult>} */
  list() {
    return this._send("GET", LESSON_DELIVERY_LIST_PATH);
  }

  /**
   * @param {string} deliveryId
   * @returns {Promise<LessonHttpResult>}
   */
  preview(deliveryId) {
    return this._send("GET", lessonDeliveryQuery(LESSON_DELIVERY_PREVIEW_PATH, deliveryId));
  }

  /**
   * @param {string} deliveryId
   * @returns {Promise<LessonHttpResult>}
   */
  getChoice(deliveryId) {
    return this._send("GET", lessonDeliveryQuery(LESSON_PRACTICE_CHOICE_PATH, deliveryId));
  }

  /**
   * POST the preview's declared digests. The body is the only place the id
   * is sent; this URL has no query string.
   *
   * @param {string} deliveryId
   * @param {string} artifactDigest
   * @param {string} behaviorDigest
   * @returns {Promise<LessonHttpResult>}
   */
  choose(deliveryId, artifactDigest, behaviorDigest) {
    return this._send("POST", LESSON_PRACTICE_CHOICE_PATH, {
      delivery_id: deliveryId,
      expected_assignment_artifact_digest: artifactDigest,
      expected_assignment_behavior_digest: behaviorDigest,
    });
  }

  /**
   * POST the preview's declared digests. The body is the only place the id
   * is sent; this URL has no query string. The call computes a bundle. It
   * does not create a choice or start playback.
   *
   * @param {string} deliveryId
   * @param {string} artifactDigest
   * @param {string} behaviorDigest
   * @returns {Promise<LessonHttpResult>}
   */
  prepare(deliveryId, artifactDigest, behaviorDigest) {
    return this._send("POST", LESSON_PRACTICE_PREPARATION_PATH, {
      delivery_id: deliveryId,
      expected_assignment_artifact_digest: artifactDigest,
      expected_assignment_behavior_digest: behaviorDigest,
    });
  }

  /**
   * @param {string} method
   * @param {string} path
   * @param {object} [body]
   * @returns {Promise<LessonHttpResult>}
   */
  async _send(method, path, body) {
    let response;
    try {
      response = await this.fetchImpl(this._url(path), {
        method,
        headers: body === undefined ? {} : { "content-type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      return { ok: false, status: 0, error: null, body: null };
    }
    const status = Number.isInteger(response.status) ? response.status : 0;
    const payload = await readObject(response);
    if (!payload) {
      return { ok: false, status, error: null, body: null };
    }
    const error = typeof payload.error === "string" ? payload.error : null;
    if (!response.ok || error !== null) {
      return { ok: false, status, error, body: null };
    }
    return { ok: true, status, error: null, body: payload };
  }

  /** @param {string} path */
  _url(path) {
    return `${this.base}${path}`;
  }
}

/**
 * Parse a JSON object. Anything else — empty, HTML, a list, a thrown read —
 * is unusable, and the caller must not invent a document from it.
 *
 * @param {{ text: () => Promise<string> }} response
 * @returns {Promise<object|null>}
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
