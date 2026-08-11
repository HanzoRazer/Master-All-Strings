import { FretboardRenderer } from "./renderer.js";
import { PresentationTransport } from "./transport.js";

const $ = (id) => document.getElementById(id);

const state = {
  payload: null,
  demos: [],
  instruments: [],
};

const transport = new PresentationTransport();
const renderer = new FretboardRenderer({
  laneLabels: $("laneLabels"),
  scrollViewport: $("scrollViewport"),
  scrollCanvas: $("scrollCanvas"),
  playLine: $("playLine"),
  gutterNotes: $("gutterNotes"),
  neckMap: $("neckMap"),
  instrumentTitle: $("instrumentTitle"),
});

function showError(message) {
  $("errorOverlay").classList.remove("hidden");
  $("errorMessage").textContent = message;
  $("statusLine").textContent = message;
}

function clearError() {
  $("errorOverlay").classList.add("hidden");
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
    ...payload.warnings.map((warning) => {
      const li = document.createElement("li");
      li.textContent = warning;
      return li;
    }),
  );
}

function applyProjectionPayload(payload) {
  clearError();
  state.payload = payload;
  const projection = payload.projection;
  if (!projection || projection.projection_version !== "1.0.0") {
    showError("Unsupported projection version");
    return;
  }
  transport.restart();
  transport.setDuration(projection.timeline.total_seconds);
  renderer.load(projection);
  setLessonInfo(projection, payload);
  $("seek").value = "0";
  $("statusLine").textContent = "Ready";
  const demo = state.demos.find((item) => item.title === projection.title);
  $("lessonDescription").textContent = demo?.description || projection.description || "";
  $("knownLimitations").textContent = (demo?.known_limitations || []).length
    ? `Known limitations: ${demo.known_limitations.join(", ")}`
    : "";
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load ${path}`);
  }
  return response.json();
}

async function bootstrap() {
  try {
    const [payload, demos, instruments] = await Promise.all([
      loadJson("./projection.json"),
      loadJson("./demos.json").catch(() => ({ demos: [] })),
      loadJson("./instruments.json").catch(() => []),
    ]);
    state.demos = demos.demos || [];
    state.instruments = instruments;
    const demoSelect = $("demoSelect");
    demoSelect.replaceChildren(
      ...state.demos.map((demo) => {
        const option = document.createElement("option");
        option.value = demo.demo_id;
        option.textContent = demo.title;
        return option;
      }),
    );
    const instrumentSelect = $("instrumentSelect");
    instrumentSelect.replaceChildren(
      ...state.instruments.map((item) => {
        const option = document.createElement("option");
        option.value = item.instrument_id;
        option.textContent = item.experimental
          ? `${item.display_name} (experimental)`
          : item.display_name;
        return option;
      }),
    );
    instrumentSelect.value = payload.instrument_id || "guitar-standard-6";
    applyProjectionPayload(payload);
  } catch (error) {
    showError(error.message || "Unable to load lesson");
  }
}

function tick(now) {
  const seconds = transport.positionSeconds(now);
  $("clockReadout").textContent = `${seconds.toFixed(2)}s · ${transport.playbackRate.toFixed(2)}×`;
  if (transport.durationSeconds > 0) {
    $("seek").value = String(Math.round((seconds / transport.durationSeconds) * 1000));
  }
  renderer.renderFrame(seconds);
  requestAnimationFrame(tick);
}

$("btnPlay").addEventListener("click", () => {
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
  const ratio = Number(event.target.value) / 1000;
  transport.seek(ratio * (transport.durationSeconds || 0));
});
document.querySelectorAll(".rates button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".rates button").forEach((node) => node.classList.remove("active"));
    button.classList.add("active");
    transport.setRate(button.dataset.rate);
  });
});

window.addEventListener("resize", () => {
  renderer.resize();
});

$("demoSelect").addEventListener("change", async (event) => {
  const demoId = event.target.value;
  transport.pause();
  try {
    const payload = await loadJson(`./projections/${demoId}.json`);
    applyProjectionPayload(payload);
    $("statusLine").textContent = `Loaded ${demoId}`;
  } catch (error) {
    showError(
      error.message ||
        "Unable to load lesson. Re-run scripts/run_mvp1.py --open to refresh demos.",
    );
  }
});

bootstrap();
requestAnimationFrame(tick);
