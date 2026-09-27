/**
 * MAS-PERF-002R — drive a headed Chrome over the DevTools protocol.
 *
 * `scripts/performance/run_mas_browser_profile.py` serves the page, launches
 * Chrome and runs this with the debugging port. This connects, loads
 * `browser_render_profile.html` once per group so no group inherits another's
 * heap or DOM, calls the page's `window.__masProfile` methods, and writes the
 * raw observations as JSON on stdout. It summarizes nothing and classifies
 * nothing; the runner does both.
 *
 * Three things only the protocol can supply are collected here:
 *
 *   - the browser's identity (`Browser.getVersion`);
 *   - memory: JS heap and DOM node counts from `Performance.getMetrics`, each
 *     read after a forced collection (`HeapProfiler.collectGarbage`);
 *   - a DevTools trace, on a page load of its own, decoded from JSON and
 *     reduced to per-event totals inside the page's user-timing marks.
 *
 * No dependency: Node's built-in WebSocket speaks the protocol. Test-only.
 *
 *     node browser_render_profile.mjs --port <devtools port> --base-url <url>
 */

import {
  WORKLOAD_SIZES,
  WORKLOAD_VERSION,
  buildBenchmarkWorkload,
  workloadDigest,
} from "./benchmark-fixtures.js";

export const DRIVER_VERSION = "1.0.0";
const WARMUPS = 5;
const SAMPLES = 20;
const PAGE_PATH = "tests/performance/browser_render_profile.html";

const TRACE_CATEGORIES = [
  "devtools.timeline",
  "disabled-by-default-devtools.timeline",
  "disabled-by-default-devtools.timeline.frame",
  "blink.user_timing",
  "toplevel",
];

// Trace events reported by name. Anything else is counted, not itemized.
const TRACE_EVENTS_OF_INTEREST = [
  "RunTask",
  "FireAnimationFrame",
  "FunctionCall",
  "UpdateLayoutTree",
  "Layout",
  "PrePaint",
  "Paint",
  "Layerize",
  "Commit",
  "RasterTask",
  "CompositeLayers",
  "UpdateLayer",
  "ParseHTML",
  "MinorGC",
  "MajorGC",
];

function argument(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

// --- a minimal protocol client -----------------------------------------------

class Cdp {
  static async connect(url) {
    const socket = new WebSocket(url);
    await new Promise((resolve, reject) => {
      socket.addEventListener("open", resolve, { once: true });
      socket.addEventListener("error", reject, { once: true });
    });
    return new Cdp(socket);
  }

  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Set();
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(`${message.error.message} (${message.error.code})`));
        else resolve(message.result);
        return;
      }
      for (const listener of this.listeners) listener(message);
    });
  }

  send(method, params = {}, sessionId = undefined) {
    const id = this.nextId++;
    const message = { id, method, params };
    if (sessionId) message.sessionId = sessionId;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify(message));
    });
  }

  waitFor(predicate, timeoutMs = 60000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.listeners.delete(listener);
        reject(new Error("timed out waiting for a protocol event"));
      }, timeoutMs);
      const listener = (message) => {
        if (!predicate(message)) return;
        clearTimeout(timer);
        this.listeners.delete(listener);
        resolve(message);
      };
      this.listeners.add(listener);
    });
  }

  close() {
    this.socket.close();
  }
}

class Page {
  constructor(cdp, sessionId) {
    this.cdp = cdp;
    this.sessionId = sessionId;
    this.errors = [];
    cdp.listeners.add((message) => {
      if (message.sessionId !== sessionId) return;
      if (message.method === "Runtime.exceptionThrown") {
        this.errors.push(message.params.exceptionDetails?.exception?.description
          ?? message.params.exceptionDetails?.text);
      }
    });
  }

  send(method, params) {
    return this.cdp.send(method, params, this.sessionId);
  }

  async navigate(url) {
    const loaded = this.cdp.waitFor(
      (message) => message.sessionId === this.sessionId && message.method === "Page.loadEventFired",
    );
    await this.send("Page.navigate", { url });
    await loaded;
    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) {
      if (await this.evaluate("window.__masProfileReady === true")) return;
      if (this.errors.length) throw new Error(`profile page failed: ${this.errors.join("; ")}`);
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error("profile page never became ready");
  }

  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true,
    });
    if (result.exceptionDetails) {
      throw new Error(
        result.exceptionDetails.exception?.description ?? result.exceptionDetails.text,
      );
    }
    return result.result.value;
  }

  /** JS heap and DOM counts after a forced collection. */
  async memory() {
    await this.send("HeapProfiler.collectGarbage");
    const { metrics } = await this.send("Performance.getMetrics");
    const byName = Object.fromEntries(metrics.map((metric) => [metric.name, metric.value]));
    return {
      method: "HeapProfiler.collectGarbage, then Performance.getMetrics",
      js_heap_used_bytes: byName.JSHeapUsedSize ?? null,
      js_heap_total_bytes: byName.JSHeapTotalSize ?? null,
      dom_nodes: byName.Nodes ?? null,
      layout_objects: byName.LayoutObjects ?? null,
    };
  }
}

// --- trace reduction ---------------------------------------------------------

/** Total length of a set of [from, to] intervals, overlaps counted once. */
function unionMs(intervals) {
  const sorted = [...intervals].sort((a, b) => a[0] - b[0]);
  let total = 0;
  let current = null;
  for (const [from, to] of sorted) {
    if (!current || from > current[1]) {
      if (current) total += current[1] - current[0];
      current = [from, to];
    } else {
      current[1] = Math.max(current[1], to);
    }
  }
  if (current) total += current[1] - current[0];
  return total / 1000;
}

// Rendering-pipeline work reported per frame. Main-thread stages, then raster.
const PER_FRAME_MAIN = ["UpdateLayoutTree", "Layout", "PrePaint", "Paint", "Layerize", "Commit"];
const RASTER_THREAD_PREFIX = "ThreadPoolForegroundWorker";

/**
 * Totals per event name inside [start, end] on the page's renderer process.
 *
 * The marks tell us the renderer main thread (the thread they were recorded
 * on) and the interval. Complete events ("X") are attributed to that interval
 * only if they lie wholly inside it. Events that straddle a mark are counted
 * separately and never apportioned.
 *
 * Totals are the union of each name's intervals, so an event nested inside
 * another of the same name (Paint inside Paint) is not counted twice.
 *
 * With `perFrame`, the interval is also cut at every FireAnimationFrame on the
 * main thread -- the page's own animation-frame callbacks -- and each stage's
 * union is reported per frame. The first `perFrame.discard` frames are the
 * page's warm-ups and are dropped, as they are from the sampled series.
 */
function reduceTrace(events, startMark, endMark, perFrame = null) {
  const mark = (name) =>
    events.find((event) => event.name === name && event.cat?.includes("blink.user_timing"));
  const start = mark(startMark);
  const end = mark(endMark);
  if (!start || !end) {
    return { status: "UNAVAILABLE", reason: `marks ${startMark}/${endMark} not found in trace` };
  }
  const pid = start.pid;
  const mainTid = start.tid;
  const threadNames = {};
  for (const event of events) {
    if (event.ph === "M" && event.name === "thread_name" && event.pid === pid) {
      threadNames[event.tid] = event.args?.name ?? null;
    }
  }
  const roleOf = (tid) => (tid === mainTid ? "main" : (threadNames[tid] ?? `tid:${tid}`));
  const inside = [];
  let straddling = 0;
  for (const event of events) {
    if (event.pid !== pid || event.ph !== "X" || typeof event.dur !== "number") continue;
    const from = event.ts;
    const to = event.ts + event.dur;
    if (to < start.ts || from > end.ts) continue;
    if (from < start.ts || to > end.ts) {
      straddling += 1;
      continue;
    }
    inside.push({ role: roleOf(event.tid), name: event.name, from, to });
  }

  const grouped = {};
  for (const event of inside) {
    const name = TRACE_EVENTS_OF_INTEREST.includes(event.name) ? event.name : null;
    if (!name) continue;
    ((grouped[event.role] ??= {})[name] ??= []).push(event);
  }
  const byThread = {};
  for (const [role, names] of Object.entries(grouped)) {
    byThread[role] = {};
    for (const [name, list] of Object.entries(names)) {
      byThread[role][name] = {
        count: list.length,
        union_ms: unionMs(list.map((event) => [event.from, event.to])),
        max_ms: Math.max(...list.map((event) => (event.to - event.from) / 1000)),
      };
    }
  }

  const reduced = {
    status: "DECODED",
    format: "Chrome trace events (JSON), Tracing.dataCollected",
    clock: "trace timestamps (microseconds), reported in ms",
    interval_ms: (end.ts - start.ts) / 1000,
    main_thread: threadNames[mainTid] ?? `tid:${mainTid}`,
    events_straddling_interval: straddling,
    totals_by_thread: byThread,
  };

  if (perFrame) {
    const callbacks = inside
      .filter((event) => event.role === "main" && event.name === "FireAnimationFrame")
      .map((event) => event.from)
      .sort((a, b) => a - b);
    // A frame is callback i to callback i+1; the last runs to the end mark.
    const bounds = [...callbacks, end.ts];
    const frames = [];
    const last = Math.min(bounds.length - 1, perFrame.discard + perFrame.keep);
    for (let index = perFrame.discard; index < last; index += 1) {
      const [from, to] = [bounds[index], bounds[index + 1]];
      const within = inside.filter((event) => event.from >= from && event.from < to);
      const stages = {};
      for (const stage of PER_FRAME_MAIN) {
        stages[stage] = unionMs(
          within
            .filter((event) => event.role === "main" && event.name === stage)
            .map((event) => [event.from, event.to]),
        );
      }
      stages.RasterTask_started = unionMs(
        within
          .filter(
            (event) => event.role.startsWith(RASTER_THREAD_PREFIX) && event.name === "RasterTask",
          )
          .map((event) => [event.from, event.to]),
      );
      frames.push({ frame_start_ms: from / 1000, frame_span_ms: (to - from) / 1000, stages_ms: stages });
    }
    reduced.per_frame = {
      delimited_by: "FireAnimationFrame on the renderer main thread",
      warmup_frames_discarded: perFrame.discard,
      frames_kept: "the SAMPLES + 1 frames whose timestamps the page retained",
      frames_found: callbacks.length,
      attribution:
        "An event belongs to the frame in which it starts. Raster runs on worker threads " +
        "and is attributed by start time, so it may be finishing an earlier frame's work.",
      frames,
    };
  }
  return reduced;
}

async function traced(cdp, page, url, eventCount) {
  const events = [];
  const collect = (message) => {
    if (message.method === "Tracing.dataCollected") events.push(...message.params.value);
  };
  cdp.listeners.add(collect);
  try {
    await page.navigate(url);
    await cdp.send("Tracing.start", {
      categories: TRACE_CATEGORIES.join(","),
      transferMode: "ReportEvents",
    });
    const run = await page.evaluate(`window.__masProfile.tracedGroup(${eventCount})`);
    const complete = cdp.waitFor((message) => message.method === "Tracing.tracingComplete", 120000);
    await cdp.send("Tracing.end");
    await complete;
    return {
      workload: run.workload,
      categories: TRACE_CATEGORIES,
      events_collected: events.length,
      frame_window: reduceTrace(events, "mas-frame-window-start", "mas-frame-window-end", {
        discard: WARMUPS,
        keep: SAMPLES + 1,
      }),
      mount: reduceTrace(events, "mas-mount-start", "mas-mount-end"),
      mount_through_next_frames: reduceTrace(events, "mas-mount-start", "mas-mount-painted"),
    };
  } finally {
    cdp.listeners.delete(collect);
  }
}

// --- the run -----------------------------------------------------------------

async function openPage(cdp) {
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  const page = new Page(cdp, sessionId);
  await page.send("Page.enable");
  await page.send("Runtime.enable");
  await page.send("Performance.enable");
  await page.send("Page.bringToFront");
  return { page, targetId };
}

async function main() {
  const port = argument("--port");
  const baseUrl = argument("--base-url");
  if (!port || !baseUrl) throw new Error("usage: --port <devtools port> --base-url <url>");
  const sizes = (argument("--sizes") ?? WORKLOAD_SIZES.join(",")).split(",").map(Number);

  const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
  const cdp = await Cdp.connect(version.webSocketDebuggerUrl);
  const browser = await cdp.send("Browser.getVersion");
  const { page, targetId } = await openPage(cdp);
  const url = new URL(PAGE_PATH, baseUrl).href;

  const result = {
    driver_version: DRIVER_VERSION,
    browser: {
      product: browser.product,
      revision: browser.revision,
      user_agent: browser.userAgent,
      js_version: browser.jsVersion,
      protocol_version: browser.protocolVersion,
    },
    page_url: url,
    node_workloads: Object.fromEntries(
      sizes.map((size) => [
        String(size),
        { workload_version: WORKLOAD_VERSION, digest: workloadDigest(buildBenchmarkWorkload(size)) },
      ]),
    ),
    runs: {},
    frame_window_repeat: {},
    traces: {},
  };

  for (const size of sizes) {
    process.stderr.write(`size ${size}: score views\n`);
    await page.navigate(url);
    const scoreBefore = await page.memory();
    const score = await page.evaluate(`window.__masProfile.scoreGroup(${size})`);
    const scoreAfter = await page.memory();

    process.stderr.write(`size ${size}: fretboard\n`);
    await page.navigate(url);
    const fretBefore = await page.memory();
    const fretboard = await page.evaluate(`window.__masProfile.fretboardGroup(${size})`);
    const fretAfter = await page.memory();

    result.runs[String(size)] = {
      score,
      fretboard,
      memory: {
        score_views: { before: scoreBefore, after_mount_and_updates: scoreAfter },
        fretboard: { before: fretBefore, after_load_and_frames: fretAfter },
      },
    };
  }

  // The 10,000-event frame window again, on a fresh page load.
  const largest = Math.max(...sizes);
  process.stderr.write(`size ${largest}: frame window, second run\n`);
  await page.navigate(url);
  result.frame_window_repeat[String(largest)] = await page.evaluate(
    `window.__masProfile.fretboardGroup(${largest}, { windowOnly: true })`,
  );

  for (const size of sizes) {
    process.stderr.write(`size ${size}: traced pass\n`);
    try {
      result.traces[String(size)] = await traced(cdp, page, url, size);
    } catch (error) {
      result.traces[String(size)] = { status: "UNAVAILABLE", reason: String(error?.message ?? error) };
    }
  }

  result.page_errors = page.errors;
  await cdp.send("Target.closeTarget", { targetId }).catch(() => {});
  cdp.close();
  process.stdout.write(JSON.stringify(result));
}

main().catch((error) => {
  process.stderr.write(`browser_render_profile: ${error?.stack ?? error}\n`);
  process.exit(1);
});
