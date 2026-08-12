export class PerformanceCaptureController {
  constructor({ midiInput, transport, api }) {
    this.midiInput = midiInput;
    this.transport = transport;
    this.api = api;
    this.armed = false;
    this.active = false;
    this.count = 0;
  }
  async arm(deviceId) {
    await this.api.arm({ device_id: deviceId });
    this.armed = this.midiInput.connect(
      deviceId,
      (m) => this.record(m),
      (id) => this.interrupt(id),
    );
    return this.armed;
  }
  async startAttempt() {
    if (!this.armed) throw new Error("Arm a MIDI input first");
    this.transport.restart();
    const snapshot = this.transport.snapshot();
    await this.api.start({
      capture_time_ns: Math.round(performance.now() * 1_000_000),
      transport: snapshot,
    });
    this.active = true;
    this.transport.play();
  }
  async record(message) {
    if (!this.active) return;
    const snapshot = this.transport.snapshot();
    await this.api.message({
      ...message,
      practice_position_seconds: snapshot.positionSeconds,
      repetition_index: snapshot.repetitionCount,
      playback_rate: snapshot.playbackRate,
    });
    this.count += 1;
  }
  async stopAttempt() {
    if (!this.active) return null;
    this.active = false;
    return this.api.stop();
  }
  async interrupt(deviceId) {
    if (this.active) {
      this.active = false;
      await this.api.interrupt({ device_id: deviceId });
    }
  }
}

export class LocalPerformanceApi {
  constructor(base = "/api/performance") {
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
  arm = (x) => this.call("arm", x);
  start = (x) => this.call("start", x);
  message = (x) => this.call("message", x);
  stop = () => this.call("stop");
  interrupt = (x) => this.call("interrupt", x);
}
