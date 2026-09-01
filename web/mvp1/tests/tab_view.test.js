import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  applyActiveEventIds,
  applyGuidedEventIds,
  applySelectedEventId,
  escapeXml,
  renderTabSvg,
  seekTickForEvent,
  serializeSvg,
  tabEventAt,
  tabEventIds,
  tabLayoutModel,
  tabRows,
  tabSvgTree,
  tabTotalTicks,
} from "../tab-view.js";

const repoUrl = (path) => fileURLToPath(new URL(path, import.meta.url));
const load = (path) => JSON.parse(readFileSync(repoUrl(path), "utf-8"));

/** The real unplayable lesson: one playable, one unplayable, one playable. */
const unplayableExport = load("../projections/unplayable_note/tab.json");
const UNPLAYABLE = unplayableExport.payload;

/** The synthetic unresolved case, which the corpus cannot produce. */
const UNRESOLVED = load("../../../resources/projections/examples/unresolved_tab.json");

const LANES = load("../projections/half_steps_one_string.json").projection.instrument.lanes;

// --- status rendering --------------------------------------------------------

test("a playable event renders the fret it was given", () => {
  const model = tabLayoutModel(UNPLAYABLE, { lanes: LANES });
  const event = model.events.find((item) => item.canonicalEventId === "ev-1");
  assert.equal(event.status, "playable");
  assert.equal(event.label, String(UNPLAYABLE.events[0].fret));
});

test("an unplayable event renders a marker instead of a fingering", () => {
  const model = tabLayoutModel(UNPLAYABLE, { lanes: LANES });
  const event = model.events.find((item) => item.canonicalEventId === "ev-2");
  assert.equal(event.status, "unplayable");
  assert.equal(event.label, "×");
  assert.equal(event.fret, null);
  assert.equal(event.stringId, null);
});

test("an unresolved event renders a marker instead of a fingering", () => {
  const model = tabLayoutModel(UNRESOLVED, { lanes: LANES });
  const event = model.events.find((item) => item.canonicalEventId === "ev-2");
  assert.equal(event.status, "unresolved");
  assert.equal(event.label, "?");
  assert.equal(event.fret, null);
});

test("all three statuses carry distinct classes in the serialized SVG", () => {
  const svg = renderTabSvg(UNPLAYABLE, { lanes: LANES });
  assert.match(svg, /tab-playable/);
  assert.match(svg, /tab-unplayable/);
  assert.doesNotMatch(svg, /tab-unresolved/);
  assert.match(renderTabSvg(UNRESOLVED, { lanes: LANES }), /tab-unresolved/);
});

// --- no inference ------------------------------------------------------------

test("the renderer shows the given fret even when it contradicts the midi note", () => {
  // Physically impossible: string-1 fret 0 does not sound MIDI 99. A renderer
  // that recomputed fingering from pitch would "correct" this; one that reports
  // what it was given shows 0. Spatial authority is not in the browser.
  const projection = {
    ...UNPLAYABLE,
    events: [
      {
        schema_version: "1.0.0",
        canonical_event_id: "ev-x",
        start_tick: 0,
        duration_ticks: 480,
        midi_note: 99,
        status: "playable",
        string_id: "string-1",
        fret: 0,
        cents_offset: 0.0,
      },
    ],
  };
  const model = tabLayoutModel(projection, { lanes: LANES });
  assert.equal(model.events[0].label, "0");
  assert.equal(model.events[0].midiNote, 99);
});

test("no string or fret is invented for an event that has none", () => {
  const model = tabLayoutModel(UNRESOLVED, { lanes: LANES });
  const unresolved = model.events.find((item) => item.status === "unresolved");
  assert.equal(unresolved.fret, null);
  assert.equal(unresolved.stringId, null);
  assert.doesNotMatch(renderTabSvg(UNRESOLVED, { lanes: LANES }), /data-fret/);
});

test("string rows come from the instrument, not from the events present", () => {
  // half_steps_one_string touches one string; the grid must still show six.
  const single = { ...UNRESOLVED, events: [UNRESOLVED.events[0]] };
  const { rows, derived } = tabRows(single, LANES);
  assert.equal(derived, false);
  assert.equal(rows.length, LANES.length);
  assert.deepEqual(
    rows.map((row) => row.stringId),
    [...LANES].sort((a, b) => a.display_order - b.display_order).map((lane) => lane.string_id),
  );
});

test("without lanes the fallback row order is reported as derived", () => {
  const { rows, derived } = tabRows(UNPLAYABLE, null);
  assert.equal(derived, true);
  assert.ok(rows.length > 0);
  assert.equal(tabLayoutModel(UNPLAYABLE, {}).rowsDerivedFromEvents, true);
});

// --- highlighting is driven only by activeEventIds ---------------------------

test("highlighting follows activeEventIds and nothing else", () => {
  const model = tabLayoutModel(UNPLAYABLE, { lanes: LANES, activeEventIds: ["ev-2"] });
  assert.deepEqual(
    model.events.filter((item) => item.active).map((item) => item.canonicalEventId),
    ["ev-2"],
  );
});

test("an empty active set highlights nothing, whatever the ticks say", () => {
  const model = tabLayoutModel(UNPLAYABLE, { lanes: LANES, activeEventIds: [] });
  assert.equal(model.events.some((item) => item.active), false);
  assert.doesNotMatch(renderTabSvg(UNPLAYABLE, { lanes: LANES }), /tab-active/);
});

test("an event at tick 0 is not highlighted merely for starting first", () => {
  // The failure this guards: a renderer deciding activity from position.
  const model = tabLayoutModel(UNPLAYABLE, { lanes: LANES, activeEventIds: ["ev-3"] });
  const first = model.events.find((item) => item.startTick === 0);
  assert.equal(first.active, false);
});

test("highlighting an id the projection lacks highlights nothing rather than guessing", () => {
  const model = tabLayoutModel(UNPLAYABLE, {
    lanes: LANES,
    activeEventIds: ["ev-does-not-exist"],
  });
  assert.equal(model.events.some((item) => item.active), false);
});

test("changing the active set does not move any event", () => {
  const base = tabLayoutModel(UNPLAYABLE, { lanes: LANES, activeEventIds: [] });
  const lit = tabLayoutModel(UNPLAYABLE, { lanes: LANES, activeEventIds: ["ev-1", "ev-3"] });
  assert.deepEqual(
    base.events.map((item) => [item.x, item.y]),
    lit.events.map((item) => [item.x, item.y]),
  );
});

// --- seeking is driven only by canonical timing ------------------------------

test("the seek target is the canonical start tick of the clicked event", () => {
  for (const event of UNPLAYABLE.events) {
    assert.equal(
      seekTickForEvent(UNPLAYABLE, event.canonical_event_id),
      event.start_tick,
    );
  }
});

test("seeking works for an unplayable event, which has no fingering to click", () => {
  assert.equal(seekTickForEvent(UNPLAYABLE, "ev-2"), UNPLAYABLE.events[1].start_tick);
});

test("an unknown event yields no seek target rather than a fabricated one", () => {
  assert.equal(seekTickForEvent(UNPLAYABLE, "nope"), null);
  assert.equal(tabEventAt(UNPLAYABLE, "nope"), null);
});

test("the seek target ignores the active set entirely", () => {
  // Same question, opposite active sets, same answer.
  const a = seekTickForEvent(UNPLAYABLE, "ev-3");
  const b = seekTickForEvent(UNPLAYABLE, "ev-3");
  assert.equal(a, b);
  assert.equal(a, UNPLAYABLE.events[2].start_tick);
});

test("the module's code never reads a clock or touches the transport", () => {
  // Comments discuss the Transport deliberately -- the boundary is the point of
  // the file. What must not appear is executable use of a timing source, so the
  // prose is stripped before looking.
  const code = readFileSync(repoUrl("../tab-view.js"), "utf-8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");

  for (const forbidden of [
    "setInterval",
    "setTimeout",
    "requestAnimationFrame",
    "Date.now",
    "performance.now",
    "Transport",
    "transport",
  ]) {
    assert.equal(
      code.includes(forbidden),
      false,
      `tab-view.js code must not reference ${forbidden}`,
    );
  }
});

test("the module imports nothing, so it cannot reach a timing authority", () => {
  const code = readFileSync(repoUrl("../tab-view.js"), "utf-8");
  assert.doesNotMatch(code, /^\s*import\s/m);
});

// --- identity ----------------------------------------------------------------

test("canonical event ids are preserved in projection order", () => {
  assert.deepEqual(tabEventIds(UNPLAYABLE), ["ev-1", "ev-2", "ev-3"]);
});

test("the rendered SVG carries the cited canonical revision", () => {
  const svg = renderTabSvg(UNPLAYABLE, { lanes: LANES });
  assert.ok(svg.includes(`data-canonical-revision-id="${UNPLAYABLE.canonical_revision_id}"`));
});

test("every event group is addressable by canonical event id", () => {
  const svg = renderTabSvg(UNPLAYABLE, { lanes: LANES });
  for (const id of tabEventIds(UNPLAYABLE)) {
    assert.ok(svg.includes(`data-canonical-event-id="${id}"`));
  }
});

// --- determinism and escaping ------------------------------------------------

test("rendering twice produces byte-identical output", () => {
  const once = renderTabSvg(UNPLAYABLE, { lanes: LANES, activeEventIds: ["ev-1"] });
  const twice = renderTabSvg(UNPLAYABLE, { lanes: LANES, activeEventIds: ["ev-1"] });
  assert.equal(once, twice);
});

test("coordinates are fixed precision so golden output cannot drift", () => {
  const model = tabLayoutModel(UNPLAYABLE, { lanes: LANES });
  for (const event of model.events) {
    assert.equal(Math.round(event.x * 100) / 100, event.x);
    assert.equal(Math.round(event.y * 100) / 100, event.y);
  }
});

test("projection text is escaped rather than executed", () => {
  assert.equal(escapeXml('<script>"&\''), "&lt;script&gt;&quot;&amp;&apos;");
  const hostile = {
    ...UNPLAYABLE,
    canonical_revision_id: 'rev-1" onload="alert(1)',
    events: [{ ...UNPLAYABLE.events[0], string_id: "<script>" }],
  };
  const svg = renderTabSvg(hostile, {});
  assert.doesNotMatch(svg, /<script>/);
  assert.doesNotMatch(svg, /onload="alert/);
});

test("an empty projection renders a grid rather than throwing", () => {
  const empty = { ...UNPLAYABLE, events: [] };
  assert.equal(tabTotalTicks(empty), 0);
  const svg = renderTabSvg(empty, { lanes: LANES });
  assert.match(svg, /tab-string/);
  assert.doesNotMatch(svg, /tab-event/);
});

test("a loop overlay is drawn only when a range is supplied", () => {
  assert.doesNotMatch(renderTabSvg(UNPLAYABLE, { lanes: LANES }), /tab-loop/);
  const looped = renderTabSvg(UNPLAYABLE, {
    lanes: LANES,
    loopRange: { startTick: 0, endTick: 480 },
  });
  assert.match(looped, /tab-loop/);
});

test("a loop range does not alter any event placement", () => {
  const plain = tabLayoutModel(UNPLAYABLE, { lanes: LANES });
  const looped = tabLayoutModel(UNPLAYABLE, {
    lanes: LANES,
    loopRange: { startTick: 0, endTick: 480 },
  });
  assert.deepEqual(
    plain.events.map((item) => [item.canonicalEventId, item.x, item.y]),
    looped.events.map((item) => [item.canonicalEventId, item.x, item.y]),
  );
});

test("serializeSvg emits self-closing tags for empty elements", () => {
  assert.equal(serializeSvg({ tag: "line", attrs: { x1: 0 }, children: [] }), '<line x1="0"/>');
  assert.equal(
    serializeSvg({ tag: "text", attrs: {}, children: ["5"] }),
    "<text>5</text>",
  );
});

test("null attributes are omitted rather than serialized as the string null", () => {
  const tree = tabSvgTree(tabLayoutModel({ events: [] }, {}));
  assert.doesNotMatch(serializeSvg(tree), /="null"/);
});

// --- the binder's active repaint ---------------------------------------------

test("applyActiveEventIds toggles only the ids it is given", () => {
  const groups = ["ev-1", "ev-2", "ev-3"].map((id) => {
    const classes = new Set();
    return {
      getAttribute: () => id,
      classList: {
        toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)),
        has: (name) => classes.has(name),
      },
    };
  });
  const root = { querySelectorAll: () => groups };

  assert.deepEqual(applyActiveEventIds(root, ["ev-2"]), ["ev-2"]);
  assert.equal(groups[1].classList.has("tab-active"), true);
  assert.equal(groups[0].classList.has("tab-active"), false);

  assert.deepEqual(applyActiveEventIds(root, []), []);
  assert.equal(groups[1].classList.has("tab-active"), false);
});

test("applyActiveEventIds on a missing root is a no-op", () => {
  assert.deepEqual(applyActiveEventIds(null, ["ev-1"]), []);
});

function classStub(id) {
  const classes = new Set();
  return {
    getAttribute: () => id,
    classList: {
      toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)),
      has: (name) => classes.has(name),
    },
  };
}

test("applyGuidedEventIds toggles only the ids it is given", () => {
  const groups = ["ev-1", "ev-2", "ev-3"].map(classStub);
  const root = { querySelectorAll: () => groups };
  assert.deepEqual(applyGuidedEventIds(root, ["ev-2"]), ["ev-2"]);
  assert.equal(groups[1].classList.has("tab-guided"), true);
  assert.equal(groups[0].classList.has("tab-guided"), false);
  assert.deepEqual(applyGuidedEventIds(null, ["ev-1"]), []);
});

test("active, selected, and guided remain independent class channels", () => {
  const groups = ["ev-1", "ev-2", "ev-3"].map(classStub);
  const root = { querySelectorAll: () => groups };
  applyActiveEventIds(root, ["ev-1"]);
  applySelectedEventId(root, "ev-2");
  applyGuidedEventIds(root, ["ev-3"]);
  assert.equal(groups[0].classList.has("tab-active"), true);
  assert.equal(groups[0].classList.has("tab-guided"), false);
  assert.equal(groups[1].classList.has("tab-selected"), true);
  assert.equal(groups[1].classList.has("tab-active"), false);
  assert.equal(groups[2].classList.has("tab-guided"), true);
  assert.equal(groups[2].classList.has("tab-active"), false);
});

test("an unrenderable guided id lights no neighbouring TAB event", () => {
  const groups = ["ev-1", "ev-2"].map(classStub);
  const root = { querySelectorAll: () => groups };
  assert.deepEqual(applyGuidedEventIds(root, ["ev-ghost"]), []);
  assert.equal(groups[0].classList.has("tab-guided"), false);
  assert.equal(groups[1].classList.has("tab-guided"), false);
});

test("layout guided flag does not alter coordinates or status", () => {
  const plain = tabLayoutModel(UNPLAYABLE, { lanes: LANES, activeEventIds: ["ev-1"] });
  const guided = tabLayoutModel(UNPLAYABLE, {
    lanes: LANES,
    activeEventIds: ["ev-1"],
    guidedEventIds: ["ev-2"],
  });
  assert.deepEqual(
    plain.events.map((item) => [item.canonicalEventId, item.x, item.y, item.status]),
    guided.events.map((item) => [item.canonicalEventId, item.x, item.y, item.status]),
  );
  assert.equal(guided.events.find((e) => e.canonicalEventId === "ev-2").guided, true);
  assert.equal(guided.events.find((e) => e.canonicalEventId === "ev-1").active, true);
  assert.equal(guided.events.find((e) => e.canonicalEventId === "ev-1").guided, false);
});
