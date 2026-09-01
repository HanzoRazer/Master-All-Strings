import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { ScoreViewCoordinator } from "../score-view.js";
import {
  applyActiveEventIds as tabActive,
  applySelectedEventId as tabSelect,
  mountTabView,
} from "../tab-view.js";
import {
  applyActiveEventIds as notationActive,
  applySelectedEventId as notationSelect,
  mountNotationView,
} from "../notation-view.js";

const repoUrl = (path) => fileURLToPath(new URL(path, import.meta.url));
const load = (path) => JSON.parse(readFileSync(repoUrl(path), "utf-8"));

const DEMO = "half_steps_one_string";
const REVISION = load(`../projections/${DEMO}/canonical_revision.json`);
const TAB = load(`../projections/${DEMO}/tab.json`);
const NOTATION = load(`../projections/${DEMO}/notation.json`);
const CONTEXT = load(`../projections/${DEMO}.json`);

function loaderFor(overrides = {}) {
  const files = {
    [`projections/${DEMO}/canonical_revision.json`]: REVISION,
    [`projections/${DEMO}/tab.json`]: TAB,
    [`projections/${DEMO}/notation.json`]: NOTATION,
    [`projections/${DEMO}.json`]: CONTEXT,
    ...overrides,
  };
  return async (path) => {
    if (!(path in files)) throw new Error(`missing ${path}`);
    return structuredClone(files[path]);
  };
}

/** Renderers recording active and selection channels separately. */
function fakeRenderers() {
  const state = {
    tab: { active: [], selected: null, guided: [] },
    notation: { active: [], selected: null, guided: [] },
  };
  const make = (name) => ({
    mount: (container, payload, options) => ({ name, payload, options }),
    applyActive: (root, ids) => {
      state[name].active = [...ids];
      return [...ids];
    },
    applySelection: (root, id) => {
      state[name].selected = id;
      // Only claim an id this view can actually depict.
      const depicts =
        name === "tab"
          ? (root.payload.events ?? []).some((e) => e.canonical_event_id === id)
          : (root.payload.measures ?? []).some((m) =>
              (m.events ?? []).some((e) => e.canonical_event_id === id),
            );
      return depicts ? id : null;
    },
    applyGuidance: (root, ids) => {
      const available = new Set(
        name === "tab"
          ? (root.payload.events ?? []).map((e) => e.canonical_event_id)
          : (root.payload.measures ?? []).flatMap((m) =>
              (m.events ?? []).map((e) => e.canonical_event_id).filter(Boolean),
            ),
      );
      state[name].guided = ids.filter((id) => available.has(id));
      return [...state[name].guided];
    },
  });
  return { renderers: { tab: make("tab"), notation: make("notation") }, state };
}

async function ready(options = {}) {
  const { overrides = {}, ...rest } = options;
  const { renderers, state } = fakeRenderers();
  const seeks = [];
  const view = new ScoreViewCoordinator({
    loadJson: loaderFor(overrides),
    renderers,
    containers: { tab: {}, notation: {} },
    onSeek: (id, tick) => seeks.push([id, tick]),
    ...rest,
  });
  await view.load(DEMO);
  return { view, state, seeks };
}

/** A narrow element fake: enough for the binder, not a DOM implementation. */
function fakeContainer(groups) {
  const listeners = {};
  return {
    innerHTML: "",
    firstChild: { querySelectorAll: () => groups },
    addEventListener: (type, handler) => {
      listeners[type] = handler;
    },
    dispatch(type, target) {
      listeners[type]?.({ target, key: type === "keydown" ? "Enter" : undefined, preventDefault() {} });
    },
  };
}

function fakeGroup(id) {
  const classes = new Set();
  const group = {
    getAttribute: (name) => (name === "data-canonical-event-id" ? id : null),
    classList: {
      toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)),
      has: (name) => classes.has(name),
    },
  };
  group.closest = () => group;
  return group;
}

// --- click to seek -----------------------------------------------------------

test("a TAB click seeks the clicked event's authored position", async () => {
  const { view, seeks } = await ready();
  for (const event of TAB.payload.events) {
    const tick = view.seekTo(event.canonical_event_id);
    assert.equal(tick, event.start_tick);
  }
  assert.deepEqual(
    seeks,
    TAB.payload.events.map((e) => [e.canonical_event_id, e.start_tick]),
  );
});

test("a notation click seeks the clicked note's authored position", async () => {
  const { view } = await ready();
  for (const measure of NOTATION.payload.measures) {
    for (const event of measure.events) {
      if (!event.canonical_event_id) continue;
      assert.equal(view.seekTo(event.canonical_event_id), event.start_tick);
    }
  }
});

test("the TAB binder turns a click into a seek at the right tick", () => {
  const groups = TAB.payload.events.map((e) => fakeGroup(e.canonical_event_id));
  const container = fakeContainer(groups);
  const seeks = [];
  mountTabView(container, TAB.payload, { onSeek: (id, tick) => seeks.push([id, tick]) });

  container.dispatch("click", groups[2]);
  assert.deepEqual(seeks, [
    [TAB.payload.events[2].canonical_event_id, TAB.payload.events[2].start_tick],
  ]);
});

test("the notation binder turns a keyboard activation into a seek", () => {
  const notes = NOTATION.payload.measures.flatMap((m) =>
    m.events.filter((e) => e.canonical_event_id),
  );
  const groups = notes.map((e) => fakeGroup(e.canonical_event_id));
  const container = fakeContainer(groups);
  const seeks = [];
  mountNotationView(container, NOTATION.payload, {
    onSeek: (id, tick) => seeks.push([id, tick]),
  });

  container.dispatch("keydown", groups[1]);
  assert.deepEqual(seeks, [[notes[1].canonical_event_id, notes[1].start_tick]]);
});

test("seeking an event the score does not contain does nothing", async () => {
  const { view, seeks } = await ready();
  assert.equal(view.seekTo("ev-nowhere"), null);
  assert.deepEqual(seeks, []);
  assert.equal(view.lastSeekTick, null);
});

test("two events sharing a pitch seek independently by id", async () => {
  // No bundled lesson repeats a pitch, so the case is constructed. Identity is
  // the join key precisely so that pitch collisions are irrelevant.
  const samePitchTab = structuredClone(TAB);
  samePitchTab.payload.events = [
    { ...TAB.payload.events[0], canonical_event_id: "ev-first", start_tick: 0, midi_note: 64 },
    { ...TAB.payload.events[0], canonical_event_id: "ev-second", start_tick: 1440, midi_note: 64 },
  ];
  const samePitchNotation = structuredClone(NOTATION);
  samePitchNotation.payload.measures = [
    {
      ...NOTATION.payload.measures[0],
      events: samePitchTab.payload.events.map((e) => ({
        schema_version: "1.0.0",
        event_kind: "note",
        start_tick: e.start_tick,
        duration_ticks: 480,
        canonical_event_id: e.canonical_event_id,
        midi_note: 64,
        display_pitch: "E4",
        display_duration: "quarter",
        derivation: null,
      })),
    },
  ];

  const { view } = await ready({
    overrides: {
      [`projections/${DEMO}/tab.json`]: samePitchTab,
      [`projections/${DEMO}/notation.json`]: samePitchNotation,
    },
  });

  assert.equal(view.seekTo("ev-first"), 0);
  assert.equal(view.seekTo("ev-second"), 1440);
  assert.notEqual(view.seekTickFor("ev-first"), view.seekTickFor("ev-second"));
});

// --- fretboard selection -----------------------------------------------------

test("fretboard selection highlights the matching event in both views", async () => {
  const { view, state } = await ready();
  const marked = view.selectEvent("ev-2");

  assert.equal(marked.tab, "ev-2");
  assert.equal(marked.notation, "ev-2");
  assert.equal(state.tab.selected, "ev-2");
  assert.equal(state.notation.selected, "ev-2");
  assert.equal(view.selectedEventId, "ev-2");
});

test("selecting null clears the selection in both views", async () => {
  const { view, state } = await ready();
  view.selectEvent("ev-2");
  view.selectEvent(null);
  assert.equal(view.selectedEventId, null);
  assert.equal(state.tab.selected, null);
  assert.equal(state.notation.selected, null);
});

test("selecting an event absent from one projection does not break the other", async () => {
  // A TAB-only event: present in tablature, absent from the notation payload.
  const partialNotation = structuredClone(NOTATION);
  partialNotation.payload.measures = partialNotation.payload.measures.map((m) => ({
    ...m,
    events: m.events.filter((e) => e.canonical_event_id !== "ev-2"),
  }));

  const { view, state } = await ready({
    overrides: { [`projections/${DEMO}/notation.json`]: partialNotation },
  });

  const marked = view.selectEvent("ev-2");
  assert.equal(marked.tab, "ev-2");
  assert.equal(marked.notation, null);
  // The view that cannot depict it is still alive and still selectable.
  assert.equal(view.views.notation.mounted, true);
  assert.equal(state.notation.selected, "ev-2");

  const shared = view.selectEvent("ev-1");
  assert.equal(shared.tab, "ev-1");
  assert.equal(shared.notation, "ev-1");
});

test("a selection failure in one view retires only that view", async () => {
  const { renderers } = fakeRenderers();
  renderers.tab.applySelection = () => {
    throw new Error("tab selection exploded");
  };
  const view = new ScoreViewCoordinator({
    loadJson: loaderFor(),
    renderers,
    containers: { tab: {}, notation: {} },
  });
  await view.load(DEMO);
  view.selectEvent("ev-1");

  assert.equal(view.views.tab.mounted, false);
  assert.match(view.views.tab.error, /tab selection exploded/);
  assert.equal(view.views.notation.mounted, true);
});

// --- selection and activity are independent ----------------------------------

test("selection does not modify the active set", async () => {
  const { view, state } = await ready();
  view.applyActiveEventIds(["ev-1"]);
  view.selectEvent("ev-3");

  assert.deepEqual(view.activeEventIds, ["ev-1"]);
  assert.deepEqual(state.tab.active, ["ev-1"]);
  assert.equal(state.tab.selected, "ev-3");
});

test("seeking does not make an event active", async () => {
  const { view, state } = await ready();
  view.seekTo("ev-3");

  assert.deepEqual(view.activeEventIds, []);
  assert.deepEqual(state.tab.active, []);
  assert.deepEqual(state.notation.active, []);
});

test("an event becomes active only when the playhead says so", async () => {
  const { view, state } = await ready();
  view.seekTo("ev-3");
  assert.deepEqual(state.tab.active, []);

  // The transport moved; the playhead then publishes its own answer.
  view.applyPlayhead({ active_event_ids: ["ev-3"], position_tick: 1440 });
  assert.deepEqual(state.tab.active, ["ev-3"]);
  assert.deepEqual(state.notation.active, ["ev-3"]);
});

test("the playhead may report an event other than the one just sought", async () => {
  // Nothing in the browser assumes seeking lands on the sought event: count-in,
  // loop bounds, and rate all belong to the transport.
  const { view, state } = await ready();
  view.seekTo("ev-1");
  view.applyPlayhead({ active_event_ids: ["ev-2"] });
  assert.deepEqual(state.tab.active, ["ev-2"]);
  assert.equal(view.lastSeekEventId, "ev-1");
});

test("active highlighting changes without changing the last seek target", async () => {
  const { view } = await ready();
  view.seekTo("ev-2");
  const tickAfterSeek = view.lastSeekTick;

  view.applyPlayhead({ active_event_ids: ["ev-1"] });
  view.applyPlayhead({ active_event_ids: ["ev-3"] });
  view.applyPlayhead({ active_event_ids: [] });

  assert.equal(view.lastSeekTick, tickAfterSeek);
  assert.equal(view.lastSeekEventId, "ev-2");
});

test("selection survives active-set changes", async () => {
  const { view, state } = await ready();
  view.selectEvent("ev-2");
  view.applyActiveEventIds(["ev-1"]);
  assert.equal(state.tab.selected, "ev-2");
  assert.equal(view.selectedEventId, "ev-2");
});

test("selecting A while the playhead reports B keeps both states distinct", async () => {
  // The conflation bug this exists to catch: selection quietly becoming
  // activity, so the view claims the reader's cursor is the sounding note.
  const { view, state } = await ready();
  view.applyPlayhead({ active_event_ids: ["ev-2"] });
  view.selectEvent("ev-1");

  assert.deepEqual(view.activeEventIds, ["ev-2"]);
  assert.equal(view.selectedEventId, "ev-1");
  assert.deepEqual(state.tab.active, ["ev-2"]);
  assert.equal(state.tab.selected, "ev-1");
  assert.deepEqual(state.notation.active, ["ev-2"]);
  assert.equal(state.notation.selected, "ev-1");

  // And the order of operations must not matter.
  const reversed = await ready();
  reversed.view.selectEvent("ev-1");
  reversed.view.applyPlayhead({ active_event_ids: ["ev-2"] });
  assert.deepEqual(reversed.view.activeEventIds, ["ev-2"]);
  assert.equal(reversed.view.selectedEventId, "ev-1");
});

test("the renderers mark A selected and B active as separate classes", () => {
  // Asserted on the real renderers, not the fakes: two groups, two channels.
  const groups = ["ev-1", "ev-2"].map(fakeGroup);
  const root = { querySelectorAll: () => groups };

  tabSelect(root, "ev-1");
  tabActive(root, ["ev-2"]);

  assert.equal(groups[0].classList.has("tab-selected"), true);
  assert.equal(groups[0].classList.has("tab-active"), false);
  assert.equal(groups[1].classList.has("tab-active"), true);
  assert.equal(groups[1].classList.has("tab-selected"), false);
});

test("one event may be both selected and active without either being lost", () => {
  const group = fakeGroup("ev-1");
  const root = { querySelectorAll: () => [group] };

  tabSelect(root, "ev-1");
  tabActive(root, ["ev-1"]);
  assert.equal(group.classList.has("tab-selected"), true);
  assert.equal(group.classList.has("tab-active"), true);

  // The playhead moves on; the selection stays where the reader put it.
  tabActive(root, []);
  assert.equal(group.classList.has("tab-active"), false);
  assert.equal(group.classList.has("tab-selected"), true);

  // And clearing the selection leaves activity alone.
  tabActive(root, ["ev-1"]);
  tabSelect(root, null);
  assert.equal(group.classList.has("tab-selected"), false);
  assert.equal(group.classList.has("tab-active"), true);
});

test("notation keeps the same separation for a doubly marked note", () => {
  const group = fakeGroup("ev-1");
  const root = { querySelectorAll: () => [group] };
  notationSelect(root, "ev-1");
  notationActive(root, ["ev-1"]);
  assert.equal(group.classList.has("notation-selected"), true);
  assert.equal(group.classList.has("notation-active"), true);

  notationSelect(root, null);
  assert.equal(group.classList.has("notation-active"), true);
});

test("the seek index holds ticks, leaving unit conversion to the existing seam", () => {
  // Transport.seek takes seconds; the index stores Core-authored ticks. The
  // bridge is DO-012's secondsAtTick over Core's anchor table, and it lives in
  // the shell -- putting it here would make the coordinator convert time.
  for (const event of TAB.payload.events) {
    assert.equal(typeof event.start_tick, "number");
  }
  const code = readFileSync(repoUrl("../score-view.js"), "utf-8");
  assert.doesNotMatch(code, /secondsAtTick/);
  assert.doesNotMatch(code, /tickAtSeconds/);
});

test("the two channels use different classes on the real renderers", () => {
  const group = fakeGroup("ev-1");
  const root = { querySelectorAll: () => [group] };

  tabSelect(root, "ev-1");
  assert.equal(group.classList.has("tab-selected"), true);
  assert.equal(group.classList.has("tab-active"), false);

  const noteGroup = fakeGroup("ev-1");
  notationSelect({ querySelectorAll: () => [noteGroup] }, "ev-1");
  assert.equal(noteGroup.classList.has("notation-selected"), true);
  assert.equal(noteGroup.classList.has("notation-active"), false);
});

test("selecting a different event unmarks the previous one", () => {
  const groups = ["ev-1", "ev-2"].map(fakeGroup);
  const root = { querySelectorAll: () => groups };
  tabSelect(root, "ev-1");
  assert.equal(groups[0].classList.has("tab-selected"), true);
  tabSelect(root, "ev-2");
  assert.equal(groups[0].classList.has("tab-selected"), false);
  assert.equal(groups[1].classList.has("tab-selected"), true);
});

// --- navigation changes no musical data --------------------------------------

test("navigation alters neither projection digests nor event counts", async () => {
  const { view } = await ready();
  const before = {
    revision: view.revisionId,
    tabDigest: view.tabDigest,
    notationDigest: view.notationDigest,
    tabEvents: view.tabPayload.events.length,
    notationEvents: view.notationPayload.measures.reduce((n, m) => n + m.events.length, 0),
    indexed: view.displayIndex.size,
    seekTargets: view.seekIndex.size,
  };

  view.seekTo("ev-1");
  view.selectEvent("ev-2");
  view.applyPlayhead({ active_event_ids: ["ev-3"] });
  view.seekTo("ev-3");
  view.selectEvent(null);
  view.applyPlayhead({ active_event_ids: [] });

  assert.deepEqual(
    {
      revision: view.revisionId,
      tabDigest: view.tabDigest,
      notationDigest: view.notationDigest,
      tabEvents: view.tabPayload.events.length,
      notationEvents: view.notationPayload.measures.reduce((n, m) => n + m.events.length, 0),
      indexed: view.displayIndex.size,
      seekTargets: view.seekIndex.size,
    },
    before,
  );
});

test("navigation does not mutate the loaded projections", async () => {
  const { view } = await ready();
  const snapshot = JSON.stringify({ tab: view.tabPayload, notation: view.notationPayload });
  view.seekTo("ev-2");
  view.selectEvent("ev-1");
  view.applyActiveEventIds(["ev-3"]);
  assert.equal(
    JSON.stringify({ tab: view.tabPayload, notation: view.notationPayload }),
    snapshot,
  );
});

test("selection and seek state do not survive a reload", async () => {
  const { view } = await ready();
  view.seekTo("ev-1");
  view.selectEvent("ev-2");
  await view.load(DEMO);
  assert.equal(view.selectedEventId, null);
  assert.equal(view.lastSeekTick, null);
  assert.equal(view.lastSeekEventId, null);
});

test("navigation state is reported by diagnostics without becoming musical", async () => {
  const { view } = await ready();
  view.seekTo("ev-2");
  view.selectEvent("ev-1");
  const diagnostics = view.diagnostics();
  assert.equal(diagnostics.selectedEventId, "ev-1");
  assert.equal(diagnostics.lastSeekEventId, "ev-2");
  assert.equal(diagnostics.canonicalRevisionId, REVISION.revision_id);
  // Selection is not activity.
  assert.deepEqual(diagnostics.activeEventIds, []);
});

test("no timing arithmetic reaches the navigation path", () => {
  const code = readFileSync(repoUrl("../score-view.js"), "utf-8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
  for (const forbidden of ["Date.now", "performance.now", "position_tick", "setInterval"]) {
    assert.equal(code.includes(forbidden), false, `must not use ${forbidden}`);
  }
  // Seek positions are read from the index, never computed.
  assert.match(code, /seekTickFor\(canonicalEventId\)/);
});

test("active, selected, and guided can all differ simultaneously", async () => {
  const { view, state } = await ready();
  view.applyPlayhead({ active_event_ids: ["ev-1"] });
  view.selectEvent("ev-2");
  view.applyGuidedEventIds(["ev-3"]);

  assert.deepEqual(view.activeEventIds, ["ev-1"]);
  assert.equal(view.selectedEventId, "ev-2");
  assert.deepEqual(view.guidedEventIds, ["ev-3"]);
  assert.deepEqual(state.tab.active, ["ev-1"]);
  assert.equal(state.tab.selected, "ev-2");
  assert.deepEqual(state.tab.guided, ["ev-3"]);
  assert.deepEqual(state.notation.active, ["ev-1"]);
  assert.equal(state.notation.selected, "ev-2");
  assert.deepEqual(state.notation.guided, ["ev-3"]);
});

test("guidance never writes the Teaching Timeline active set", async () => {
  const { view, state } = await ready();
  view.applyPlayhead({ active_event_ids: ["ev-1"] });
  view.applyGuidance({
    items: [{ canonical_event_id: "ev-3" }],
    next_action: { action_type: "repeat" },
    guidance_digest: "sha256:test",
  });
  assert.deepEqual(view.activeEventIds, ["ev-1"]);
  assert.deepEqual(state.tab.active, ["ev-1"]);
  assert.deepEqual(view.guidedEventIds, ["ev-3"]);
});

test("guidance does not mutate TAB or notation digests", async () => {
  const { view } = await ready();
  const tab = view.tabDigest;
  const notation = view.notationDigest;
  const revision = view.revisionId;
  view.applyGuidance({
    items: [{ canonical_event_id: "ev-2" }],
    next_action: { action_type: "slow_down", target_rate: 0.75 },
  });
  assert.equal(view.tabDigest, tab);
  assert.equal(view.notationDigest, notation);
  assert.equal(view.revisionId, revision);
});

test("unrenderable guidance is not moved onto a neighbouring event", async () => {
  const { view, state } = await ready();
  view.applyGuidedEventIds(["ev-ghost"]);
  assert.deepEqual(view.guidedEventIds, ["ev-ghost"]);
  assert.deepEqual(state.tab.guided, []);
  assert.deepEqual(state.notation.guided, []);
});

// --- sticky channels survive a mount ----------------------------------------

test("guidance and selection are replayed onto a view that mounts afterwards", async () => {
  // The active set repairs itself, because the playhead republishes constantly.
  // Guidance and selection are applied once and would otherwise stay missing on
  // a view that mounted after them, with nothing to correct it later.
  const { view, state } = await ready();
  view.applyGuidedEventIds(["ev-1"]);
  view.selectEvent("ev-2");

  // A view goes down and is remounted, as a future remount path would do.
  view.views.tab.mounted = false;
  state.tab.guided = [];
  state.tab.selected = null;

  view._mount("tab", {});

  assert.deepEqual(state.tab.guided, ["ev-1"]);
  assert.equal(state.tab.selected, "ev-2");
});

test("replay writes nothing when no sticky channel is set", async () => {
  const { view, state } = await ready();
  view.views.tab.mounted = false;
  state.tab.guided = [];
  state.tab.selected = null;

  view._mount("tab", {});

  assert.deepEqual(state.tab.guided, []);
  assert.equal(state.tab.selected, null);
});

test("replay never revives the active set, which has its own authority", async () => {
  // Activity comes from the playhead. A remount must not re-assert a stale
  // active set the timeline may since have changed.
  const { view, state } = await ready();
  view.applyActiveEventIds(["ev-3"]);
  view.views.tab.mounted = false;
  state.tab.active = [];

  view._mount("tab", {});

  assert.deepEqual(state.tab.active, []);
});
