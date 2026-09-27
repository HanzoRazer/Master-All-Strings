/**
 * MAS-PERF-002R — the measurements taken inside the browser.
 *
 * Loaded by `browser_render_profile.html` and driven over the DevTools
 * protocol by `browser_render_profile.mjs`. It exposes one object,
 * `window.__masProfile`, whose methods each run one group of operations and
 * resolve to raw observations. It computes no summaries and reaches no
 * verdicts: the runner does both from the raw samples, so nothing reported
 * here can disagree with the numbers it came from.
 *
 * Clocks are never mixed. Each series is read from one clock:
 *
 *   js_ms            performance.now() around one synchronous product call
 *   style_layout_ms  performance.now() around a layout read issued right after
 *                    it, which forces style and layout to complete there
 *   frame timestamps the requestAnimationFrame callback argument
 *   long tasks       PerformanceObserver entries, kept whole
 *
 * Every sample runs in its own animation frame, so one sample's invalidations
 * are settled before the next begins and no sample inherits another's layout.
 *
 * Test-only. It imports the product modules and changes none of them.
 */

import { FretboardRenderer } from "../../renderer.js";
import {
  applyActiveEventIds as applyNotationActive,
  renderNotationSvg,
} from "../../notation-view.js";
import { applyActiveEventIds as applyTabActive, renderTabSvg } from "../../tab-view.js";
import {
  WORKLOAD_VERSION,
  buildBenchmarkLanes,
  buildBenchmarkNotationPayload,
  buildBenchmarkProjection,
  buildBenchmarkTabPayload,
  buildBenchmarkWorkload,
  workloadDigest,
} from "./benchmark-fixtures.js";

export const HARNESS_VERSION = "1.0.0";
export const WARMUPS = 5;
export const SAMPLES = 20;

/** The selector both views' `applyActiveEventIds()` issue. */
const EVENT_SELECTOR = "[data-canonical-event-id]";

const $ = (id) => document.getElementById(id);
const nextFrame = () => new Promise((resolve) => requestAnimationFrame(resolve));
const settle = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// --- long tasks --------------------------------------------------------------

const longTasks = [];
let longTaskSupported = false;
const longTaskObserver =
  typeof PerformanceObserver === "function" ? new PerformanceObserver((list) => {
    longTasks.push(...list.getEntries());
  }) : null;
try {
  longTaskObserver?.observe({ type: "longtask", buffered: true });
  longTaskSupported = PerformanceObserver.supportedEntryTypes?.includes("longtask") ?? false;
} catch {
  longTaskSupported = false;
}

function longTaskRecord(entry) {
  return {
    name: entry.name ?? null,
    entry_type: entry.entryType ?? null,
    start_time_ms: typeof entry.startTime === "number" ? entry.startTime : null,
    duration_ms: typeof entry.duration === "number" ? entry.duration : null,
    attribution: Array.isArray(entry.attribution)
      ? entry.attribution.map((item) => ({
          name: item.name ?? null,
          entry_type: item.entryType ?? null,
          container_type: item.containerType ?? null,
          container_name: item.containerName ?? null,
          container_id: item.containerId ?? null,
          container_src: item.containerSrc ?? null,
        }))
      : null,
  };
}

/** Long tasks that overlap [from, to], in the page's own time origin. */
async function longTasksBetween(from, to) {
  // Entries are delivered after the task ends; give the observer a moment.
  await nextFrame();
  await settle(100);
  longTasks.push(...(longTaskObserver?.takeRecords() ?? []));
  return longTasks
    .filter((entry) => entry.startTime + entry.duration >= from && entry.startTime <= to)
    .map(longTaskRecord);
}

// --- shared pieces -----------------------------------------------------------

function forceStyleLayout(element) {
  const started = performance.now();
  element.getBoundingClientRect();
  return performance.now() - started;
}

/**
 * Run `step` once per animation frame: WARMUPS discarded, SAMPLES kept.
 * `step(index)` returns an object of named durations for that sample.
 */
async function sampled(step) {
  const kept = [];
  for (let index = 0; index < WARMUPS + SAMPLES; index += 1) {
    await nextFrame();
    const sample = step(index);
    if (index >= WARMUPS) kept.push(sample);
  }
  const series = {};
  for (const sample of kept) {
    for (const [name, value] of Object.entries(sample)) {
      (series[name] ??= []).push(value);
    }
  }
  return { warmups_discarded: WARMUPS, series };
}

function workloadIdentity(eventCount) {
  const workload = buildBenchmarkWorkload(eventCount);
  return {
    workload_version: WORKLOAD_VERSION,
    event_count: eventCount,
    digest: workloadDigest(workload),
  };
}

function pageEnvironment() {
  const viewport = $("scrollViewport");
  return {
    harness_version: HARNESS_VERSION,
    user_agent: navigator.userAgent,
    viewport: { width: window.innerWidth, height: window.innerHeight },
    device_pixel_ratio: window.devicePixelRatio,
    cross_origin_isolated: window.crossOriginIsolated === true,
    visibility_state: document.visibilityState,
    has_focus: document.hasFocus(),
    time_origin_ms: performance.timeOrigin,
    longtask_supported: longTaskSupported,
    fretboard_viewport_width_px: viewport?.clientWidth ?? null,
  };
}

// --- M5: replacing the rendered score tree -----------------------------------

async function measureMount(view, container, render) {
  const operation = await sampled(() => {
    const started = performance.now();
    const svg = render();
    const built = performance.now();
    // What mountTabView()/mountNotationView() do with the string.
    container.innerHTML = svg;
    const replaced = performance.now();
    return {
      string_build_ms: built - started,
      innerhtml_replace_ms: replaced - built,
      style_layout_ms: forceStyleLayout(container),
    };
  });
  return {
    ...operation,
    view,
    svg_characters: render().length,
    elements_in_tree: container.getElementsByTagName("*").length,
    event_groups_in_tree: container.querySelectorAll(EVENT_SELECTOR).length,
  };
}

// --- M4: active-state updates on a mounted tree ------------------------------

async function measureActive(view, root, apply, ids) {
  // A playing lesson moves its active window along: eight ids, advancing one
  // event per sample, the same "shifted" pattern MAS-PERF-001 used.
  const span = Math.max(1, ids.length - 8);
  const windowAt = (index) => ids.slice(index % span, (index % span) + 8);
  const update = await sampled((index) => {
    const active = windowAt(index);
    const started = performance.now();
    apply(root, active);
    const ended = performance.now();
    return { active_update_ms: ended - started, style_layout_ms: forceStyleLayout(root) };
  });
  // The selector on its own, in its own frames: never derived from the above.
  const selector = await sampled(() => {
    const started = performance.now();
    const matched = root.querySelectorAll(EVENT_SELECTOR).length;
    const ended = performance.now();
    return { selector_ms: ended - started, matched };
  });
  return {
    view,
    selector: EVENT_SELECTOR,
    active_ids_per_update: 8,
    active_update: update,
    selector_only: selector,
  };
}

async function scoreGroup(eventCount) {
  const tabPayload = buildBenchmarkTabPayload({ eventCount });
  const notationPayload = buildBenchmarkNotationPayload({ eventCount });
  const lanes = buildBenchmarkLanes();
  const tabContainer = $("tabView");
  const notationContainer = $("notationView");

  const tabMount = await measureMount("tab", tabContainer, () =>
    renderTabSvg(tabPayload, { lanes }),
  );
  const notationMount = await measureMount("notation", notationContainer, () =>
    renderNotationSvg(notationPayload, {}),
  );

  const ids = tabPayload.events.map((event) => event.canonical_event_id);
  const tabActive = await measureActive("tab", tabContainer.firstElementChild, applyTabActive, ids);
  const notationActive = await measureActive(
    "notation",
    notationContainer.firstElementChild,
    applyNotationActive,
    ids,
  );

  return {
    group: "score",
    workload: workloadIdentity(eventCount),
    environment: pageEnvironment(),
    operations: {
      m5_tab_mount: tabMount,
      m5_notation_mount: notationMount,
      m4_tab_active: tabActive,
      m4_notation_active: notationActive,
    },
  };
}

// --- M2: the fretboard frame -------------------------------------------------

function loadRenderer(eventCount) {
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
  renderer.load(buildBenchmarkProjection({ eventCount }));
  return renderer;
}

async function measureRenderFrame(renderer) {
  const total = renderer.projection.timeline.total_seconds || 1;
  // The three playhead positions MAS-PERF-001 cycled through.
  const positions = [0.05, 0.5, 0.95].map((fraction) => total * fraction);
  const canvas = $("scrollCanvas");
  return sampled((index) => {
    const started = performance.now();
    renderer.renderFrame(positions[index % positions.length]);
    const ended = performance.now();
    return { js_ms: ended - started, style_layout_ms: forceStyleLayout(canvas) };
  });
}

/**
 * The app's loop, reduced to the renderer: one renderFrame() per animation
 * frame, the playhead advancing in real time. Nothing is forced; the browser
 * styles, lays out and paints on its own schedule, which is the point.
 *
 * Returns WARMUPS + SAMPLES + 1 timestamps: the first WARMUPS frames are
 * discarded, and SAMPLES deltas are taken over the SAMPLES + 1 that follow.
 */
async function frameWindow(renderer, markPrefix = null) {
  const total = renderer.projection.timeline.total_seconds || 1;
  const startPosition = total * 0.05;
  if (markPrefix) performance.mark(`${markPrefix}-start`);
  const observedFrom = performance.now();
  const timestamps = [];
  const js = [];
  const frames = WARMUPS + SAMPLES + 1;
  await new Promise((resolve) => {
    let first = null;
    const tick = (timestamp) => {
      first ??= timestamp;
      const started = performance.now();
      renderer.renderFrame(startPosition + (timestamp - first) / 1000);
      js.push(performance.now() - started);
      timestamps.push(timestamp);
      if (timestamps.length < frames) requestAnimationFrame(tick);
      else resolve();
    };
    requestAnimationFrame(tick);
  });
  const observedTo = performance.now();
  // One more frame so the last sampled frame's rendering lands inside the mark.
  if (markPrefix) {
    await nextFrame();
    performance.mark(`${markPrefix}-end`);
  }
  return {
    warmups_discarded: WARMUPS,
    frame_timestamps_ms: timestamps.slice(WARMUPS),
    discarded_timestamps_ms: timestamps.slice(0, WARMUPS),
    // js_ms[i] is the renderFrame() call in the frame stamped
    // frame_timestamps_ms[i]; the last retained timestamp closes the window.
    js_ms: js.slice(WARMUPS, WARMUPS + SAMPLES),
    observed_from_ms: observedFrom,
    observed_to_ms: observedTo,
    long_tasks: await longTasksBetween(observedFrom, observedTo),
  };
}

async function fretboardGroup(eventCount, { windowOnly = false } = {}) {
  const renderer = loadRenderer(eventCount);
  await nextFrame();
  const operations = {};
  if (!windowOnly) operations.m2_render_frame = await measureRenderFrame(renderer);
  operations.m2_frame_window = await frameWindow(renderer);
  return {
    group: windowOnly ? "fretboard_window" : "fretboard",
    workload: workloadIdentity(eventCount),
    environment: pageEnvironment(),
    notes_rendered: renderer.notes.length,
    operations,
  };
}

// --- the traced pass ---------------------------------------------------------

/**
 * One frame window and one mount of each view, bracketed by user-timing marks
 * so the driver can find them in the trace. Run on its own page load, with
 * tracing on, and never mixed into the sampled numbers above.
 */
async function tracedGroup(eventCount) {
  const renderer = loadRenderer(eventCount);
  await nextFrame();
  const window_ = await frameWindow(renderer, "mas-frame-window");

  const tabPayload = buildBenchmarkTabPayload({ eventCount });
  const notationPayload = buildBenchmarkNotationPayload({ eventCount });
  const lanes = buildBenchmarkLanes();
  await nextFrame();
  performance.mark("mas-mount-start");
  $("tabView").innerHTML = renderTabSvg(tabPayload, { lanes });
  $("notationView").innerHTML = renderNotationSvg(notationPayload, {});
  performance.mark("mas-mount-end");
  // Let the frame that paints the new trees happen inside the trace.
  await nextFrame();
  await nextFrame();
  performance.mark("mas-mount-painted");
  return {
    group: "traced",
    workload: workloadIdentity(eventCount),
    frame_timestamps_ms: window_.frame_timestamps_ms,
  };
}

window.__masProfile = {
  harnessVersion: HARNESS_VERSION,
  environment: pageEnvironment,
  digest: (eventCount) => workloadIdentity(eventCount),
  scoreGroup,
  fretboardGroup,
  tracedGroup,
};
window.__masProfileReady = true;
