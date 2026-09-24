/**
 * Deterministic benchmark workloads for the Node side of MAS-PERF-001.
 *
 * The grammar lives in `scripts/performance/generate_benchmark_lesson.py`;
 * this mirrors it. A test asserts both produce the same digest for the same
 * event count, so the Python and Node halves of this tranche are measuring one
 * lesson rather than two that merely share a size.
 *
 * Integer milliseconds and integer MIDI notes throughout: floats would let the
 * two implementations disagree in the last bit and turn determinism into a
 * tolerance argument.
 *
 * Benchmark-side only. Nothing here is imported by product code, and the
 * element factory below exists so a benchmark can count style writes without a
 * counter being added to the renderer.
 */

import { createHash } from "node:crypto";

export const WORKLOAD_VERSION = "1.0.0";
export const WORKLOAD_SIZES = [100, 1000, 10000];

const STRINGS = 6;
const STEP_MS = 250;
const MIN_DURATION_MS = 200;

export function buildBenchmarkEvents(count) {
  const events = [];
  for (let index = 0; index < count; index += 1) {
    const stringIndex = index % STRINGS;
    const fret = (index * 7) % 13;
    const onsetMs = index * STEP_MS;
    const durationMs = MIN_DURATION_MS + (index % 4) * 50;
    events.push({
      event_id: `bench-ev-${String(index).padStart(5, "0")}`,
      canonical_event_id: `bench-canonical-${String(index).padStart(5, "0")}`,
      onset_ms: onsetMs,
      release_ms: onsetMs + durationMs,
      midi_note: 40 + stringIndex * 5 + fret,
      string_index: stringIndex,
      fret,
      velocity: 64 + (index % 8) * 4,
    });
  }
  return events;
}

export function buildBenchmarkWorkload(count) {
  const events = buildBenchmarkEvents(count);
  return {
    workload_version: WORKLOAD_VERSION,
    event_count: count,
    total_ms: events.length ? events[events.length - 1].release_ms : 0,
    strings: STRINGS,
    events,
  };
}

/** Canonical JSON with sorted keys, matching Python's `sort_keys=True`. */
function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function workloadDigest(workload) {
  return `sha256:${createHash("sha256").update(canonical(workload), "utf8").digest("hex")}`;
}

// --- shapes the runtime modules consume --------------------------------------

/** A playback plan for `AudioScheduler.loadPlan()`. */
export function buildBenchmarkPlan({ eventCount }) {
  const workload = buildBenchmarkWorkload(eventCount);
  return {
    schema_version: "1.0.0",
    assignment_id: "bench-assignment",
    content_id: "bench-content",
    total_seconds: workload.total_ms / 1000,
    events: workload.events.map((event) => ({
      event_id: event.event_id,
      onset_seconds: event.onset_ms / 1000,
      release_seconds: event.release_ms / 1000,
      midi_note: event.midi_note,
      velocity: event.velocity,
    })),
  };
}

/** A fretboard projection for `FretboardRenderer.load()`. */
export function buildBenchmarkProjection({ eventCount }) {
  const workload = buildBenchmarkWorkload(eventCount);
  const lanes = Array.from({ length: STRINGS }, (_, index) => ({
    string_id: `bench-string-${index}`,
    display_order: index,
    display_name: `S${index}`,
    open_midi_note: 40 + index * 5,
  }));
  return {
    schema_version: "1.0.0",
    instrument: { display_name: "Benchmark six-string", lanes },
    timeline: { play_line_fraction: 0.22, total_seconds: workload.total_ms / 1000 },
    notes: workload.events.map((event) => ({
      event_id: event.event_id,
      canonical_event_id: event.canonical_event_id,
      string_id: `bench-string-${event.string_index}`,
      fret_number: event.fret,
      status: "selected",
      onset_seconds: event.onset_ms / 1000,
      release_seconds: event.release_ms / 1000,
      midi_note: event.midi_note,
    })),
  };
}

/**
 * A TAB projection payload, shaped like the checked-in ones.
 *
 * The shapes differ between the two score views -- TAB is a flat event list,
 * notation is measures holding events -- so they are built separately from one
 * workload rather than one payload bent to fit both.
 */
export function buildBenchmarkTabPayload({ eventCount }) {
  const workload = buildBenchmarkWorkload(eventCount);
  return {
    schema_version: "1.0.0",
    canonical_revision_id: "bench-revision",
    instrument_profile_id: "bench-instrument",
    events: workload.events.map((event, index) => ({
      schema_version: "1.0.0",
      canonical_event_id: event.canonical_event_id,
      start_tick: index * 480,
      duration_ticks: 480,
      midi_note: event.midi_note,
      status: "playable",
      string_id: `bench-string-${event.string_index}`,
      fret: event.fret,
      cents_offset: 0.0,
    })),
    unsupported_features: [],
  };
}

const PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

function displayPitch(midiNote) {
  const name = PITCH_NAMES[midiNote % 12];
  const octave = Math.floor(midiNote / 12) - 1;
  return `${name}${octave}`;
}

/** A notation projection payload: four events per measure, like the real ones. */
export function buildBenchmarkNotationPayload({ eventCount }) {
  const workload = buildBenchmarkWorkload(eventCount);
  const perMeasure = 4;
  const measures = [];
  for (let index = 0; index < workload.events.length; index += perMeasure) {
    const slice = workload.events.slice(index, index + perMeasure);
    const measureIndex = measures.length;
    measures.push({
      schema_version: "1.0.0",
      measure_index: measureIndex,
      start_tick: measureIndex * 1920,
      end_tick: (measureIndex + 1) * 1920,
      meter: { schema_version: "1.0.0", tick: measureIndex * 1920, numerator: 4, denominator: 4 },
      events: slice.map((event, offset) => ({
        schema_version: "1.0.0",
        event_kind: "note",
        start_tick: measureIndex * 1920 + offset * 480,
        duration_ticks: 480,
        canonical_event_id: event.canonical_event_id,
        midi_note: event.midi_note,
        display_pitch: displayPitch(event.midi_note),
        display_duration: "quarter",
        derivation: null,
      })),
    });
  }
  return {
    schema_version: "1.0.0",
    canonical_revision_id: "bench-revision",
    ticks_per_quarter: 480,
    display_policy: { schema_version: "1.0.0" },
    measures,
    unsupported_features: [],
  };
}

export function buildBenchmarkLanes() {
  return Array.from({ length: STRINGS }, (_, index) => ({
    string_id: `bench-string-${index}`,
    display_order: index,
    display_name: `S${index}`,
    open_midi_note: 40 + index * 5,
  }));
}

// --- a document that counts, so the renderer does not have to ----------------

/**
 * A DOM element that records how many style writes it receives.
 *
 * The renderer must not grow a counter to be measurable, so the counting lives
 * out here. What this measures is the number of property assignments and the
 * JavaScript around them -- not layout, style recalculation or paint, which
 * only a real browser can tell us about.
 */
export function createCountingElement(tagName = "div", counters) {
  const classes = new Set();
  const style = new Proxy(
    {},
    {
      set(target, key, value) {
        counters.styleWrites += 1;
        target[key] = value;
        return true;
      },
    },
  );
  const element = {
    tagName: String(tagName).toUpperCase(),
    textContent: "",
    innerHTML: "",
    style,
    children: [],
    dataset: {},
    clientWidth: 900,
    classList: {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
      toggle: (name, force) => {
        const next = force === undefined ? !classes.has(name) : Boolean(force);
        counters.classToggles += 1;
        if (next) classes.add(name);
        else classes.delete(name);
        return next;
      },
    },
    setAttribute() {},
    removeAttribute() {},
    getAttribute: () => null,
    appendChild(child) {
      element.children.push(child);
      return child;
    },
    append(...nodes) {
      element.children.push(...nodes);
    },
    replaceChildren(...nodes) {
      element.children = nodes;
    },
    remove() {},
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {},
    getBoundingClientRect: () => ({ width: 900, height: 300, top: 0, left: 0 }),
  };
  return element;
}

export function installCountingDocument(counters) {
  const previous = globalThis.document;
  globalThis.document = {
    createElement: (tagName) => createCountingElement(tagName, counters),
    createElementNS: (_ns, tagName) => createCountingElement(tagName, counters),
  };
  return () => {
    if (previous === undefined) delete globalThis.document;
    else globalThis.document = previous;
  };
}

export function newCounters() {
  return { styleWrites: 0, classToggles: 0 };
}

// --- sampling ----------------------------------------------------------------

export function benchmark(fn, { iterations = 50, warmup = 10 } = {}) {
  for (let index = 0; index < warmup; index += 1) fn(index);
  const samples = [];
  for (let index = 0; index < iterations; index += 1) {
    const started = performance.now();
    fn(index);
    samples.push(performance.now() - started);
  }
  return samples;
}

export function percentile(samples, p) {
  if (!samples.length) return 0;
  const sorted = [...samples].sort((a, b) => a - b);
  const rank = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[Math.max(0, rank)];
}

export function summarize(samples) {
  const sorted = [...samples].sort((a, b) => a - b);
  return {
    iterations: samples.length,
    median_ms: percentile(sorted, 50),
    p95_ms: percentile(sorted, 95),
    min_ms: sorted[0] ?? 0,
    max_ms: sorted[sorted.length - 1] ?? 0,
  };
}
