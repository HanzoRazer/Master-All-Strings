/** Practice page for one chosen local delivery.

Loads a fresh preview, confirms the stored choice, and prepares with that
preview's pins. An explicit attempt uses the Stage 7 routes and the
preparation those routes return. Reference practice stays available when no
attempt is active.
*/

import { LessonDeliveryClient } from "./lesson_delivery_client.js";
import {
  acceptPreparation,
  isChosen,
  isReadyPreview,
  parsePracticeSearch,
  practiceFailureMessage,
} from "./lesson_delivery_validation.js";
import { WebMidiInput } from "./midi_input.js";
import { ReceivedAttemptClient } from "./received_attempt_client.js";
import {
  AttemptState,
  createReceivedAttemptController,
} from "./received_attempt_controller.js";
import {
  clearAttemptFeedback,
  presentGuidance,
  renderCapturedEvidence,
  renderEvaluatedFeedback,
  renderInterruptedFeedback,
} from "./received_attempt_feedback.js";
import { mountReceivedLessonRuntime } from "./received_lesson_runtime.js";

const BUSY = new Set([
  AttemptState.STARTING,
  AttemptState.CAPTURING,
  AttemptState.FINISHING,
  AttemptState.CANCELLING,
]);

/**
 * @param {ParentNode} root
 * @param {object} [options]
 */
export function mountLessonPractice(root, options = {}) {
  const document = root.ownerDocument;
  if (!document) throw new Error("lesson practice root has no document");
  const client = options.client ?? new LessonDeliveryClient();
  const location = options.location ?? document.defaultView?.location ?? { search: "" };
  const view = options.view ?? document.defaultView;
  const runtimeFactory = options.runtimeFactory ?? ((spec) => mountReceivedLessonRuntime({
    ...spec,
    roots: spec.roots,
  }));
  const nowNs = options.nowNs ?? (() => Math.round(globalThis.performance.now() * 1_000_000));
  const midi = options.midi ?? new WebMidiInput({
    fakeMode: false,
    navigatorObject: view?.navigator ?? {},
  });
  const attemptClient = options.attemptClient ?? new ReceivedAttemptClient();

  const statusEl = required(root, "#status");
  const titleEl = required(root, "#lesson-title");
  const objectiveEl = required(root, "#lesson-objective");
  const noteEl = required(root, "#teacher-note");
  const instrumentEl = required(root, "#instrument-name");
  const deliveryEl = required(root, "#identity-delivery");
  const assignmentEl = required(root, "#identity-assignment");
  const contentEl = required(root, "#identity-content");
  const warningsEl = required(root, "#warning-list");
  const unsupportedEl = required(root, "#unsupported-list");
  const unresolvedEl = required(root, "#unresolved-list");
  const scoreNotice = required(root, "#score-notice");
  const clockEl = required(root, "#clock");
  const repetitionEl = required(root, "#repetition-count");
  const loopEnabled = required(root, "#loop-enabled");
  const loopBounds = required(root, "#loop-bounds");
  const loopTarget = required(root, "#loop-target");
  const soundEnabled = required(root, "#sound-enabled");
  const volume = required(root, "#master-volume");
  const audioStatus = required(root, "#audio-status");
  const playButton = required(root, "#btn-play");
  const pauseButton = required(root, "#btn-pause");
  const restartButton = required(root, "#btn-restart");
  const seek = required(root, "#seek");
  const refreshButton = required(root, "#refresh-lesson");
  const midiInput = required(root, "#midi-input");
  const midiStatus = required(root, "#midi-status");
  const enableMidi = required(root, "#btn-enable-midi");
  const startAttempt = required(root, "#btn-start-attempt");
  const finishAttempt = required(root, "#btn-finish-attempt");
  const cancelAttempt = required(root, "#btn-cancel-attempt");
  const retryFinish = required(root, "#btn-retry-finish");
  const attemptStatus = required(root, "#attempt-status");
  const attemptCount = required(root, "#attempt-count");
  const attemptFeedback = required(root, "#attempt-feedback");
  const attemptEvidence = required(root, "#attempt-evidence");
  const evidenceBody = required(root, "#attempt-evidence-body");
  const roots = {
    fretboard: {
      laneLabels: required(root, "#laneLabels"),
      scrollViewport: required(root, "#scrollViewport"),
      scrollCanvas: required(root, "#scrollCanvas"),
      playLine: required(root, "#playLine"),
      gutterNotes: required(root, "#gutterNotes"),
      unplayableGutter: required(root, "#unplayableGutter"),
      neckMap: required(root, "#neckMap"),
      instrumentTitle: required(root, "#instrumentTitle"),
    },
    tab: required(root, "#tabView"),
    notation: required(root, "#notationView"),
  };
  const rateButtons = [...root.querySelectorAll("[data-rate]")];

  let generation = 0;
  let hidden = false;
  let practiceLocked = false;
  /** @type {object|null} */
  let runtime = null;
  /** @type {{ preview: object, choice: object }|null} */
  let lesson = null;
  /** @type {object|null} */
  let referenceBundle = null;
  /** @type {Promise<void>} */
  let idle = Promise.resolve();

  const controller = createReceivedAttemptController({
    client: attemptClient,
    midi,
    nowNs,
    isCurrent: () => !hidden,
    getLesson: () => lesson,
    positionSeconds: () => runtime?.transport.positionSeconds() ?? 0,
    lockInteractions,
    stopPlayback,
    pausePlayback: stopPlayback,
    replaceRuntime: (bundle) => mountBundle(bundle, generation),
    clearFeedback,
    showEvaluated,
    showInterrupted,
    onChange: showAttempt,
  });

  function track(promise) {
    idle = promise.then(
      () => undefined,
      () => undefined,
    );
    return promise;
  }

  function current(token) {
    return token === generation && !hidden;
  }

  function setStatus(text, isError = false) {
    statusEl.textContent = text;
    statusEl.classList.toggle("is-error", isError);
  }

  function setReady(enabled) {
    const on = enabled && !practiceLocked;
    for (const control of [
      playButton, pauseButton, restartButton, seek, loopEnabled, soundEnabled, volume,
      ...rateButtons,
    ]) {
      if (control === soundEnabled || control === volume) {
        control.disabled = !enabled;
        continue;
      }
      control.disabled = !on;
    }
  }

  function lockInteractions(locked) {
    const wasLocked = practiceLocked;
    practiceLocked = locked;
    refreshButton.disabled = locked;
    midiInput.disabled = locked || midi.devices().length === 0;
    if (locked) {
      loopEnabled.checked = false;
      for (const button of rateButtons) {
        button.setAttribute("aria-pressed", button.getAttribute("data-rate") === "1" ? "true" : "false");
      }
    }
    runtime?.setInteractionLock?.(locked);
    if (!locked && wasLocked) restoreReferenceControls();
    setReady(Boolean(runtime));
    syncAttemptButtons();
  }

  function restoreReferenceControls() {
    if (!runtime || !referenceBundle) return;
    runtime.setInteractionLock?.(false);
    runtime.setRate?.(1);
    const enabled = Boolean(referenceBundle.practice?.policy?.loop?.enabled);
    runtime.setLoopEnabled?.(enabled);
    loopEnabled.checked = enabled;
  }

  function stopRuntime() {
    if (!runtime) return;
    const currentRuntime = runtime;
    runtime = null;
    currentRuntime.dispose();
  }

  function stopPlayback() {
    runtime?.pause?.();
    runtime?.silence?.();
  }

  function showFailure(result, invalid = false) {
    stopRuntime();
    lesson = null;
    referenceBundle = null;
    practiceLocked = false;
    setReady(false);
    soundEnabled.checked = false;
    audioStatus.textContent = "Sound off.";
    setStatus(practiceFailureMessage(result, invalid), true);
    syncAttemptButtons();
  }

  function renderTextList(list, items) {
    const nodes = items.map((item) => {
      const line = document.createElement("li");
      line.textContent = item;
      return line;
    });
    list.replaceChildren(...nodes);
  }

  function renderLesson(preview, bundle) {
    titleEl.textContent = preview.title;
    objectiveEl.textContent = preview.instruction_objective ?? "";
    noteEl.textContent = preview.teacher_note ?? "";
    const instrument = bundle.projection.projection.instrument;
    const instrumentLabel = instrument.display_name || instrument.instrument_id;
    instrumentEl.textContent = instrumentLabel;
    roots.fretboard.instrumentTitle.textContent = instrumentLabel;
    deliveryEl.textContent = preview.delivery_id;
    assignmentEl.textContent = preview.assignment_id;
    contentEl.textContent = preview.content_id;
    const playbackWarnings = bundle.playback.warnings.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item.message === "string") return item.message;
      if (item && typeof item.code === "string") return item.code;
      return "";
    }).filter((item) => item.length > 0);
    renderTextList(warningsEl, [...bundle.projection.warnings, ...playbackWarnings]);
    renderTextList(unsupportedEl, [
      ...bundle.projection.unsupported_features,
      ...bundle.playback.unsupported_features.filter((item) => typeof item === "string"),
    ]);
    const unresolved = bundle.projection.projection.notes
      .filter((note) => note.status !== "selected" || note.unresolved_reason)
      .map((note) => `${note.event_id}: ${note.unresolved_reason || note.status}`);
    renderTextList(unresolvedEl, unresolved);
    const loop = bundle.practice.policy.loop;
    const bounds = bundle.practice.runtime;
    loopEnabled.checked = loop.enabled;
    loopBounds.textContent = `${bounds.loop_start_seconds}s to ${bounds.loop_end_seconds}s`;
    loopTarget.textContent = loop.target_repetitions == null
      ? "Repetition target: until you stop"
      : `Repetition target: ${loop.target_repetitions}`;
    repetitionEl.textContent = "0";
    clockEl.textContent = "0.00s";
    seek.value = "0";
    soundEnabled.checked = false;
    audioStatus.textContent = "Sound off.";
  }

  function showScoreNotice(mounted) {
    const views = mounted.coordinator?.views;
    if (!views) {
      scoreNotice.hidden = true;
      scoreNotice.textContent = "";
      return;
    }
    const failed = ["tab", "notation"].filter((name) => views[name] && !views[name].mounted);
    if (failed.length === 0) {
      scoreNotice.hidden = true;
      scoreNotice.textContent = "";
      return;
    }
    scoreNotice.hidden = false;
    scoreNotice.textContent = `${failed.join(" and ")} could not be drawn. The rest of the lesson stays available.`;
  }

  function clearFeedback() {
    clearAttemptFeedback(attemptFeedback);
    clearAttemptFeedback(evidenceBody);
    attemptFeedback.hidden = true;
    attemptEvidence.open = false;
  }

  function showEvaluated(body) {
    attemptFeedback.hidden = false;
    renderEvaluatedFeedback(attemptFeedback, body);
    presentGuidance(runtime?.coordinator, body.guidance);
    renderCapturedEvidence(evidenceBody, body);
    attemptEvidence.open = false;
  }

  function showInterrupted(body) {
    attemptFeedback.hidden = false;
    renderInterruptedFeedback(attemptFeedback, body);
    renderCapturedEvidence(evidenceBody, body);
    attemptEvidence.open = true;
  }

  function showAttempt(snap, notice = "") {
    attemptCount.textContent = `Acknowledged messages: ${snap.acked}`;
    attemptStatus.textContent = notice || attemptLabel(snap.state);
    renderDevices(snap.devices, snap.selectedId);
    midiStatus.textContent = midiLabel(snap.midiState);
    const busy = BUSY.has(snap.state);
    if (busy && !practiceLocked) lockInteractions(true);
    if (!busy && practiceLocked) {
      practiceLocked = false;
      restoreReferenceControls();
      setReady(Boolean(runtime));
      refreshButton.disabled = false;
      midiInput.disabled = midi.devices().length === 0;
    }
    syncAttemptButtons();
  }

  function syncAttemptButtons() {
    const snap = controller.snapshot();
    const busy = BUSY.has(snap.state);
    startAttempt.disabled = busy || !lesson || !snap.selectedId || snap.unconfirmedKind === "finish";
    finishAttempt.disabled = snap.state !== AttemptState.CAPTURING;
    cancelAttempt.hidden = snap.state !== AttemptState.CAPTURING;
    pauseButton.hidden = snap.state === AttemptState.CAPTURING;
    retryFinish.hidden = snap.unconfirmedKind !== "finish";
    enableMidi.disabled = busy;
  }

  function renderDevices(devices, selectedId) {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select an input";
    const options = devices.map((device) => {
      const option = document.createElement("option");
      option.value = device.id;
      option.textContent = device.name || device.id;
      return option;
    });
    midiInput.replaceChildren(placeholder, ...options);
    midiInput.value = selectedId || "";
    midiInput.disabled = practiceLocked || devices.length === 0;
  }

  async function mountBundle(bundle, token) {
    stopRuntime();
    let mounted = null;
    try {
      mounted = await runtimeFactory({
        bundle,
        roots,
        isCurrent: () => current(token),
        onPlayback: (playbackState) => {
          if (!current(token) || runtime !== mounted) return;
          if (controller.state === AttemptState.CAPTURING && playbackState === "ended") {
            track(controller.noteNaturalEnd());
            return;
          }
          if (practiceLocked) return;
          if (playbackState === "playing") setStatus("Playing.");
          if (playbackState === "paused") setStatus("Paused.");
          if (playbackState === "ended") setStatus("Playback ended.");
        },
        onFrame: (frame) => {
          if (!current(token) || runtime !== mounted) return;
          clockEl.textContent = `${frame.positionSeconds.toFixed(2)}s`;
          repetitionEl.textContent = String(frame.repetitionCount);
          audioStatus.dataset.scheduledNotes = String(frame.scheduledNotes ?? 0);
          if (document.activeElement !== seek && mounted.transport.durationSeconds > 0) {
            seek.value = String(Math.round(
              (frame.positionSeconds / mounted.transport.durationSeconds) * 1000,
            ));
          }
        },
      });
    } catch {
      if (mounted?.dispose) mounted.dispose();
      return null;
    }
    if (!current(token) || !mounted) {
      mounted?.dispose();
      return null;
    }
    runtime = mounted;
    referenceBundle = bundle;
    if (lesson) renderLesson(lesson.preview, bundle);
    if (practiceLocked) loopEnabled.checked = false;
    showScoreNotice(mounted);
    soundEnabled.checked = false;
    audioStatus.textContent = "Sound off.";
    return mounted;
  }

  async function loadLesson() {
    const token = ++generation;
    controller.abandon();
    clearFeedback();
    attemptStatus.textContent = "No attempt.";
    attemptCount.textContent = "Acknowledged messages: 0";
    lesson = null;
    referenceBundle = null;
    practiceLocked = false;
    stopRuntime();
    setReady(false);
    soundEnabled.checked = false;
    audioStatus.textContent = "Sound off.";
    syncAttemptButtons();
    const parsed = parsePracticeSearch(location.search || "");
    if (!parsed.ok) {
      setStatus("Open practice from the inbox. This page needs one delivery id.", true);
      return;
    }
    const deliveryId = parsed.deliveryId;
    setStatus("Loading the lesson.");

    const preview = await client.preview(deliveryId);
    if (!current(token)) return;
    if (!isReadyPreview(preview, deliveryId)) {
      showFailure(preview);
      return;
    }

    const choice = await client.getChoice(deliveryId);
    if (!current(token)) return;
    if (!isChosen(choice, preview.body)) {
      showFailure(choice, Boolean(choice?.ok));
      return;
    }

    const prepared = await client.prepare(
      deliveryId,
      preview.body.assignment_artifact_digest,
      preview.body.assignment_behavior_digest,
    );
    if (!current(token)) return;
    const accepted = acceptPreparation(prepared, preview.body, choice.body);
    if (!accepted.ok) {
      showFailure(prepared, accepted.invalid);
      return;
    }

    lesson = { preview: preview.body, choice: choice.body };
    const mounted = await mountBundle(accepted.body, token);
    if (!current(token)) return;
    if (!mounted) {
      showFailure(prepared, true);
      return;
    }
    setReady(true);
    syncAttemptButtons();
    setStatus("Paused. Playback has not started.");
  }

  playButton.addEventListener("click", () => {
    if (practiceLocked) return;
    runtime?.play();
  });
  pauseButton.addEventListener("click", () => {
    if (practiceLocked) return;
    runtime?.pause();
  });
  restartButton.addEventListener("click", () => {
    if (practiceLocked) return;
    runtime?.restart();
  });
  seek.addEventListener("input", () => {
    if (!runtime || practiceLocked) return;
    runtime.seek((Number(seek.value) / 1000) * runtime.transport.durationSeconds);
  });
  for (const button of rateButtons) {
    button.addEventListener("click", () => {
      if (!runtime || practiceLocked) return;
      runtime.setRate(Number(button.getAttribute("data-rate") ?? button.dataset.rate));
      for (const other of rateButtons) {
        other.setAttribute("aria-pressed", other === button ? "true" : "false");
      }
    });
  }
  loopEnabled.addEventListener("change", () => {
    if (practiceLocked) return;
    runtime?.setLoopEnabled(loopEnabled.checked);
  });
  soundEnabled.addEventListener("change", () => {
    const currentRuntime = runtime;
    if (!currentRuntime) {
      soundEnabled.checked = false;
      return;
    }
    if (!soundEnabled.checked) {
      currentRuntime.disableSound();
      audioStatus.textContent = "Sound off.";
      return;
    }
    track(currentRuntime.enableSound().then((result) => {
      if (runtime !== currentRuntime) return;
      if (!result?.ok) {
        soundEnabled.checked = false;
        audioStatus.textContent = "Sound is unavailable.";
        return;
      }
      audioStatus.textContent = "Sound ready.";
    }));
  });
  volume.addEventListener("input", () => {
    runtime?.setVolume(Number(volume.value));
  });
  refreshButton.addEventListener("click", () => {
    if (practiceLocked) return;
    track(loadLesson());
  });
  enableMidi.addEventListener("click", () => {
    track(controller.enableMidi());
  });
  midiInput.addEventListener("change", () => {
    controller.selectInput(midiInput.value);
  });
  startAttempt.addEventListener("click", () => {
    track(controller.start());
  });
  finishAttempt.addEventListener("click", () => {
    track(controller.finish());
  });
  cancelAttempt.addEventListener("click", () => {
    track(controller.cancel());
  });
  retryFinish.addEventListener("click", () => {
    track(controller.retryFinish());
  });

  if (view && typeof view.addEventListener === "function") {
    view.addEventListener("pagehide", () => {
      hidden = true;
      generation += 1;
      controller.abandon();
      stopRuntime();
      setReady(false);
      soundEnabled.checked = false;
    });
    view.addEventListener("pageshow", (event) => {
      if (!hidden && !event?.persisted) return;
      hidden = false;
      track(loadLesson());
    });
  }

  track(loadLesson());

  return {
    idle: () => idle,
    refresh: () => track(loadLesson()),
  };
}

function bootLessonPractice() {
  if (typeof document === "undefined") return;
  const root = document.querySelector("[data-lesson-practice]");
  if (!root) return;
  mountLessonPractice(root);
}

bootLessonPractice();

function required(root, selector) {
  const node = root.querySelector(selector);
  if (!node) throw new Error(`lesson practice is missing ${selector}`);
  return node;
}

/**
 * @param {string} state
 */
function attemptLabel(state) {
  if (state === AttemptState.CAPTURING) return "Capturing.";
  if (state === AttemptState.STARTING) return "Starting the attempt.";
  if (state === AttemptState.FINISHING) return "Finishing the attempt.";
  if (state === AttemptState.CANCELLING) return "Cancelling the attempt.";
  if (state === AttemptState.EVALUATED) return "Evaluated.";
  if (state === AttemptState.INTERRUPTED) return "Interrupted.";
  if (state === AttemptState.UNCONFIRMED) return "The last attempt write was not confirmed.";
  return "No attempt.";
}

/**
 * @param {string} state
 */
function midiLabel(state) {
  if (state === "ready") return "MIDI input is ready.";
  if (state === "permission_denied") return "MIDI permission was denied. Reference practice is still available.";
  if (state === "unsupported") return "This browser has no MIDI input. Reference practice is still available.";
  if (state === "disconnected") return "The MIDI input disconnected. Reference practice is still available.";
  if (state === "failed") return "MIDI input failed. Reference practice is still available.";
  return "MIDI input is off.";
}
