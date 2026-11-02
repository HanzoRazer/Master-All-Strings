/** One explicit attempt against the lesson snapshot the server returned.

MIDI intake, the outbound queue, and terminal transitions live here. Musical
comparison does not.
*/

import {
  acceptBeginGateway,
  definitiveBeginRefusal,
  isBeginRequestId,
} from "./received_begin_validation.js";
import {
  acceptAcknowledgement,
  acceptBegin,
  acceptEvaluated,
  acceptInterrupted,
  attemptRejectionNotice,
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
  REJECTED: "REJECTED",
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
  let pumping = null;
  let nextSequence = 0;
  let acked = 0;
  let lastCaptureNs = 0;
  let terminal = null;
  let unconfirmedKind = null;
  let pendingBegin = null;
  let resolving = false;
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
      pendingBegin: pendingBegin !== null,
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

  // The server refused a terminal write. Only a missing or unreadable answer,
  // or a server fault, leaves the outcome open.
  function isRejection(response) {
    return response.status >= 400 && response.status < 500;
  }

  // Every non-success end clears feedback and gives the controls back.
  function settle(next, notice, kind = null) {
    unconfirmedKind = kind;
    deps.clearFeedback?.();
    deps.lockInteractions(false);
    setState(next, notice);
    return snapshot();
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
    if (unconfirmedKind === "finish" || unconfirmedKind === "begin" || pendingBegin) return snapshot();
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
    const key = mintKey();
    if (!key) {
      return settle(
        AttemptState.IDLE,
        "This browser could not create a start key. Refresh the page and try again.",
      );
    }
    const begin = {
      deliveryId: lesson.preview.delivery_id,
      artifactDigest: lesson.preview.assignment_artifact_digest,
      behaviorDigest: lesson.preview.assignment_behavior_digest,
      deviceId: deviceLabel(device),
      captureTimeNs,
    };
    pendingBegin = { key, begin };
    const response = await deps.client.beginRequest({ beginRequestId: key, begin });
    if (!alive(token)) {
      keepaliveResolve();
      return snapshot();
    }
    return applyBeginResponse(token, response, lesson);
  }

  function mintKey() {
    let key = "";
    try {
      const generate = deps.newBeginRequestId || (() => crypto.randomUUID());
      key = generate();
    } catch {
      key = "";
    }
    return isBeginRequestId(key) ? key : null;
  }

  function keepaliveResolve() {
    if (!pendingBegin) return;
    const request = pendingBegin;
    pendingBegin = null;
    void deps.client.resolveBegin({
      beginRequestId: request.key,
      begin: request.begin,
      keepalive: true,
    });
  }

  async function applyBeginResponse(token, response, lesson) {
    if (!response.ok || (response.status !== 201 && response.status !== 200)) {
      deps.lockInteractions(false);
      if (definitiveBeginRefusal(response)) {
        pendingBegin = null;
        return settle(AttemptState.IDLE, publicAttemptFailure(response));
      }
      return settle(AttemptState.UNCONFIRMED, beginUnconfirmedNotice(response), "begin");
    }
    const accepted = acceptBeginGateway(
      response.body,
      pendingBegin?.key,
      lesson.preview,
      lesson.choice,
    );
    if (!alive(token)) {
      keepaliveResolve();
      return snapshot();
    }
    if (!accepted.ok || accepted.status === "PENDING") {
      return settle(AttemptState.UNCONFIRMED, "The start request did not finish.", "begin");
    }
    if (accepted.status === "NO_ATTEMPT") {
      pendingBegin = null;
      return settle(
        AttemptState.IDLE,
        "No attempt is available in this server process.",
      );
    }
    if (accepted.status === "INTERRUPTED") {
      pendingBegin = null;
      // settle() clears feedback, so the interrupted document is shown after it.
      settle(AttemptState.INTERRUPTED, "The unconfirmed attempt was interrupted.");
      deps.showInterrupted?.(accepted.attempt);
      return snapshot();
    }
    const begun = acceptBegin(accepted.attempt, lesson.preview, lesson.choice);
    if (!begun.ok) {
      return settle(AttemptState.UNCONFIRMED, "The start request did not finish.", "begin");
    }
    pendingBegin = null;
    let runtime = null;
    try {
      runtime = await deps.replaceRuntime(begun.body.preparation);
    } catch {
      runtime = null;
    }
    if (!alive(token)) {
      runtime?.dispose?.();
      void deps.client.cancel({
        attemptId: begun.body.attempt_id,
        captureTimeNs: deps.nowNs(),
        keepalive: true,
      });
      return snapshot();
    }
    if (!runtime) {
      beginDoc = begun.body;
      await performCancel(token, "The lesson snapshot could not be mounted.");
      return snapshot();
    }
    // A locked runtime ignores rate, loop, and restart, so set the policy first.
    runtime.setRate?.(1);
    runtime.setLoopEnabled?.(false);
    runtime.restart?.();
    runtime.setInteractionLock?.(true);
    beginDoc = begun.body;
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

  // A pump belongs to one attempt. A stale one still waiting on its append
  // must not stop the next attempt's queue from draining.
  function pump(token) {
    if (pumping === token) return drain;
    pumping = token;
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
      if (pumping === token) pumping = null;
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
    if (isRejection(response)) {
      return settle(AttemptState.REJECTED, attemptRejectionNotice("finish", response));
    }
    if (!response.ok || !response.body) {
      const what = response.status === 0 ? "did not finish" : "failed on the server";
      return settle(
        AttemptState.UNCONFIRMED,
        `The finish request ${what}. Retry finish to read the stored result.`,
        "finish",
      );
    }
    const accepted = acceptEvaluated(response.body, beginDoc);
    if (!accepted.ok) {
      return settle(AttemptState.UNCONFIRMED, "The evaluation response could not be checked.", "finish");
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
    if (isRejection(response)) {
      return settle(AttemptState.REJECTED, attemptRejectionNotice("cancel", response));
    }
    if (!response.ok || !response.body) {
      return settle(AttemptState.UNCONFIRMED, "The cancellation was not confirmed.", "cancel");
    }
    const accepted = acceptInterrupted(response.body, beginDoc);
    if (!accepted.ok) {
      return settle(AttemptState.UNCONFIRMED, "The cancellation response could not be checked.", "cancel");
    }
    unconfirmedKind = null;
    deps.showInterrupted?.(accepted.body);
    deps.lockInteractions(false);
    setState(AttemptState.INTERRUPTED, notice);
    return snapshot();
  }

  async function resolveBegin() {
    if (!pendingBegin || resolving || unconfirmedKind !== "begin") return snapshot();
    resolving = true;
    const token = generation;
    const request = pendingBegin;
    const response = await deps.client.resolveBegin({
      beginRequestId: request.key,
      begin: request.begin,
    });
    resolving = false;
    if (!alive(token) || pendingBegin !== request) return snapshot();
    if (!response.ok || response.status === 202) {
      return settle(AttemptState.UNCONFIRMED, beginUnconfirmedNotice(response), "begin");
    }
    const lesson = deps.getLesson();
    const accepted = acceptBeginGateway(
      response.body,
      request.key,
      lesson?.preview,
      lesson?.choice,
    );
    if (!accepted.ok || accepted.status === "PENDING" || accepted.status === "STARTED") {
      return settle(AttemptState.UNCONFIRMED, "The start request did not finish.", "begin");
    }
    pendingBegin = null;
    if (accepted.status === "NO_ATTEMPT") {
      return settle(AttemptState.IDLE, "No attempt is available in this server process.");
    }
    settle(AttemptState.INTERRUPTED, "The unconfirmed attempt was interrupted.");
    deps.showInterrupted?.(accepted.attempt);
    return snapshot();
  }

  function beginUnconfirmedNotice(response) {
    if (response?.status === 0) return "The start request did not finish.";
    if (response?.status === 202) return "The start is still unresolved. Resolve start again.";
    if (response?.status >= 500) return "The start failed on the server. Resolve start to check it.";
    return "The start request did not finish.";
  }

  function abandon() {
    const attemptId = beginDoc?.attempt_id;
    const open = ACTIVE.has(state) || state === AttemptState.CAPTURING;
    const pending = pendingBegin;
    generation += 1;
    stopIntake();
    queue = [];
    if (pending && !beginDoc) {
      pendingBegin = null;
      void deps.client.resolveBegin({
        beginRequestId: pending.key,
        begin: pending.begin,
        keepalive: true,
      });
    } else if (attemptId && open) {
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
    resolveBegin,
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
