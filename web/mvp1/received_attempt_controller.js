/** One explicit attempt against the lesson snapshot the server returned.

MIDI intake, the outbound queue, and terminal transitions live here. Musical
comparison does not.
*/

import {
  acceptAcknowledgement,
  acceptBegin,
  acceptEvaluated,
  acceptInterrupted,
  isSupportedNoteMessage,
  publicAttemptFailure,
} from "./received_attempt_validation.js";

export const AttemptState = Object.freeze({
  IDLE: "IDLE",
  STARTING: "STARTING",
  CAPTURING: "CAPTURING",
  FINISHING: "FINISHING",
  CANCELLING: "CANCELLING",
  EVALUATED: "EVALUATED",
  INTERRUPTED: "INTERRUPTED",
  UNCONFIRMED: "UNCONFIRMED",
});

const QUEUE_LIMIT = 256;
const ACTIVE = new Set([
  AttemptState.STARTING,
  AttemptState.CAPTURING,
  AttemptState.FINISHING,
  AttemptState.CANCELLING,
]);

/**
 * @param {object} deps
 */
export function createReceivedAttemptController(deps) {
  let state = AttemptState.IDLE;
  let generation = 0;
  let intakeToken = 0;
  let beginDoc = null;
  let selectedId = null;
  let queue = [];
  let sending = false;
  let nextSequence = 0;
  let acked = 0;
  let lastCaptureNs = 0;
  let terminal = null;
  let unconfirmedKind = null;
  let midiState = "permission_required";
  let drain = Promise.resolve();

  function snapshot() {
    return {
      state,
      acked,
      attemptId: beginDoc?.attempt_id ?? null,
      selectedId,
      midiState,
      unconfirmedKind,
      devices: typeof deps.midi.devices === "function" ? deps.midi.devices() : [],
    };
  }

  function publish(notice = "") {
    deps.onChange?.(snapshot(), notice);
  }

  function setState(next, notice = "") {
    state = next;
    publish(notice);
  }

  function alive(token) {
    return token === generation && deps.isCurrent() !== false;
  }

  function stopIntake() {
    intakeToken += 1;
    deps.midi.disconnect?.();
  }

  function terminalNs() {
    const now = deps.nowNs();
    return now >= lastCaptureNs ? now : lastCaptureNs;
  }

  async function enableMidi() {
    if (ACTIVE.has(state)) return snapshot();
    midiState = await deps.midi.requestPermission();
    const devices = deps.midi.devices();
    if (!selectedId && devices.length === 1) selectedId = devices[0].id;
    if (selectedId && !devices.some((device) => device.id === selectedId)) selectedId = null;
    publish();
    return snapshot();
  }

  function selectInput(id) {
    if (ACTIVE.has(state)) return snapshot();
    const devices = deps.midi.devices();
    selectedId = devices.some((device) => device.id === id) ? id : null;
    publish();
    return snapshot();
  }

  async function start() {
    if (ACTIVE.has(state) || state === AttemptState.FINISHING) return snapshot();
    if (unconfirmedKind === "finish") return snapshot();
    const lesson = deps.getLesson();
    const device = (deps.midi.devices() || []).find((item) => item.id === selectedId);
    if (!lesson?.preview || !lesson.choice || !device) {
      publish("Select a connected MIDI input before starting an attempt.");
      return snapshot();
    }
    const token = ++generation;
    stopIntake();
    beginDoc = null;
    queue = [];
    nextSequence = 0;
    acked = 0;
    terminal = null;
    unconfirmedKind = null;
    deps.clearFeedback?.();
    deps.lockInteractions(true);
    deps.stopPlayback();
    setState(AttemptState.STARTING);
    const captureTimeNs = deps.nowNs();
    lastCaptureNs = captureTimeNs;
    const response = await deps.client.begin({
      deliveryId: lesson.preview.delivery_id,
      artifactDigest: lesson.preview.assignment_artifact_digest,
      behaviorDigest: lesson.preview.assignment_behavior_digest,
      deviceId: deviceLabel(device),
      captureTimeNs,
    });
    if (!alive(token)) {
      const lateId = response?.body?.attempt_id;
      if (typeof lateId === "string" && lateId.trim()) {
        void deps.client.cancel({
          attemptId: lateId,
          captureTimeNs: deps.nowNs(),
          keepalive: true,
        });
      }
      return snapshot();
    }
    if (!response.ok || response.status !== 201) {
      deps.lockInteractions(false);
      if (response.status === 0) {
        unconfirmedKind = "begin";
        setState(AttemptState.UNCONFIRMED, "The start request did not finish.");
        return snapshot();
      }
      setState(AttemptState.IDLE, publicAttemptFailure(response));
      return snapshot();
    }
    const accepted = acceptBegin(response.body, lesson.preview, lesson.choice);
    if (!accepted.ok) {
      const attemptId = typeof response.body?.attempt_id === "string" ? response.body.attempt_id : "";
      if (attemptId.trim()) {
        const cancelled = await deps.client.cancel({
          attemptId,
          captureTimeNs: deps.nowNs(),
          keepalive: true,
        });
        if (!alive(token)) return snapshot();
        if (cancelled.status === 0) {
          beginDoc = { attempt_id: attemptId };
          unconfirmedKind = "cancel";
          deps.lockInteractions(false);
          setState(
            AttemptState.UNCONFIRMED,
            "The begin response could not be used, and cancellation was not confirmed.",
          );
          return snapshot();
        }
      }
      if (!alive(token)) return snapshot();
      deps.lockInteractions(false);
      setState(AttemptState.IDLE, "The begin response could not be used.");
      return snapshot();
    }
    let runtime = null;
    try {
      runtime = await deps.replaceRuntime(accepted.body.preparation);
    } catch {
      runtime = null;
    }
    if (!alive(token)) {
      runtime?.dispose?.();
      void deps.client.cancel({
        attemptId: accepted.body.attempt_id,
        captureTimeNs: deps.nowNs(),
        keepalive: true,
      });
      return snapshot();
    }
    if (!runtime) {
      beginDoc = accepted.body;
      await performCancel(token, "The lesson snapshot could not be mounted.");
      return snapshot();
    }
    runtime.setInteractionLock?.(true);
    runtime.setRate?.(1);
    runtime.setLoopEnabled?.(false);
    runtime.restart?.();
    beginDoc = accepted.body;
    lastCaptureNs = captureTimeNs;
    setState(AttemptState.CAPTURING);
    attachIntake(token);
    if (state !== AttemptState.CAPTURING) return snapshot();
    runtime.play?.();
    return snapshot();
  }

  function attachIntake(token) {
    const mine = ++intakeToken;
    const connected = deps.midi.connect(selectedId, (event) => {
      onMidi(mine, token, event);
    }, () => {
      if (mine !== intakeToken || !alive(token)) return;
      if (state === AttemptState.CAPTURING || state === AttemptState.STARTING) {
        void cancel("The MIDI input disconnected.");
      }
    });
    if (connected === false && state === AttemptState.CAPTURING) {
      void cancel("The MIDI input disconnected.");
    }
  }

  function onMidi(mine, token, event) {
    if (mine !== intakeToken || !alive(token) || state !== AttemptState.CAPTURING) return;
    if (event?.device_id !== selectedId) return;
    if (!isSupportedNoteMessage(event?.raw_payload)) return;
    const captureTimeNs = Number.isInteger(event.capture_time_ns) && event.capture_time_ns >= 0
      ? event.capture_time_ns
      : deps.nowNs();
    const practicePositionSeconds = deps.positionSeconds();
    if (queue.length >= QUEUE_LIMIT) {
      void cancel("The capture queue is full.");
      return;
    }
    const sequenceNumber = nextSequence;
    nextSequence += 1;
    if (captureTimeNs > lastCaptureNs) lastCaptureNs = captureTimeNs;
    queue.push(Object.freeze({
      attemptId: beginDoc.attempt_id,
      sequenceNumber,
      captureTimeNs,
      practicePositionSeconds,
      rawPayload: event.raw_payload.map((byte) => byte),
    }));
    void pump(token);
  }

  function pump(token) {
    if (sending) return drain;
    sending = true;
    drain = runPump(token);
    return drain;
  }

  async function runPump(token) {
    let failed = false;
    try {
      while (
        queue.length > 0 &&
        alive(token) &&
        (state === AttemptState.CAPTURING || state === AttemptState.FINISHING)
      ) {
        const item = queue[0];
        const response = await deps.client.append(item);
        if (!alive(token) || beginDoc?.attempt_id !== item.attemptId) return snapshot();
        if (state !== AttemptState.CAPTURING && state !== AttemptState.FINISHING) return snapshot();
        const ack = response.status === 200
          ? acceptAcknowledgement(response.body, beginDoc, acked + 1)
          : { ok: false };
        if (!response.ok || !ack.ok) {
          queue = [];
          failed = true;
          break;
        }
        queue.shift();
        acked = ack.body.accepted_event_count;
        publish();
      }
    } finally {
      sending = false;
    }
    if (!alive(token)) return snapshot();
    if (failed) return performCancel(token, "A captured message was not accepted.");
    if (state === AttemptState.FINISHING && queue.length === 0 && !terminal) {
      terminal = submitFinish(token);
      return terminal;
    }
    return snapshot();
  }

  function finish() {
    if (state !== AttemptState.CAPTURING || terminal) return Promise.resolve(snapshot());
    stopIntake();
    deps.pausePlayback();
    setState(AttemptState.FINISHING);
    return pump(generation);
  }

  async function submitFinish(token) {
    const response = await deps.client.finish({
      attemptId: beginDoc.attempt_id,
      captureTimeNs: terminalNs(),
    });
    if (!alive(token)) return snapshot();
    if (response.status === 0 || !response.body) {
      unconfirmedKind = "finish";
      deps.lockInteractions(false);
      setState(AttemptState.UNCONFIRMED, "The finish request did not finish. Retry finish to read the stored result.");
      return snapshot();
    }
    const accepted = acceptEvaluated(response.body, beginDoc);
    if (!accepted.ok) {
      unconfirmedKind = "finish";
      deps.lockInteractions(false);
      deps.clearFeedback?.();
      setState(AttemptState.UNCONFIRMED, "The evaluation response could not be checked.");
      return snapshot();
    }
    unconfirmedKind = null;
    deps.showEvaluated?.(accepted.body);
    deps.lockInteractions(false);
    setState(AttemptState.EVALUATED);
    return snapshot();
  }

  async function retryFinish() {
    if (state !== AttemptState.UNCONFIRMED || unconfirmedKind !== "finish" || !beginDoc) {
      return snapshot();
    }
    const token = generation;
    terminal = null;
    deps.lockInteractions(true);
    setState(AttemptState.FINISHING);
    terminal = submitFinish(token);
    await terminal;
    return snapshot();
  }

  async function cancel(notice = "The attempt was cancelled.") {
    if (terminal) return terminal;
    if (state !== AttemptState.CAPTURING && state !== AttemptState.FINISHING && state !== AttemptState.STARTING) {
      return snapshot();
    }
    if (!beginDoc?.attempt_id) {
      generation += 1;
      stopIntake();
      deps.stopPlayback();
      deps.lockInteractions(false);
      setState(AttemptState.IDLE, notice);
      return snapshot();
    }
    return performCancel(generation, notice);
  }

  function performCancel(token, notice) {
    if (terminal) return terminal;
    stopIntake();
    deps.pausePlayback();
    queue = [];
    setState(AttemptState.CANCELLING);
    terminal = submitCancel(token, notice);
    return terminal;
  }

  async function submitCancel(token, notice) {
    const response = await deps.client.cancel({
      attemptId: beginDoc.attempt_id,
      captureTimeNs: terminalNs(),
    });
    if (!alive(token)) return snapshot();
    if (response.status === 0 || !response.body) {
      unconfirmedKind = "cancel";
      deps.lockInteractions(false);
      deps.clearFeedback?.();
      setState(AttemptState.UNCONFIRMED, "The cancellation was not confirmed.");
      return snapshot();
    }
    const accepted = acceptInterrupted(response.body, beginDoc);
    if (!accepted.ok) {
      unconfirmedKind = "cancel";
      deps.lockInteractions(false);
      deps.clearFeedback?.();
      setState(AttemptState.UNCONFIRMED, "The cancellation response could not be checked.");
      return snapshot();
    }
    unconfirmedKind = null;
    deps.showInterrupted?.(accepted.body);
    deps.lockInteractions(false);
    setState(AttemptState.INTERRUPTED, notice);
    return snapshot();
  }

  function abandon() {
    const attemptId = beginDoc?.attempt_id;
    const open = ACTIVE.has(state) || state === AttemptState.CAPTURING;
    generation += 1;
    stopIntake();
    queue = [];
    if (attemptId && open) {
      void deps.client.cancel({
        attemptId,
        captureTimeNs: terminalNs(),
        keepalive: true,
      });
    }
    beginDoc = null;
    terminal = null;
    unconfirmedKind = null;
    state = AttemptState.IDLE;
  }

  function noteNaturalEnd() {
    if (state !== AttemptState.CAPTURING) return Promise.resolve(snapshot());
    return finish();
  }

  return {
    enableMidi,
    selectInput,
    start,
    finish,
    retryFinish,
    cancel,
    abandon,
    noteNaturalEnd,
    snapshot,
    get state() {
      return state;
    },
  };
}

/**
 * @param {{ id: string, name?: string }} device
 */
function deviceLabel(device) {
  return typeof device.name === "string" && device.name.trim() ? device.name : device.id;
}
