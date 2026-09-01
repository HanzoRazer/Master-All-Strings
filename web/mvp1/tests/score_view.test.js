import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  SCORE_ERROR,
  SCORE_STATUS,
  SCORE_VIEW_FOLLOWER_ID,
  ScoreViewCoordinator,
  assertRevisionAgreement,
  buildDisplayIndex,
  buildSeekIndex,
} from "../score-view.js";
import { TeachingTimeline } from "../teaching-timeline.js";
import { Transport } from "../transport.js";

const repoUrl = (path) => fileURLToPath(new URL(path, import.meta.url));
const load = (path) => JSON.parse(readFileSync(repoUrl(path), "utf-8"));

const DEMO = "half_steps_one_string";
const REVISION = load(`../projections/${DEMO}/canonical_revision.json`);
const TAB = load(`../projections/${DEMO}/tab.json`);
const NOTATION = load(`../projections/${DEMO}/notation.json`);
const CONTEXT = load(`../projections/${DEMO}.json`);

/** A loader over the real exported artifacts, with optional overrides. */
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
    const value = files[path];
    if (value instanceof Error) throw value;
    return structuredClone(value);
  };
}

/** Renderers that record calls instead of touching a DOM. */
function fakeRenderers(failures = {}) {
  const calls = { tab: [], notation: [] };
  const make = (name) => ({
    mount: (container, payload, options) => {
      if (failures[`${name}Mount`]) throw new Error(`${name} mount exploded`);
      return { name, payload, options };
    },
    applyActive: (root, ids) => {
      if (failures[`${name}Apply`]) throw new Error(`${name} apply exploded`);
      calls[name].push([...ids]);
      return [...ids];
    },
    applyGuidance: (root, ids) => [...ids],
  });
  return { renderers: { tab: make("tab"), notation: make("notation") }, calls };
}

function coordinator(options = {}) {
  const { failures = {}, overrides = {}, ...rest } = options;
  const { renderers, calls } = fakeRenderers(failures);
  const view = new ScoreViewCoordinator({
    loadJson: loaderFor(overrides),
    renderers,
    containers: { tab: {}, notation: {} },
    ...rest,
  });
  return { view, calls };
}

// --- revision agreement ------------------------------------------------------

test("matching revision ids load successfully", async () => {
  const { view } = coordinator();
  const result = await view.load(DEMO);
  assert.equal(result.ok, true);
  assert.equal(view.status, SCORE_STATUS.ready);
  assert.equal(view.revisionId, REVISION.revision_id);
  assert.equal(view.views.tab.mounted, true);
  assert.equal(view.views.notation.mounted, true);
});

test("a tab citing another revision fails locally", async () => {
  const foreign = structuredClone(TAB);
  foreign.canonical_revision_id = "rev-somewhere-else";
  foreign.payload.canonical_revision_id = "rev-somewhere-else";
  const { view } = coordinator({
    overrides: { [`projections/${DEMO}/tab.json`]: foreign },
  });

  const result = await view.load(DEMO);
  assert.equal(result.ok, false);
  assert.equal(result.reason, SCORE_ERROR.revisionMismatch);
  assert.equal(result.disagreed, "tab");
  assert.equal(view.status, SCORE_STATUS.unavailable);
});

test("a notation citing another revision fails locally", async () => {
  const foreign = structuredClone(NOTATION);
  foreign.canonical_revision_id = "rev-somewhere-else";
  foreign.payload.canonical_revision_id = "rev-somewhere-else";
  const { view } = coordinator({
    overrides: { [`projections/${DEMO}/notation.json`]: foreign },
  });

  const result = await view.load(DEMO);
  assert.equal(result.reason, SCORE_ERROR.revisionMismatch);
  assert.equal(result.disagreed, "notation");
});

test("an envelope agreeing while its payload disagrees is still refused", async () => {
  // The subtle case: the citation on the outside looks right.
  const sneaky = structuredClone(TAB);
  sneaky.payload.canonical_revision_id = "rev-somewhere-else";
  const { view } = coordinator({ overrides: { [`projections/${DEMO}/tab.json`]: sneaky } });
  assert.equal((await view.load(DEMO)).reason, SCORE_ERROR.revisionMismatch);
});

test("nothing is mounted when revisions disagree", async () => {
  const foreign = structuredClone(TAB);
  foreign.canonical_revision_id = "rev-x";
  foreign.payload.canonical_revision_id = "rev-x";
  const { view, calls } = coordinator({
    overrides: { [`projections/${DEMO}/tab.json`]: foreign },
  });
  await view.load(DEMO);
  assert.equal(view.views.tab.mounted, false);
  assert.equal(view.views.notation.mounted, false);
  assert.deepEqual(calls.notation, []);
});

test("a missing artifact degrades rather than throwing", async () => {
  const { view } = coordinator({
    overrides: { [`projections/${DEMO}/tab.json`]: new Error("404") },
  });
  const result = await view.load(DEMO);
  assert.equal(result.ok, false);
  assert.equal(result.reason, SCORE_ERROR.loadFailed);
  assert.equal(view.status, SCORE_STATUS.unavailable);
});

test("a missing presentation context still loads the score", async () => {
  // Lanes and the tempo label are optional; the music is not.
  const { view } = coordinator({
    overrides: { [`projections/${DEMO}.json`]: new Error("404") },
  });
  assert.equal((await view.load(DEMO)).ok, true);
});

test("assertRevisionAgreement reports a missing revision distinctly", () => {
  const result = assertRevisionAgreement(null, TAB, NOTATION);
  assert.equal(result.ok, false);
  assert.equal(result.reason, "missing_canonical_revision");
});

// --- one follower, fanned out ------------------------------------------------

test("one Teaching Timeline follower fans the same ids to both views", async () => {
  const { view, calls } = coordinator();
  await view.load(DEMO);

  const applied = view.applyPlayhead({ active_event_ids: ["ev-2", "ev-3"] });
  assert.deepEqual(applied.tab, ["ev-2", "ev-3"]);
  assert.deepEqual(applied.notation, ["ev-2", "ev-3"]);
  assert.deepEqual(calls.tab.at(-1), calls.notation.at(-1));
});

test("the coordinator registers exactly one follower", async () => {
  const { view } = coordinator();
  await view.load(DEMO);

  const timeline = new TeachingTimeline({ transport: new Transport({ now: () => 0 }) });
  timeline.addFollower(view.follower());
  assert.deepEqual(timeline.diagnostics().followers, [SCORE_VIEW_FOLLOWER_ID]);
});

test("the follower forwards the playhead's ids verbatim", async () => {
  const { view, calls } = coordinator();
  await view.load(DEMO);
  view.follower().onPlayhead({ active_event_ids: ["ev-1"], position_tick: 99999 });
  assert.deepEqual(calls.tab.at(-1), ["ev-1"]);
});

test("an empty active set is forwarded, not skipped", async () => {
  const { view, calls } = coordinator();
  await view.load(DEMO);
  view.applyActiveEventIds(["ev-1"]);
  view.applyActiveEventIds([]);
  assert.deepEqual(calls.tab.at(-1), []);
  assert.deepEqual(calls.notation.at(-1), []);
});

test("a playhead with no active ids clears rather than retaining the last set", async () => {
  const { view } = coordinator();
  await view.load(DEMO);
  view.applyPlayhead({ active_event_ids: ["ev-1"] });
  view.applyPlayhead({});
  assert.deepEqual(view.activeEventIds, []);
});

test("a timeline error clears highlighting instead of freezing it", async () => {
  const { view, calls } = coordinator();
  await view.load(DEMO);
  view.applyActiveEventIds(["ev-1"]);
  view.follower().onError(new Error("boom"));
  assert.deepEqual(calls.tab.at(-1), []);
});

// --- activity comes only from the playhead -----------------------------------

test("no score-view code derives activity from transport time", () => {
  const code = readFileSync(repoUrl("../score-view.js"), "utf-8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
  for (const forbidden of [
    "setInterval",
    "setTimeout",
    "requestAnimationFrame",
    "Date.now",
    "performance.now",
    "position_tick",
    "position_seconds",
    "currentTime",
    "ticks_per_quarter",
    "microseconds_per_quarter",
  ]) {
    assert.equal(code.includes(forbidden), false, `score-view.js must not use ${forbidden}`);
  }
});

test("position and repetition on the playhead are ignored entirely", async () => {
  const { view, calls } = coordinator();
  await view.load(DEMO);
  // A playhead deep into the lesson, with nothing active. A coordinator that
  // consulted position would light something here.
  view.applyPlayhead({ position_tick: 2400, repetition_index: 3, active_event_ids: [] });
  assert.deepEqual(calls.tab.at(-1), []);
  assert.deepEqual(view.activeEventIds, []);
});

test("the seek index does not participate in active state", async () => {
  const { view } = coordinator();
  await view.load(DEMO);
  // Every event has a seek target...
  assert.ok(view.seekTickFor("ev-1") !== null);
  // ...and none of them is active until the playhead says so.
  assert.deepEqual(view.activeEventIds, []);
  view.applyActiveEventIds(["ev-1"]);
  assert.deepEqual(view.activeEventIds, ["ev-1"]);
  // Seek targets are unchanged by activity.
  assert.equal(view.seekTickFor("ev-1"), TAB.payload.events[0].start_tick);
});

test("an active id absent from the projection is still forwarded unchanged", async () => {
  // The coordinator does not filter the playhead's answer; renderers ignore ids
  // they do not have. Filtering here would be the coordinator overruling the
  // timing authority about what is active.
  const { view, calls } = coordinator();
  await view.load(DEMO);
  view.applyActiveEventIds(["ev-not-here"]);
  assert.deepEqual(calls.tab.at(-1), ["ev-not-here"]);
});

// --- indices -----------------------------------------------------------------

test("the display index is keyed by canonical event id", () => {
  const index = buildDisplayIndex(TAB.payload, NOTATION.payload);
  for (const event of TAB.payload.events) {
    assert.ok(index.has(event.canonical_event_id));
  }
});

test("the display index joins both views on the same key", () => {
  const index = buildDisplayIndex(TAB.payload, NOTATION.payload);
  const entry = index.get("ev-1");
  assert.equal(entry.tab.status, TAB.payload.events[0].status);
  assert.equal(entry.notation.displayPitch, NOTATION.payload.measures[0].events[0].display_pitch);
});

test("the display index carries no timing", () => {
  const index = buildDisplayIndex(TAB.payload, NOTATION.payload);
  const entry = index.get("ev-1");
  assert.equal("startTick" in entry.tab, false);
  assert.equal("start_tick" in entry.tab, false);
  assert.equal("startTick" in (entry.notation ?? {}), false);
});

test("the seek index carries only ticks", () => {
  const index = buildSeekIndex(TAB.payload, NOTATION.payload);
  for (const [, tick] of index) assert.equal(typeof tick, "number");
});

test("the seek index agrees with the projections it was built from", () => {
  const index = buildSeekIndex(TAB.payload, NOTATION.payload);
  for (const event of TAB.payload.events) {
    assert.equal(index.get(event.canonical_event_id), event.start_tick);
  }
});

test("derived rests are absent from both indices, having no identity", () => {
  const rest = load("../../../resources/projections/examples/global_rest_notation.json");
  const display = buildDisplayIndex({ events: [] }, rest);
  const seek = buildSeekIndex({ events: [] }, rest);
  assert.equal(display.has(null), false);
  assert.equal(seek.has(null), false);
  assert.equal(display.size, 2);
  assert.equal(seek.size, 2);
});

test("shared event ids are those both views can depict", async () => {
  const { view } = coordinator();
  await view.load(DEMO);
  const shared = view.sharedEventIds();
  assert.ok(shared.length > 0);
  for (const id of shared) {
    assert.ok(view.displayFor(id).tab);
    assert.ok(view.displayFor(id).notation);
  }
});

test("an unknown id has neither display nor seek target", async () => {
  const { view } = coordinator();
  await view.load(DEMO);
  assert.equal(view.displayFor("nope"), null);
  assert.equal(view.seekTickFor("nope"), null);
});

// --- failure isolation -------------------------------------------------------

test("a TAB mount failure does not suppress notation", async () => {
  const { view, calls } = coordinator({ failures: { tabMount: true } });
  const result = await view.load(DEMO);

  assert.equal(result.ok, true);
  assert.equal(view.views.tab.mounted, false);
  assert.match(view.views.tab.error, /tab mount exploded/);
  assert.equal(view.views.notation.mounted, true);

  view.applyActiveEventIds(["ev-1"]);
  assert.deepEqual(calls.notation.at(-1), ["ev-1"]);
});

test("a notation mount failure does not suppress TAB", async () => {
  const { view, calls } = coordinator({ failures: { notationMount: true } });
  const result = await view.load(DEMO);

  assert.equal(result.ok, true);
  assert.equal(view.views.notation.mounted, false);
  assert.equal(view.views.tab.mounted, true);

  view.applyActiveEventIds(["ev-1"]);
  assert.deepEqual(calls.tab.at(-1), ["ev-1"]);
});

test("a TAB highlight failure retires only TAB", async () => {
  const { view, calls } = coordinator({ failures: { tabApply: true } });
  await view.load(DEMO);
  view.applyActiveEventIds(["ev-1"]);

  assert.equal(view.views.tab.mounted, false);
  assert.match(view.views.tab.error, /tab apply exploded/);
  assert.equal(view.views.notation.mounted, true);
  assert.deepEqual(calls.notation.at(-1), ["ev-1"]);

  // And the surviving view keeps updating afterwards.
  view.applyActiveEventIds(["ev-2"]);
  assert.deepEqual(calls.notation.at(-1), ["ev-2"]);
});

test("a notation highlight failure retires only notation", async () => {
  const { view, calls } = coordinator({ failures: { notationApply: true } });
  await view.load(DEMO);
  view.applyActiveEventIds(["ev-1"]);

  assert.equal(view.views.notation.mounted, false);
  assert.equal(view.views.tab.mounted, true);
  view.applyActiveEventIds(["ev-2"]);
  assert.deepEqual(calls.tab.at(-1), ["ev-2"]);
});

test("both renderers failing marks the score unavailable, not the lesson", async () => {
  const { view } = coordinator({ failures: { tabMount: true, notationMount: true } });
  const result = await view.load(DEMO);
  assert.equal(result.ok, false);
  assert.equal(result.reason, SCORE_ERROR.renderFailed);
  assert.equal(view.status, SCORE_STATUS.unavailable);
  // The revision still resolved; only presentation failed.
  assert.equal(view.revisionId, REVISION.revision_id);
});

// --- lifecycle and diagnostics ----------------------------------------------

test("clearing releases the score without disturbing status reporting", async () => {
  const { view } = coordinator();
  await view.load(DEMO);
  view.follower().onClear();
  assert.equal(view.status, SCORE_STATUS.idle);
  assert.equal(view.revisionId, null);
  assert.equal(view.displayIndex.size, 0);
});

test("loading a second lesson does not retain the first", async () => {
  const { view } = coordinator();
  await view.load(DEMO);
  view.applyActiveEventIds(["ev-1"]);
  const stale = new Error("404");
  const second = new ScoreViewCoordinator({
    loadJson: loaderFor({ [`projections/${DEMO}/tab.json`]: stale }),
    renderers: fakeRenderers().renderers,
    containers: { tab: {}, notation: {} },
  });
  await second.load(DEMO);
  assert.equal(second.activeEventIds.length, 0);
  assert.equal(second.displayIndex.size, 0);
});

test("diagnostics report state and change none of it", async () => {
  const { view } = coordinator();
  await view.load(DEMO);
  view.applyActiveEventIds(["ev-2"]);

  const before = view.diagnostics();
  assert.equal(before.canonicalRevisionId, REVISION.revision_id);
  assert.equal(before.tabLoaded, true);
  assert.equal(before.notationLoaded, true);
  assert.equal(before.tabDigest, TAB.digest);
  assert.equal(before.notationDigest, NOTATION.digest);
  assert.deepEqual(before.activeEventIds, ["ev-2"]);

  // Mutating the snapshot must not reach the coordinator.
  before.activeEventIds.push("ev-9");
  assert.deepEqual(view.diagnostics().activeEventIds, ["ev-2"]);
});

test("diagnostics report a failed view without hiding it", async () => {
  const { view } = coordinator({ failures: { tabMount: true } });
  await view.load(DEMO);
  const diagnostics = view.diagnostics();
  assert.equal(diagnostics.tabLoaded, false);
  assert.match(diagnostics.tabError, /exploded/);
  assert.equal(diagnostics.notationLoaded, true);
});

test("a status callback observes transitions", async () => {
  const seen = [];
  const { view } = coordinator({ onStatus: (status, reason) => seen.push([status, reason]) });
  await view.load(DEMO);
  assert.deepEqual(seen.at(-1), [SCORE_STATUS.ready, null]);
});

test("guidance fan-out does not rewrite the active set", async () => {
  const { view, calls } = coordinator();
  await view.load(DEMO);
  view.applyActiveEventIds(["ev-1"]);
  view.applyGuidedEventIds(["ev-3"]);
  assert.deepEqual(view.activeEventIds, ["ev-1"]);
  assert.deepEqual(view.guidedEventIds, ["ev-3"]);
  assert.deepEqual(calls.tab.at(-1), ["ev-1"]);
});
