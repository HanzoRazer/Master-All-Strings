import { FretboardRenderer } from "./renderer.js";
import { PresentationTransport } from "./transport.js";

const $ = (id) => document.getElementById(id);

const state = {
  payload: null,
  demos: [],
  demosById: new Map(),
  instruments: [],
};

const transport = new PresentationTransport();
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
    ...(payload.warnings || []).map((warning) => {
      const li = document.createElement("li");
      li.textContent = warning;
      return li;
    }),
  );
}

/**
 * Resolve the catalog entry for a payload using stable identity only.
 * Titles are display text and must never be used to correlate.
 */
function demoForPayload(payload) {
  const projection = payload.projection;
  return (
    state.demosById.get(payload.demo_id) ||
    state.demosById.get(projection?.content_id) ||
    null
  );
}

function applyProjectionPayload(payload) {
  const projection = payload?.projection;
  if (!projection || projection.projection_version !== "1.0.0") {
    showError("Unsupported projection version");
    return;
  }
  clearError();
  state.payload = payload;
  transport.restart();
  transport.setDuration(projection.timeline.total_seconds);
  renderer.load(projection);
  setLessonInfo(projection, payload);
  $("seek").value = "0";
  $("statusLine").textContent = "Ready";

  const demo = demoForPayload(payload);
  // Keep the sidebar controls in sync with what is actually rendered.
  if (demo) $("demoSelect").value = demo.demo_id;
  $("instrumentSelect").value = payload.instrument_id || projection.instrument.instrument_id;
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

/**
 * Load an ad-hoc CLI export when one is named via ``?projection=<relative path>``
 * (scripts/run_mvp1.py prints that URL), otherwise a checked-in demo fixture.
 * Probing for the runtime file unconditionally would log a 404 on every clean
 * load, so the caller states the intent instead.
 */
async function loadInitialPayload() {
  const requested = new URLSearchParams(window.location.search).get("projection");
  if (requested) {
    // Same-origin relative paths only: no scheme, no root, no traversal.
    const safe = /^[\w-]+(\/[\w-]+)*\.json$/.test(requested);
    if (!safe) {
      throw new Error(`Refusing to load projection path: ${requested}`);
    }
    return loadJson(`./${requested}`);
  }
  if (!state.demos.length) {
    throw new Error("No lesson available. Run scripts/run_mvp1.py to export one.");
  }
  return loadJson(`./projections/${state.demos[0].demo_id}.json`);
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

    applyProjectionPayload(await loadInitialPayload());
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

// Resize triggers a full static rebuild, so coalesce bursts into one frame.
let resizePending = false;
window.addEventListener("resize", () => {
  if (resizePending) return;
  resizePending = true;
  requestAnimationFrame(() => {
    resizePending = false;
    renderer.resize();
  });
});

$("demoSelect").addEventListener("change", async (event) => {
  const demoId = event.target.value;
  transport.pause();
  try {
    applyProjectionPayload(await loadJson(`./projections/${demoId}.json`));
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
