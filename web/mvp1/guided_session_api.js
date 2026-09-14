/** Browser client for the DO-015 Stage 4 guided-session API.

Transport/adaptation only. This module records learner disposition. It does
not choose Educational actions, mint identities, or execute Transport.
*/

export const GUIDED_SESSION_API_PREFIX = "/api/education/guided-sessions";

export class LocalGuidedSessionApi {
  /**
   * @param {object} [options]
   * @param {string} [options.base]
   * @param {typeof fetch} [options.fetchImpl]
   */
  constructor({ base = GUIDED_SESSION_API_PREFIX, fetchImpl } = {}) {
    this.base = base.replace(/\/$/, "");
    this.fetchImpl = fetchImpl || globalThis.fetch.bind(globalThis);
  }

  async create({ sessionId, attemptId, evaluation, guidance }) {
    return this._request("POST", "", {
      session_id: sessionId,
      attempt_id: attemptId,
      evaluation,
      guidance,
    });
  }

  async get(sessionId) {
    return this._request("GET", `/${encodeURIComponent(sessionId)}`);
  }

  async recordDisposition(sessionId, disposition) {
    return this._request("POST", `/${encodeURIComponent(sessionId)}/disposition`, {
      disposition,
    });
  }

  async append({ sessionId, attemptId, evaluation, guidance }) {
    return this._request("POST", `/${encodeURIComponent(sessionId)}/attempts`, {
      attempt_id: attemptId,
      evaluation,
      guidance,
    });
  }

  async _request(method, suffix, body) {
    const response = await this.fetchImpl(`${this.base}${suffix}`, {
      method,
      headers: body === undefined ? {} : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
      const error = new Error(payload.error || response.statusText);
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }
}
