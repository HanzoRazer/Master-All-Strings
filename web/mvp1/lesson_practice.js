/** Practice page for one chosen local delivery.

Loads a fresh preview, confirms the stored choice, and prepares with that
preview's pins. It does not create a choice, start playback, or retry.
*/

import { LessonDeliveryClient } from "./lesson_delivery_client.js";
import {
  acceptPreparation,
  isChosen,
  isReadyPreview,
  parsePracticeSearch,
  practiceFailureMessage,
} from "./lesson_delivery_validation.js";
import { mountReceivedLessonRuntime } from "./received_lesson_runtime.js";

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
  /** @type {object|null} */
  let runtime = null;
  /** @type {Promise<void>} */
  let idle = Promise.resolve();

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
    for (const control of [
      playButton, pauseButton, restartButton, seek, loopEnabled, soundEnabled, volume,
      ...rateButtons,
    ]) {
      control.disabled = !enabled;
    }
  }

  function stopRuntime() {
    if (!runtime) return;
    const currentRuntime = runtime;
    runtime = null;
    currentRuntime.dispose();
  }

  function showFailure(result, invalid = false) {
    stopRuntime();
    setReady(false);
    soundEnabled.checked = false;
    audioStatus.textContent = "Sound off.";
    setStatus(practiceFailureMessage(result, invalid), true);
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

  async function loadLesson() {
    const token = ++generation;
    stopRuntime();
    setReady(false);
    soundEnabled.checked = false;
    audioStatus.textContent = "Sound off.";
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

    let mounted = null;
    try {
      mounted = await runtimeFactory({
        bundle: accepted.body,
        roots,
        isCurrent: () => current(token),
        onPlayback: (state) => {
          if (!current(token) || runtime !== mounted) return;
          if (state === "playing") setStatus("Playing.");
          if (state === "paused") setStatus("Paused.");
          if (state === "ended") setStatus("Playback ended.");
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
      if (!current(token)) return;
      showFailure(prepared, true);
      return;
    }
    if (!current(token) || !mounted) {
      mounted?.dispose();
      return;
    }
    runtime = mounted;
    renderLesson(preview.body, accepted.body);
    showScoreNotice(mounted);
    setReady(true);
    setStatus("Paused. Playback has not started.");
  }

  playButton.addEventListener("click", () => {
    runtime?.play();
  });
  pauseButton.addEventListener("click", () => {
    runtime?.pause();
  });
  restartButton.addEventListener("click", () => {
    runtime?.restart();
  });
  seek.addEventListener("input", () => {
    if (!runtime) return;
    runtime.seek((Number(seek.value) / 1000) * runtime.transport.durationSeconds);
  });
  for (const button of rateButtons) {
    button.addEventListener("click", () => {
      if (!runtime) return;
      runtime.setRate(Number(button.getAttribute("data-rate") ?? button.dataset.rate));
      for (const other of rateButtons) {
        other.setAttribute("aria-pressed", other === button ? "true" : "false");
      }
    });
  }
  loopEnabled.addEventListener("change", () => {
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
    track(loadLesson());
  });

  if (view && typeof view.addEventListener === "function") {
    view.addEventListener("pagehide", () => {
      hidden = true;
      generation += 1;
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
