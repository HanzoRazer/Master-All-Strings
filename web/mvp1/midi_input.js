export const MidiInputState = Object.freeze({
  UNSUPPORTED: "unsupported",
  PERMISSION_REQUIRED: "permission_required",
  PERMISSION_DENIED: "permission_denied",
  READY: "ready",
  DISCONNECTED: "disconnected",
  FAILED: "failed",
});

export class WebMidiInput {
  constructor({ navigatorObject = navigator } = {}) {
    this.navigator = navigatorObject;
    this.access = null;
    this.input = null;
    this.state = this.navigator.requestMIDIAccess
      ? MidiInputState.PERMISSION_REQUIRED
      : MidiInputState.UNSUPPORTED;
    this.listener = null;
    this.disconnectListener = null;
  }
  async requestPermission() {
    if (!this.navigator.requestMIDIAccess) return this.state;
    try {
      this.access = await this.navigator.requestMIDIAccess();
      this.state = MidiInputState.READY;
    } catch (error) {
      this.state =
        error?.name === "NotAllowedError"
          ? MidiInputState.PERMISSION_DENIED
          : MidiInputState.FAILED;
    }
    return this.state;
  }
  devices() {
    return this.access
      ? [...this.access.inputs.values()].map((i) => ({
          id: i.id,
          name: i.name || i.id,
        }))
      : [];
  }
  connect(id, listener, disconnectListener) {
    this.input = this.access?.inputs.get(id) || null;
    this.listener = listener;
    this.disconnectListener = disconnectListener;
    if (!this.input) {
      this.state = MidiInputState.DISCONNECTED;
      return false;
    }
    this.input.onmidimessage = (event) =>
      listener({
        capture_time_ns: Math.round(event.timeStamp * 1_000_000),
        raw_payload: [...event.data],
        device_id: id,
      });
    if (this.access)
      this.access.onstatechange = (event) => {
        if (event.port?.id === id && event.port.state === "disconnected") {
          this.state = MidiInputState.DISCONNECTED;
          disconnectListener(id);
        }
      };
    return true;
  }
  disconnect() {
    if (this.input) this.input.onmidimessage = null;
    this.input = null;
  }
}
