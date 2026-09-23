/**
 * M4, M5 and M10 — TAB and notation: active updates, full mounts, lookups.
 *
 * Three claims under test: active-state updates traverse the whole rendered
 * SVG, a mount serializes the entire score and replaces `innerHTML`, and event
 * navigation scans the payload linearly.
 *
 * **Where the harness runs out.** Two of the three costs are pure JavaScript
 * and measured honestly here: building the layout model, building the SVG tree
 * and serializing it to a string; and scanning a payload for one event. The
 * third is not. `applyActiveEventIds()` calls `root.querySelectorAll()` over a
 * real SVG tree, and no stub can tell us what that costs in a browser. What is
 * measured instead is the per-element loop that follows the selector, over a
 * node list of known size -- a lower bound on the work, not the cost of the
 * query. The selector traversal and the `innerHTML` parse are reported as
 * INSUFFICIENT_EVIDENCE rather than guessed at.
 *
 * Emits JSON on stdout. Changes nothing.
 */

import {
  applyActiveEventIds as applyNotationActive,
  notationEventAt,
  renderNotationSvg,
  seekTickForEvent as notationSeekTick,
} from "../../notation-view.js";
import {
  applyActiveEventIds as applyTabActive,
  renderTabSvg,
  tabEventAt,
  tabLayoutModel,
  tabSvgTree,
  seekTickForEvent as tabSeekTick,
  serializeSvg,
} from "../../tab-view.js";
import {
  WORKLOAD_SIZES,
  benchmark,
  buildBenchmarkLanes,
  buildBenchmarkNotationPayload,
  buildBenchmarkTabPayload,
  newCounters,
  summarize,
} from "./benchmark-fixtures.js";

/** A node list of the size a mounted score would produce, and nothing more. */
function fakeGroups(payload, counters) {
  return payload.events.map((event) => ({
    getAttribute: () => event.canonical_event_id,
    classList: {
      toggle: (_name, force) => {
        counters.classToggles += 1;
        return Boolean(force);
      },
    },
  }));
}

function fakeRoot(payload, counters) {
  const groups = fakeGroups(payload, counters);
  return { querySelectorAll: () => groups };
}

function measureActive(apply, payload, iterations) {
  const counters = newCounters();
  const root = fakeRoot(payload, counters);
  const ids = payload.events.map((event) => event.canonical_event_id);
  const scenarios = {
    none: [],
    one: ids.slice(0, 1),
    eight: ids.slice(0, 8),
    shifted_by_one: ids.slice(1, 9),
  };
  const results = {};
  for (const [name, active] of Object.entries(scenarios)) {
    results[name] = summarize(benchmark(() => apply(root, active), { iterations, warmup: 10 }));
  }
  results.elements_visited_per_call = payload.events.length;
  results.class_toggles_total = counters.classToggles;
  return results;
}

function measureMount(tabPayload, notationPayload, lanes, iterations) {
  const options = { lanes };
  const payload = tabPayload;
  const model = tabLayoutModel(payload, options);
  return {
    tab_layout_model: summarize(
      benchmark(() => tabLayoutModel(payload, options), { iterations, warmup: 5 }),
    ),
    tab_svg_tree: summarize(benchmark(() => tabSvgTree(model), { iterations, warmup: 5 })),
    tab_serialize: summarize(
      benchmark(() => serializeSvg(tabSvgTree(model)), { iterations, warmup: 5 }),
    ),
    tab_render_total: summarize(
      benchmark(() => renderTabSvg(payload, options), { iterations, warmup: 5 }),
    ),
    notation_render_total: summarize(
      benchmark(() => renderNotationSvg(notationPayload, {}), { iterations, warmup: 5 }),
    ),
    tab_svg_characters: renderTabSvg(payload, options).length,
    notation_svg_characters: renderNotationSvg(notationPayload, {}).length,
  };
}

function measureLookup(payload, notationPayload, iterations) {
  const ids = payload.events.map((event) => event.canonical_event_id);
  const targets = {
    first: ids[0],
    middle: ids[Math.floor(ids.length / 2)],
    last: ids[ids.length - 1],
    missing: "bench-canonical-does-not-exist",
  };
  const results = {};
  for (const [name, id] of Object.entries(targets)) {
    results[`tab_${name}`] = summarize(
      benchmark(() => tabEventAt(payload, id), { iterations, warmup: 10 }),
    );
    results[`notation_${name}`] = summarize(
      benchmark(() => notationEventAt(notationPayload, id), { iterations, warmup: 10 }),
    );
  }
  results.tab_seek_tick_last = summarize(
    benchmark(() => tabSeekTick(payload, targets.last), { iterations, warmup: 10 }),
  );
  results.notation_seek_tick_last = summarize(
    benchmark(() => notationSeekTick(notationPayload, targets.last), { iterations, warmup: 10 }),
  );
  return results;
}

const lanes = buildBenchmarkLanes();
const measurements = {};
for (const size of WORKLOAD_SIZES) {
  const payload = buildBenchmarkTabPayload({ eventCount: size });
  const notationPayload = buildBenchmarkNotationPayload({ eventCount: size });
  const iterations = size >= 10000 ? 15 : 40;
  measurements[String(size)] = {
    tab_active: measureActive(applyTabActive, payload, iterations),
    notation_active: measureActive(applyNotationActive, payload, iterations),
    mount: measureMount(payload, notationPayload, lanes, size >= 10000 ? 5 : 20),
    lookup: measureLookup(payload, notationPayload, iterations),
  };
}

process.stdout.write(
  JSON.stringify(
    {
      benchmark: "score_views",
      risk: "M4, M5, M10",
      measures: [
        "layout model, SVG tree and serialization cost",
        "the per-element loop inside applyActiveEventIds",
        "linear event lookup",
      ],
      does_not_measure: [
        "querySelectorAll over a real SVG tree",
        "innerHTML parsing and DOM construction",
        "layout and paint of a mounted score",
      ],
      measurements,
    },
    null,
    2,
  ),
);
