import { AudioScheduler } from "./audio_scheduler.js";
import { AudioReadiness, ReferenceSynth } from "./audio.js";
import {
  FretboardRenderer,
  oneStringViewProjection,
  zoneReadoutText,
} from "./renderer.js";
import { WebMidiInput } from "./midi_input.js";
import {
  LocalPerformanceApi,
  PerformanceCaptureController,
} from "./performance_capture.js";
import {
  LocalEducationApi,
  PracticeActionController,
} from "./practice_actions.js";
import { focusRangeFromEvaluation, renderResultsPanel } from "./results.js";
import { Transport } from "./transport.js";
import { MediaPlayerController, MediaSyncMode } from "./media-player.js";
import { MediaSyncFollower } from "./media-sync.js";
import {
  TeachingTimeline,
  resolveFocusRangeSeconds,
  secondsAtTick,
} from "./teaching-timeline.js";
import { ScoreViewCoordinator } from "./score-view.js";
import {
  buildScoreDiagnostics,
  createFretboardSelectionHandler,
  createGuidanceAcceptHandler,
  createScoreSeekHandler,
  presentTeachingGuidance,
} from "./score-shell.js";
import { NOTATION_LIMITATIONS } from "./notation-view.js";

const $ = (id) => document.getElementById(id);
const state = {
  payload: null,
  playback: null,
  practice: null,
  demos: [],
  demosById: new Map(),
  instruments: [],
  diagnostics: [],
  stage: "lesson",
  lastEvaluation: null,
};

const transport = new Transport();
// One coordinator over the one transport. It owns no clock; see
// docs/architecture/SYNCHRONIZED_TEACHING_TIMELINE.md.
const teachingTimeline = new TeachingTimeline({ transport });

// The score views are followers of the existing timeline, not owners of one.
// The shell holds the reference so it can connect the transport and fretboard;
// the score state itself lives in the coordinator.
const scoreView = new ScoreViewCoordinator({
  loadJson,
  containers: {
    get tab() {
      return document.getElementById("tabView");
    },
    get notation() {
      return document.getElementById("notationView");
    },
  },
  onSeek: (canonicalEventId, tick) => scoreSeek(canonicalEventId, tick),
  onStatus: (status, reason) => renderScoreStatus(status, reason),
});

// Ticks in, seconds out, through DO-012's already-governed mapping seam.
const scoreSeek = createScoreSeekHandler({
  timeline: teachingTimeline,
  transport,
  secondsAtTick,
});

const selectFromFretboard = createFretboardSelectionHandler({ coordinator: scoreView });
const midiInput = new WebMidiInput();
$("btnFakeMidi").hidden = !midiInput.fakeMode;
const capture = new PerformanceCaptureController({
  midiInput,
  transport,
  api: new LocalPerformanceApi(),
});
const educationApi = new LocalEducationApi();
const practiceActions = new PracticeActionController({
  transport,
  onStatus: (message) => {
    $("resultsStatus").textContent = message;
    $("statusLine").textContent = message;
  },
  // DO-012: ISOLATE_PASSAGE now becomes a real loop. The Educational Engine
  // still chooses the passage; this only converts its authoritative focus
  // ticks into the seconds the shared transport speaks.
  resolveFocusRange: (startTick, endTick) => {
    if (!teachingTimeline.ready) return null;
    try {
      return resolveFocusRangeSeconds(teachingTimeline.anchors, startTick, endTick);
    } catch (_) {
      return null;
    }
  },
  targetRepetitions: () => state.practice?.policy.loop.target_repetitions ?? null,
});
const acceptGuidance = createGuidanceAcceptHandler({
  practiceActions,
  educationApi,
});
const params = new URLSearchParams(window.location.search);
if (params.get("devGolden") === "1") {
  $("btnGoldenDemo").hidden = false;
}
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

const mediaPlayer = new MediaPlayerController({
  root: $("teachingMedia"),
  onStatus: (message) => {
    $("statusLine").textContent = message;
  },
  // Synchronized media routes its controls through the shared transport rather
  // than becoming a second thing that owns play state, position, or rate.
  onSeekLesson: (seconds) => transport.seek(seconds),
  onTransportPlay: () => transport.play(),
  onTransportPause: () => transport.pause(),
  onTransportRate: (rate) => transport.setRate(rate),
  onBindingChange: (binding) => {
    mediaFollower.setBinding(binding);
    mediaFollower.setMode(
      mediaPlayer.synchronized ? "synchronized" : "detached",
    );
  },
});

const mediaFollower = new MediaSyncFollower({
  id: "media",
  getElement: () => mediaPlayer.element,
  onHealth: (health) => mediaPlayer.renderHealth(health),
});
teachingTimeline.addFollower(mediaFollower);
// One follower for both score views. Registering per renderer would put two
// subscriptions on one clock and give them two chances to disagree.
teachingTimeline.addFollower(scoreView.follower());

// The fretboard and Zone display are followers too: they read the timeline
// rather than deriving musical position for themselves.
teachingTimeline.addFollower({
  id: "zone",
  onPlayhead: () => renderActiveZones(),
  onClear: () => {
    $("zoneActive").textContent = "Zone: none";
  },
});

/**
 * Mirror synchronization state onto document.body as data- attributes.
 *
 * The window-level diagnostics object is only reachable from the page's own
 * JavaScript context; a headless driver evaluating in an isolated world sees
 * the DOM but not page globals. Mirroring here makes the same evidence
 * capturable without a bridge, at the cost of a few string writes per publish.
 *
 * Non-public: these attributes are a debug seam, not an API.
 */
teachingTimeline.addFollower({
  id: "diagnostics",
  onTimeline: (state) => {
    const data = document.body.dataset;
    data.masLessonId = state.lesson_id;
    data.masSequence = String(state.sequence);
    data.masPositionTick = String(state.position_tick);
    data.masPositionSeconds = state.position_seconds.toFixed(6);
    data.masPlaying = String(state.playing);
    data.masPlaybackRate = String(state.playback_rate);
    data.masLoopEnabled = String(state.loop_enabled);
    data.masLoopStartTick = state.loop_start_tick === null ? "" : String(state.loop_start_tick);
    data.masLoopEndTick = state.loop_end_tick === null ? "" : String(state.loop_end_tick);
    data.masRepetitionIndex = String(state.repetition_index);
  },
  onPlayhead: () => {
    const data = document.body.dataset;
    const health = mediaFollower.health();
    data.masSyncMode = mediaPlayer.syncMode;
    data.masSyncStatus = health ? health.status : "";
    data.masSyncDriftMs = health && health.drift_ms !== null ? health.drift_ms.toFixed(3) : "";
    data.masHardSeekCount = String(mediaFollower.hardSeekCount);
    data.masBindingId = mediaPlayer.activeBinding()?.binding_id ?? "";
    const activeZones = renderer.activeZones();
    data.masActiveZones = activeZones.map((zone) => zone.zoneId).join(" ");
    data.masTritoneAxes = [
      ...new Set(activeZones.map((zone) => zone.tritoneAxisId).filter(Boolean)),
    ].join(" ");
  },
  onClear: () => {
    for (const key of Object.keys(document.body.dataset)) {
      if (key.startsWith("mas")) delete document.body.dataset[key];
    }
  },
});

function renderActiveZones() {
  const zones = renderer.activeZones();
  const node = $("zoneActive");
  if (!zones.length) {
    node.textContent = "Zone: none";
    node.dataset.zoneIds = "";
    node.dataset.tritoneAxes = "";
    return;
  }
  // Simultaneous notes may occupy different Zones. Show the set; naming one
  // "dominant" Zone would invent a semantic the artifact does not assert.
  // Formatting lives in renderer.js so the rule is unit-testable.
  const zoneIds = zones.map((zone) => zone.zoneId);
  const axes = [...new Set(zones.map((zone) => zone.tritoneAxisId).filter(Boolean))];
  node.textContent = zoneReadoutText(zones);
  node.dataset.zoneIds = zoneIds.join(" ");
  node.dataset.tritoneAxes = axes.join(" ");
}

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

function setStage(stage) {
  state.stage = stage;
  document.querySelectorAll(".workflow-step").forEach((button) => {
    button.classList.toggle("active", button.dataset.stage === stage);
  });
  document.querySelectorAll("[data-stage-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.stagePanel !== stage;
  });
  // Status is always visible.
}

document.querySelectorAll(".workflow-step").forEach((button) => {
  button.addEventListener("click", () => setStage(button.dataset.stage));
});

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

/**
 * Mirror the transport's loop into the loop controls.
 *
 * The transport stays authoritative: this reads from it after something else
 * (an Educational action) has set a loop, so the inputs never disagree with
 * what is actually looping.
 */
function syncLoopControlsFromTransport() {
  const loop = transport.loop;
  if (!loop || !loop.enabled) {
    $("loopEnabled").checked = false;
    renderer.setLoop(null);
    $("loopRange").textContent = "Loop off";
    return;
  }
  $("loopEnabled").checked = true;
  $("loopStart").value = String(loop.startSeconds);
  $("loopEnd").value = String(loop.endSeconds);
  renderer.setLoop(loop);
  $("loopRange").textContent =
    `${loop.startSeconds.toFixed(2)}s–${loop.endSeconds.toFixed(2)}s`;
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
  capture.setLessonContext({
    assignmentId: playback.assignment_id,
    contentId: playback.content_id,
  });
  educationApi
    .beginLesson({
      assignment_id: playback.assignment_id,
      content_id: playback.content_id,
    })
    .catch((error) => {
      $("statusLine").textContent = error.message || "Education session failed";
    });
  state.lastEvaluation = null;
  renderResultsPanel($("resultsPanel"), null);
  renderer.setFocusRange(null);
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
  // Bind the coordinator to this lesson's Core-authored anchor table. Clearing
  // first is deliberate: stale anchors would mis-time the new lesson.
  const lessonIdentity = projection.content_id || playback.content_id;
  if (Array.isArray(payload.timeline_anchors) && payload.timeline_anchors.length) {
    teachingTimeline.setLesson({
      lessonId: lessonIdentity,
      anchors: payload.timeline_anchors,
    });
  } else {
    // No anchors means no derived ticks. The lesson still plays; only the
    // timeline followers stand down.
    teachingTimeline.clearLesson();
    $("statusLine").textContent = "Lesson has no timeline anchors; sync unavailable";
  }
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
  const lessonKey =
    demo?.demo_id || projection.content_id || payload.content_id || "";
  void mediaPlayer.loadForLesson(lessonKey);
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

function renderScoreStatus(status, reason) {
  const panel = document.getElementById("scorePanel");
  if (!panel) return;
  panel.dataset.scoreStatus = status;
  const notice = document.getElementById("scoreUnavailable");
  if (!notice) return;
  // A score that cannot be shown says so and stops there. The lesson, its
  // transport, media, Zone, and practice are all still usable.
  notice.hidden = status !== "unavailable";
  notice.textContent =
    status === "unavailable" ? `Score views unavailable (${reason || "unknown"})` : "";
}

async function loadScoreViews(demoId) {
  if (!demoId) return;
  // Never allowed to break lesson loading: the score is one surface among many.
  try {
    await scoreView.load(demoId);
  } catch (error) {
    renderScoreStatus("unavailable", error?.message || "load failed");
  }
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
  // The demo id comes from the payload the exporter stamped, not from a
  // parameter. It was a parameter first, and the lesson-change handler forgot to
  // pass it -- so switching lessons left the score views unloaded while every
  // other surface reloaded. Reading it from the applied payload means no call
  // site can omit it.
  await loadScoreViews(state.payload?.demo_id ?? null);
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
  // Active events are known only after the frame is rendered, so the playhead
  // is published from here rather than from a transport event.
  if (teachingTimeline.ready) {
    teachingTimeline.setActiveEventIds(renderer.activeEventIds());
    // Use the state that was actually emitted rather than deriving it again, so
    // what the DOM reports is the same snapshot the followers received.
    const { playhead } = teachingTimeline.publish("frame", now) || {};
    if (playhead) {
      document.body.dataset.playheadTick = String(playhead.position_tick);
      document.body.dataset.playheadEventIds = playhead.active_event_ids.join(" ");
    }
  }
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
  if (!evidence || !state.payload?.projection) return;
  try {
    const projection = state.payload.projection;
    const evaluation = await educationApi.evaluate({
      assignment_id: projection.assignment_id,
      content_id: projection.content_id,
      performance_session_id:
        evidence.raw_capture?.session_id ||
        evidence.performance_session_id ||
        `session-${Date.now()}`,
      current_rate: transport.playbackRate,
      timeline: projection.timeline,
      tempo_changes: projection.tempo_changes,
      expected_notes: projection.notes.map((note) => ({
        event_id: note.event_id,
        midi_note: note.midi_note,
        onset_tick: note.onset_tick,
        duration_ticks: note.duration_ticks,
        velocity: 80,
      })),
      observed_events: evidence.observed_events || [],
      repetition_count: Math.max(1, transport.snapshot().repetitionCount || 1),
      canonical_revision_id: scoreView.revisionId,
    });
    state.lastEvaluation = evaluation;
    renderResultsPanel($("resultsPanel"), evaluation);
    presentTeachingGuidance({
      coordinator: scoreView,
      renderer,
      projection: evaluation.guidance,
    });
    const data = document.body.dataset;
    data.masGuidedEventIds = (scoreView.guidedEventIds || []).join(",");
    data.masGuidanceAction = evaluation.guidance?.next_action?.action_type || "";
    data.masGuidanceDigest = evaluation.guidance?.guidance_digest || "";
    const focus = focusRangeFromEvaluation(evaluation.evaluation, projection);
    renderer.setFocusRange(focus);
    setStage("results");
    $("statusLine").textContent = `Evaluated · ${evaluation.evaluation.primary_next_action.action_type}`;
  } catch (error) {
    $("statusLine").textContent = error.message || "Evaluation failed";
  }
});
$("btnFakeMidi").addEventListener("click", () => midiInput.emitFakeScale());
$("btnApplyPrimary").addEventListener("click", async () => {
  const action =
    state.lastEvaluation?.guidance?.next_action ||
    state.lastEvaluation?.evaluation?.primary_next_action;
  if (!action) return;
  await acceptGuidance(action);
  syncLoopControlsFromTransport();
  if (action.action_type === "isolate_passage" && state.payload?.projection) {
    renderer.setFocusRange(
      focusRangeFromEvaluation(
        {
          summary: {
            focus_ranges: [
              {
                start_tick: action.focus_start_tick,
                end_tick: action.focus_end_tick,
                finding_ids: action.reason_finding_ids || [],
              },
            ],
          },
        },
        state.payload.projection,
      ),
    );
  }
  setStage("practice");
});
$("btnGoldenDemo").addEventListener("click", async () => {
  try {
    const result = await educationApi.goldenDemo();
    $("resultsStatus").textContent = `Golden demo: ${result.sequence.join(" → ")}`;
    $("statusLine").textContent = "Golden 3-attempt demo complete";
    setStage("results");
  } catch (error) {
    $("resultsStatus").textContent = error.message || "Golden demo failed";
  }
});
$("syncEnabled").addEventListener("change", (event) => {
  const requested = event.target.checked
    ? MediaSyncMode.SYNCHRONIZED
    : MediaSyncMode.DETACHED;
  const actual = mediaPlayer.setSyncMode(requested);
  // setSyncMode refuses to synchronize unbound media, so reflect what happened
  // rather than what was asked for.
  event.target.checked = actual === MediaSyncMode.SYNCHRONIZED;
  mediaFollower.setMode(actual);
  $("statusLine").textContent =
    actual === MediaSyncMode.SYNCHRONIZED
      ? "Media synchronized to the lesson"
      : "Media detached";
  teachingTimeline.publish("sync-mode");
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
  mediaPlayer.clear();
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
  educationApi,
  setStage,
  teachingTimeline,
  mediaPlayer,
  mediaFollower,
  practiceActions,
  syncLoopControlsFromTransport,
};

/**
 * Non-public diagnostics seam for browser smoke capture (DO-012).
 *
 * Named separately from __mvp2a so synchronization evidence has a stable home
 * as more teaching surfaces arrive. Not an API: shape may change with the
 * tranche that reads it.
 */
window.__masDiagnostics = {
  teachingTimeline: () => ({
    coordinator: teachingTimeline.diagnostics(),
    media: {
      syncMode: mediaPlayer.syncMode,
      binding: mediaPlayer.activeBinding(),
      health: mediaFollower.health(),
      hardSeekCount: mediaFollower.hardSeekCount,
    },
    zones: renderer.activeZones(),
  }),
  scoreViews: () =>
    buildScoreDiagnostics({
      coordinator: scoreView,
      limitations: NOTATION_LIMITATIONS,
      loopRange: state.practice?.policy?.loop ?? null,
      repetitionIndex: transport.repetitionCount,
    }),
  guidance: () => ({
    status: scoreView.diagnostics().guidanceStatus,
    guidanceDigest: scoreView.diagnostics().guidanceDigest,
    guidedEventIds: [...scoreView.guidedEventIds],
    guidanceAction: scoreView.diagnostics().guidanceAction,
    guidanceRange: scoreView.diagnostics().guidanceRange,
    guidanceError: scoreView.diagnostics().guidanceError,
    tabDigest: scoreView.tabDigest,
    notationDigest: scoreView.notationDigest,
    canonicalRevisionId: scoreView.revisionId,
  }),
};
// Fretboard selection reaches the score views as a canonical event id and
// nothing else. It marks a highlight channel; it does not decide what is active.
$("scrollCanvas").addEventListener("click", (event) => {
  selectFromFretboard(event.target);
});

bootstrap();
setStage("lesson");
requestAnimationFrame(tick);
