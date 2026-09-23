/**
 * M2 and M3 — what a frame costs in the renderer, and what the loop adds.
 *
 * The claim under test: `renderFrame()` writes a position for every rendered
 * note on every animation frame, on-screen or not, and the app loop then scans
 * the notes again through `activeEventIds()`.
 *
 * **What this measures and what it cannot.** The elements here are plain
 * objects whose `style` is a counting proxy, so this measures the JavaScript
 * traversal and the *number* of style writes issued. It does not measure
 * style recalculation, layout or paint, which is where a real browser would
 * spend its time on a thousand absolutely-positioned elements. A conclusion
 * about the DOM cost of this loop cannot be drawn from these numbers, and the
 * report says so rather than dressing the traversal figure up as a frame cost.
 *
 * The style-write count is the durable finding here: it is exact, harness
 * independent, and it is the quantity a viewport cull would change.
 *
 * Emits JSON on stdout. Changes nothing.
 */

import { FretboardRenderer } from "../../renderer.js";
import {
  WORKLOAD_SIZES,
  benchmark,
  buildBenchmarkProjection,
  createCountingElement,
  installCountingDocument,
  newCounters,
  summarize,
} from "./benchmark-fixtures.js";

const ROOT_KEYS = [
  "scrollViewport",
  "scrollCanvas",
  "laneLabels",
  "playLine",
  "gutterNotes",
  "neckMap",
  "instrumentTitle",
];

function renderer(eventCount, counters) {
  const roots = {};
  for (const key of ROOT_KEYS) roots[key] = createCountingElement("div", counters);
  const instance = new FretboardRenderer(roots);
  instance.load(buildBenchmarkProjection({ eventCount }));
  return instance;
}

function measure(eventCount) {
  const counters = newCounters();
  const restore = installCountingDocument(counters);
  try {
    const instance = renderer(eventCount, counters);
    const totalSeconds = instance.projection.timeline.total_seconds || 1;

    // A frame's work should not depend on where the playhead is: every note
    // gets a write either way. Measured at three positions to show that.
    const positions = [0.05, 0.5, 0.95].map((fraction) => totalSeconds * fraction);
    const iterations = eventCount >= 10000 ? 30 : 60;

    const built = counters.styleWrites;
    const frame = benchmark(
      (index) => instance.renderFrame(positions[index % positions.length]),
      { iterations, warmup: 10 },
    );
    const framesMeasured = iterations + 10;
    const writesDuringFrames = counters.styleWrites - built;

    const beforeActive = counters.styleWrites;
    const active = benchmark(() => instance.activeEventIds(), { iterations, warmup: 10 });
    const activeWrites = counters.styleWrites - beforeActive;

    // The loop as app.js runs it: a frame, then the notes scanned again for
    // the active set the timeline publishes.
    const loop = benchmark(
      (index) => {
        instance.renderFrame(positions[index % positions.length]);
        instance.activeEventIds();
      },
      { iterations, warmup: 10 },
    );

    return {
      notes_rendered: instance.notes.length,
      render_frame: {
        ...summarize(frame),
        style_writes_per_frame: writesDuringFrames / framesMeasured,
        class_toggles_total: counters.classToggles,
      },
      active_event_ids: { ...summarize(active), style_writes: activeWrites },
      frame_plus_active: summarize(loop),
    };
  } finally {
    restore();
  }
}

const measurements = {};
for (const size of WORKLOAD_SIZES) {
  measurements[String(size)] = measure(size);
}

process.stdout.write(
  JSON.stringify(
    {
      benchmark: "fretboard_render_frame",
      risk: "M2, M3",
      measures: "JavaScript traversal and style-write counts against stub elements",
      does_not_measure: ["style recalculation", "layout", "paint", "compositing"],
      measurements,
    },
    null,
    2,
  ),
);
