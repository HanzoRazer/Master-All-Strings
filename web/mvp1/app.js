import { AudioScheduler } from "./audio_scheduler.js";
import { AudioReadiness, ReferenceSynth } from "./audio.js";
import { FretboardRenderer, oneStringViewProjection } from "./renderer.js";
import { WebMidiInput } from "./midi_input.js";
import {
  LocalPerformanceApi,
  PerformanceCaptureController,
} from "./performance_capture.js";
import { Transport } from "./transport.js";

const $ = (id) => document.getElementById(id);
const state = {
  payload: null,
  playback: null,
  practice: null,
  demos: [],
  demosById: new Map(),
  instruments: [],
  diagnostics: [],
};

const transport = new Transport();
const midiInput = new WebMidiInput();
const capture = new PerformanceCaptureController({
  midiInput,
  transport,
  api: new LocalPerformanceApi(),
});
const synth = new ReferenceSynth();
const scheduler = new AudioScheduler({
  transport,
  synth,
  onDiagnostic: (item) => {
    state.diagnostics.push({ ...item, capturedAtMs: performance.now() });
    if (state.diagnostics.length > 200) state.diagnostics.shift();
    if (item.type === "scheduled") {
      $("audioStatus").dataset.lastScheduledEvent = item.eventId;
      $("audioStatus").dataset.mappingErrorMs = item.mappingErrorMs.toFixed(6);
    }
  },
});
scheduler.setEnabled(false);
scheduler.start();

const renderer = new FretboardRenderer({
  laneLabels: $("laneLabels"),
  scrollViewport: $("scrollViewport"),
  scrollCanvas: $("scrollCanvas"),
  playLine: $("playLine"),
  gutterNotes: $("gutterNotes"),
  unplayableGutter: $("unplayableGutter"),
  neckMap: $("neckMap"),
  instrumentTitle: $("instrumentTitle"),
});

transport.subscribe((event) => {
  if (event.type === "complete") $("statusLine").textContent = "Complete";
  if (event.type === "loop-complete")
    $("statusLine").textContent = "Loop complete";
});

function showError(message) {
  $("errorOverlay").classList.remove("hidden");
  $("errorMessage").textContent = message;
  $("statusLine").textContent = message;
}

function clearError() {
  $("errorOverlay").classList.add("hidden");
}

function setAudioStatus(message, readiness = synth.readiness) {
  $("audioStatus").textContent = message;
  $("audioStatus").dataset.readiness = readiness;
}

function setLessonInfo(projection, payload) {
  const info = $("lessonInfo");
  info.replaceChildren();
  const rows = [
    ["Title", projection.title],
    ["Instrument", projection.instrument.display_name],
    ["Selection policy", projection.selection_policy],
    ["Objective", projection.objective || "—"],
    ["Teacher note", projection.teacher_note || "—"],
    ["Projection digest", projection.projection_digest],
  ];
  rows.forEach(([label, value]) => {
    const wrap = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = value;
    wrap.append(dt, dd);
    info.appendChild(wrap);
  });
  $("sourceMeta").textContent =
    `${payload.summary_title} · ${payload.instrument_id} · ${projection.notes.length} events`;
  $("warningList").replaceChildren(
    ...(payload.warnings || []).map((warning) => {
      const li = document.createElement("li");
      li.textContent = warning;
      return li;
    }),
  );
}

function demoForPayload(payload) {
  return (
    state.demosById.get(payload.demo_id) ||
    state.demosById.get(payload.projection?.content_id) ||
    null
  );
}

function assertSharedIdentity(payload, playback, practice) {
  const identities = [
    [payload.projection.assignment_id, payload.projection.content_id],
    [playback.assignment_id, playback.content_id],
    [practice.policy.assignment_id, practice.policy.content_id],
  ].map((pair) => pair.join("\u0000"));
  if (new Set(identities).size !== 1) {
    throw new Error(
      "Lesson visual, audio, and practice artifacts do not match",
    );
  }
}

function commitLoop() {
  if (!$("loopEnabled").checked) {
    transport.clearLoop();
    renderer.setLoop(null);
    $("loopRange").textContent = "Loop off";
    return;
  }
  const startSeconds = Number($("loopStart").value);
  const endSeconds = Number($("loopEnd").value);
  try {
    transport.setLoop({
      startSeconds,
      endSeconds,
      targetRepetitions: state.practice?.policy.loop.target_repetitions ?? null,
    });
    renderer.setLoop(transport.loop);
    $("loopRange").textContent =
      `${startSeconds.toFixed(2)}s–${endSeconds.toFixed(2)}s`;
  } catch (error) {
    $("loopEnabled").checked = false;
    transport.clearLoop();
    renderer.setLoop(null);
    $("loopRange").textContent = error.message;
  }
}

function configureLoopControls(practice, duration) {
  for (const input of [$("loopStart"), $("loopEnd")]) {
    input.max = String(duration);
    input.step = "0.01";
  }
  $("loopStart").value = String(practice.runtime.loop_start_seconds);
  $("loopEnd").value = String(practice.runtime.loop_end_seconds);
  $("loopEnabled").checked = practice.policy.loop.enabled;
  commitLoop();
}

function applySessionArtifacts(payload, playback, practice) {
  const projection = payload?.projection;
  if (!projection || projection.projection_version !== "1.0.0") {
    throw new Error("Unsupported projection version");
  }
  if (playback?.schema_version !== "1.0.0" || !practice?.policy) {
    throw new Error("Unsupported practice artifact version");
  }
  assertSharedIdentity(payload, playback, practice);
  clearError();
  transport.pause();
  scheduler.panic("lesson-change");
  transport.restart();
  transport.setDuration(playback.total_seconds);
  scheduler.loadPlan(playback);
  state.payload = payload;
  state.playback = playback;
  state.practice = practice;
  renderer.load(projection);
  const oneString = payload.teaching_aids?.one_string || [];
  $("teachingString").replaceChildren(
    ...oneString.map((item) => {
      const option = document.createElement("option");
      option.value = item.requested_string_id;
      option.textContent = item.display_label;
      return option;
    }),
  );
  $("teachingView").value = "normal";
  $("teachingString").disabled = true;
  const zoneAvailable = projection.notes.some((note) => note.zone_semantics);
  $("zoneOverlay").disabled = !zoneAvailable;
  if (!zoneAvailable) $("zoneOverlay").checked = false;
  renderer.setZoneOverlay(zoneAvailable && $("zoneOverlay").checked);
  $("zoneStatus").textContent = zoneAvailable
    ? "Authoritative Zone semantics available"
    : "No Zone semantic artifact";
  setLessonInfo(projection, payload);
  configureLoopControls(practice, playback.total_seconds);
  $("seek").value = "0";
  $("statusLine").textContent = "Ready";
  $("repeatCount").textContent = "0";

  const demo = demoForPayload(payload);
  if (demo) $("demoSelect").value = demo.demo_id;
  $("instrumentSelect").value =
    payload.instrument_id || projection.instrument.instrument_id;
  $("lessonDescription").textContent =
    demo?.description || projection.description || "";
  $("knownLimitations").textContent = (demo?.known_limitations || []).length
    ? `Known limitations: ${demo.known_limitations.join(", ")}`
    : "";
}

function renderTeachingView() {
  const projection = state.payload?.projection;
  if (!projection) return;
  if ($("teachingView").value === "normal") {
    $("teachingString").disabled = true;
    renderer.load(projection);
  } else {
    $("teachingString").disabled = false;
    const options = state.payload.teaching_aids?.one_string || [];
    const selected = options.find(
      (item) => item.requested_string_id === $("teachingString").value,
    );
    renderer.load(oneStringViewProjection(projection, selected));
  }
  renderer.setZoneOverlay($("zoneOverlay").checked);
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to load ${path}`);
  return response.json();
}

function sessionPathsForDemo(demoId) {
  return [
    `./projections/${demoId}.json`,
    `./playback/${demoId}.json`,
    `./practice/${demoId}.json`,
  ];
}

async function loadSession(paths) {
  const artifacts = await Promise.all(paths.map((path) => loadJson(path)));
  applySessionArtifacts(...artifacts);
}

async function loadInitialSession() {
  const requested = new URLSearchParams(window.location.search).get(
    "projection",
  );
  if (requested) {
    if (!/^[\w-]+(\/[\w-]+)*\.json$/.test(requested)) {
      throw new Error(`Refusing to load projection path: ${requested}`);
    }
    const directory = requested.split("/").slice(0, -1).join("/");
    return loadSession([
      `./${requested}`,
      `./${directory}/playback.json`,
      `./${directory}/practice.json`,
    ]);
  }
  if (!state.demos.length) throw new Error("No lesson available");
  return loadSession(sessionPathsForDemo(state.demos[0].demo_id));
}

async function bootstrap() {
  try {
    const [demos, instruments] = await Promise.all([
      loadJson("./demos.json").catch(() => ({ demos: [] })),
      loadJson("./instruments.json").catch(() => []),
    ]);
    state.demos = demos.demos || [];
    state.demosById = new Map(state.demos.map((demo) => [demo.demo_id, demo]));
    state.instruments = instruments;
    $("demoSelect").replaceChildren(
      ...state.demos.map((demo) => {
        const option = document.createElement("option");
        option.value = demo.demo_id;
        option.textContent = demo.title;
        return option;
      }),
    );
    $("instrumentSelect").replaceChildren(
      ...state.instruments.map((item) => {
        const option = document.createElement("option");
        option.value = item.instrument_id;
        option.textContent = item.experimental
          ? `${item.display_name} (experimental)`
          : item.display_name;
        return option;
      }),
    );
    await loadInitialSession();
  } catch (error) {
    showError(error.message || "Unable to load lesson");
  }
}

async function activateAudio() {
  setAudioStatus("Initializing Reference Synth…", AudioReadiness.INITIALIZING);
  try {
    await synth.initialize();
    scheduler.setEnabled(true);
    setAudioStatus("Reference Synth ready", AudioReadiness.READY);
    return true;
  } catch (error) {
    scheduler.setEnabled(false);
    setAudioStatus(`Audio failed: ${error.message}`, AudioReadiness.FAILED);
    return false;
  }
}

function tick(now) {
  const seconds = transport.positionSeconds(now);
  $("clockReadout").textContent =
    `${seconds.toFixed(2)}s · ${transport.playbackRate.toFixed(2)}×`;
  if (transport.durationSeconds > 0) {
    $("seek").value = String(
      Math.round((seconds / transport.durationSeconds) * 1000),
    );
  }
  $("repeatCount").textContent = String(transport.repetitionCount);
  $("audioStatus").dataset.activeVoices = String(synth.registry.size);
  document.body.dataset.transportPositionSeconds = seconds.toFixed(6);
  renderer.renderFrame(seconds);
  requestAnimationFrame(tick);
}

$("btnPlay").addEventListener("click", async () => {
  if ($("soundEnabled").checked && synth.readiness !== AudioReadiness.READY) {
    if (!(await activateAudio())) return;
  }
  transport.play();
  $("statusLine").textContent = "Playing";
});
$("btnPause").addEventListener("click", () => {
  transport.pause();
  $("statusLine").textContent = "Paused";
});
$("btnRestart").addEventListener("click", () => {
  transport.restart();
  $("statusLine").textContent = "Restarted";
});
$("seek").addEventListener("input", (event) => {
  transport.seek(
    (Number(event.target.value) / 1000) * transport.durationSeconds,
  );
});
document.querySelectorAll(".rates button").forEach((button) => {
  button.addEventListener("click", () => {
    document
      .querySelectorAll(".rates button")
      .forEach((node) => node.classList.remove("active"));
    button.classList.add("active");
    transport.setRate(button.dataset.rate);
  });
});
$("soundEnabled").addEventListener("change", async (event) => {
  if (event.target.checked) {
    if (!(await activateAudio())) event.target.checked = false;
  } else {
    scheduler.setEnabled(false);
    setAudioStatus("Sound off", synth.readiness);
  }
});
$("masterVolume").addEventListener("input", (event) => {
  synth.setVolume(Number(event.target.value));
});
$("loopEnabled").addEventListener("change", commitLoop);
$("loopStart").addEventListener("change", commitLoop);
$("loopEnd").addEventListener("change", commitLoop);
$("btnMidiPermission").addEventListener("click", async () => {
  $("captureStatus").textContent = await midiInput.requestPermission();
  $("midiDevice").replaceChildren(
    ...midiInput.devices().map((device) => {
      const option = document.createElement("option");
      option.value = device.id;
      option.textContent = device.name;
      return option;
    }),
  );
});
$("btnArm").addEventListener("click", async () => {
  $("captureStatus").textContent = (await capture.arm($("midiDevice").value))
    ? "armed"
    : "disconnected";
});
$("btnStartAttempt").addEventListener("click", async () => {
  await capture.startAttempt();
  $("captureStatus").textContent = "capturing";
});
$("btnStopAttempt").addEventListener("click", async () => {
  const evidence = await capture.stopAttempt();
  $("captureStatus").textContent = evidence?.status || "complete";
  $("observedCount").textContent = String(capture.count);
  renderer.setObservedEvidence(evidence?.observed_events || []);
});
$("zoneOverlay").addEventListener("change", (event) => {
  renderer.setZoneOverlay(event.target.checked);
  $("zoneStatus").textContent = event.target.checked
    ? "Zone Colors on"
    : "Zone Colors off";
});
$("teachingView").addEventListener("change", renderTeachingView);
$("teachingString").addEventListener("change", renderTeachingView);

let resizePending = false;
window.addEventListener("resize", () => {
  if (resizePending) return;
  resizePending = true;
  requestAnimationFrame(() => {
    resizePending = false;
    renderer.resize();
  });
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden && transport.playing) {
    transport.pause();
    $("statusLine").textContent = "Paused while tab hidden";
  }
});
$("demoSelect").addEventListener("change", async (event) => {
  transport.pause();
  scheduler.panic("lesson-change");
  try {
    await loadSession(sessionPathsForDemo(event.target.value));
    $("statusLine").textContent = `Loaded ${event.target.value}`;
  } catch (error) {
    showError(error.message || "Unable to load lesson");
  }
});

function captureDiagnostics() {
  const latestSchedule =
    [...state.diagnostics]
      .reverse()
      .find((item) => item.type === "scheduled") || null;
  const audioContextTime = synth.context?.currentTime ?? null;
  return Object.freeze({
    capturedAtMs: performance.now(),
    transport: transport.snapshot(),
    visual: renderer.diagnostics(),
    audio: {
      readiness: synth.readiness,
      activeVoices: synth.registry.size,
      latestSchedule,
      audioContextTime,
      mappingErrorMs: latestSchedule?.mappingErrorMs ?? null,
    },
  });
}

window.__mvp2a = {
  state,
  transport,
  synth,
  scheduler,
  renderer,
  loadSession,
  captureDiagnostics,
};
bootstrap();
requestAnimationFrame(tick);
