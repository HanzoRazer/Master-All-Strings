/** Map authoritative playback-plan seconds onto Web Audio scheduling timestamps. */

export class AudioScheduler {
  constructor({
    transport,
    synth,
    lookaheadSeconds = 0.15,
    intervalMs = 25,
    setIntervalFn = (callback, milliseconds) => globalThis.setInterval(callback, milliseconds),
    clearIntervalFn = (timer) => globalThis.clearInterval(timer),
    onDiagnostic = () => {},
  }) {
    if (!transport || !synth) throw new TypeError("scheduler requires transport and synth");
    this.transport = transport;
    this.synth = synth;
    this.lookaheadSeconds = lookaheadSeconds;
    this.intervalMs = intervalMs;
    this.setIntervalFn = setIntervalFn;
    this.clearIntervalFn = clearIntervalFn;
    this.onDiagnostic = onDiagnostic;
    this.plan = null;
    this.enabled = true;
    this.scheduled = new Set();
    this.timer = null;
    this.unsubscribe = transport.subscribe((event) => this._onTransport(event));
  }

  loadPlan(plan) {
    this.panic("lesson-change");
    if (!plan || plan.schema_version !== "1.0.0" || !Array.isArray(plan.events)) {
      throw new TypeError("unsupported playback plan");
    }
    if (!Number.isFinite(plan.total_seconds) || plan.total_seconds <= 0) {
      throw new RangeError("playback plan requires a positive duration");
    }
    let previous = [-1, -1, ""];
    for (const event of plan.events) {
      const current = [event.onset_seconds, event.release_seconds, event.event_id];
      if (
        !Number.isFinite(event.onset_seconds) ||
        !Number.isFinite(event.release_seconds) ||
        event.release_seconds <= event.onset_seconds ||
        compareEventOrder(current, previous) < 0
      ) {
        throw new RangeError("playback events must have ordered positive durations");
      }
      previous = current;
    }
    this.plan = plan;
  }

  setEnabled(enabled) {
    this.enabled = Boolean(enabled);
    if (!this.enabled) this.panic("sound-disabled");
  }

  start() {
    if (this.timer != null) return;
    this.timer = this.setIntervalFn(() => this.tick(), this.intervalMs);
  }

  stop() {
    if (this.timer != null) this.clearIntervalFn(this.timer);
    this.timer = null;
    this.panic("scheduler-stop");
  }

  destroy() {
    this.stop();
    this.unsubscribe();
  }

  panic(reason = "explicit") {
    this.synth.panic();
    this.scheduled.clear();
    this.onDiagnostic({ type: "panic", reason });
  }

  tick() {
    if (!this.enabled || !this.plan || !this.transport.playing) return 0;
    const context = this.synth.context;
    if (!context || this.synth.readiness !== "ready") return 0;

    const position = this.transport.positionSeconds();
    const rate = this.transport.playbackRate;
    const horizon = position + this.lookaheadSeconds * rate;
    let count = 0;
    for (const event of this.plan.events) {
      if (this.scheduled.has(event.event_id)) continue;
      if (event.release_seconds <= position || event.onset_seconds >= horizon) continue;
      const effectiveOnset = Math.max(position, event.onset_seconds);
      const expectedLeadSeconds = (effectiveOnset - position) / rate;
      const audioContextTime = context.currentTime;
      const startAt = audioContextTime + expectedLeadSeconds;
      const releaseAt = startAt + (event.release_seconds - effectiveOnset) / rate;
      this.synth.scheduleNote(
        {
          eventId: event.event_id,
          midiNote: event.midi_note,
          velocity: event.velocity,
          centsOffset: event.cents_offset,
        },
        startAt,
        releaseAt,
      );
      this.scheduled.add(event.event_id);
      count += 1;
      this.onDiagnostic({
        type: "scheduled",
        eventId: event.event_id,
        musicalOnsetSeconds: event.onset_seconds,
        transportPositionSeconds: position,
        audioStartTime: startAt,
        audioContextTime,
        playbackRate: rate,
        expectedLeadSeconds,
        mappingErrorMs: (startAt - audioContextTime - expectedLeadSeconds) * 1000,
      });
    }
    return count;
  }

  _onTransport(event) {
    if (
      [
        "pause",
        "restart",
        "seek",
        "rate",
        "loop",
        "duration",
        "loop-wrap",
        "loop-complete",
        "complete",
      ].includes(event.type)
    ) {
      this.panic(`transport-${event.type}`);
    }
    if (event.type === "play") {
      this.scheduled.clear();
      this.tick();
    }
  }
}

function compareEventOrder(left, right) {
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] < right[index]) return -1;
    if (left[index] > right[index]) return 1;
  }
  return 0;
}
