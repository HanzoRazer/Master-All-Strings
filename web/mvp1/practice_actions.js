/** Apply Educational next actions onto the existing practice shell. */

export class PracticeActionController {
  constructor({ transport, onStatus }) {
    this.transport = transport;
    this.onStatus = onStatus || (() => {});
  }

  async apply(action, api) {
    if (!action) return null;
    const result = await api.applyAction({
      action_type: action.action_type,
      target_rate: action.target_rate,
      focus_start_tick: action.focus_start_tick,
      focus_end_tick: action.focus_end_tick,
      message_key: action.message_key,
    });
    if (action.action_type === "slow_down" && action.target_rate != null) {
      this.transport.setRate(Number(action.target_rate));
      this.onStatus(`Slow down to ${action.target_rate}×`);
    } else if (action.action_type === "isolate_passage") {
      this.onStatus(
        `Isolate passage ticks ${action.focus_start_tick}–${action.focus_end_tick}`,
      );
    } else if (action.action_type === "repeat") {
      this.onStatus("Repeat the passage");
    } else if (action.action_type === "continue") {
      this.onStatus("Continue — no immediate repetition required under this policy");
    }
    return result;
  }
}

export class LocalEducationApi {
  constructor(base = "/api/education") {
    this.base = base;
  }
  async call(path, body = {}) {
    const response = await fetch(`${this.base}/${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  }
  beginLesson = (x) => this.call("begin_lesson", x);
  evaluate = (x) => this.call("evaluate", x);
  get = () => this.call("get");
  session = () => this.call("session");
  applyAction = (x) => this.call("apply_action", x);
  goldenDemo = () => this.call("golden_demo");
}
