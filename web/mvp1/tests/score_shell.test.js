import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  buildScoreDiagnostics,
  createFretboardSelectionHandler,
  createScoreSeekHandler,
  presentTeachingGuidance,
} from "../score-shell.js";
import { createGuidanceDispositionHandler } from "../guided_disposition.js";
import { createGuidedApplyHandler } from "../guided-action-executor.js";
import { ScoreViewCoordinator } from "../score-view.js";
import { NOTATION_LIMITATIONS } from "../notation-view.js";
import { TeachingTimeline, secondsAtTick } from "../teaching-timeline.js";
import { Transport } from "../transport.js";

const repoUrl = (path) => fileURLToPath(new URL(path, import.meta.url));
const load = (path) => JSON.parse(readFileSync(repoUrl(path), "utf-8"));

const DEMO = "half_steps_one_string";
const REVISION = load(`../projections/${DEMO}/canonical_revision.json`);
const TAB = load(`../projections/${DEMO}/tab.json`);
const NOTATION = load(`../projections/${DEMO}/notation.json`);
const CONTEXT = load(`../projections/${DEMO}.json`);
const ANCHORS = CONTEXT.timeline_anchors;

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

function fakeRenderers(failures = {}) {
  const state = {
    tab: { active: [], selected: null, guided: [] },
    notation: { active: [], selected: null, guided: [] },
  };
  const make = (name) => ({
    mount: () => {
      if (failures[`${name}Mount`]) throw new Error(`${name} mount failed`);
      return { name };
    },
    applyActive: (root, ids) => {
      state[name].active = [...ids];
      return [...ids];
    },
    applySelection: (root, id) => {
      state[name].selected = id;
      return id;
    },
    applyGuidance: (root, ids) => {
      state[name].guided = [...ids];
      return [...ids];
    },
  });
  return { renderers: { tab: make("tab"), notation: make("notation") }, state };
}

async function harness(options = {}) {
  const { failures = {}, overrides = {} } = options;
  let now = 0;
  const transport = new Transport({ now: () => now });
  const timeline = new TeachingTimeline({ transport });
  transport.setDuration(4.5);
  timeline.setLesson({ lessonId: DEMO, anchors: ANCHORS });

  const { renderers, state } = fakeRenderers(failures);
  const seeks = [];
  const coordinator = new ScoreViewCoordinator({
    loadJson: loaderFor(overrides),
    renderers,
    containers: { tab: {}, notation: {} },
  });
  const scoreSeek = createScoreSeekHandler({
    timeline,
    transport,
    secondsAtTick,
    onSeek: (id, tick, seconds) => seeks.push([id, tick, seconds]),
  });
  coordinator._onSeek = (id, tick) => scoreSeek(id, tick);
  await coordinator.load(DEMO);
  timeline.addFollower(coordinator.follower());

  return { transport, timeline, coordinator, state, seeks, scoreSeek, advance: (ms) => (now += ms) };
}

// --- shell seek path ---------------------------------------------------------

test("the shell converts a tick through secondsAtTick and seeks the transport", async () => {
  const { transport, coordinator, seeks } = await harness();
  const event = TAB.payload.events[2];

  const seconds = coordinator.seekTo(event.canonical_event_id);
  assert.equal(seconds, event.start_tick);

  const expected = secondsAtTick(ANCHORS, event.start_tick);
  assert.equal(seeks.at(-1)[2], expected);
  assert.equal(transport.positionSeconds(), expected);
});

test("the coordinator hands over a tick, never seconds", async () => {
  const { coordinator, seeks } = await harness();
  const event = TAB.payload.events[1];
  coordinator.seekTo(event.canonical_event_id);

  const [, tick, seconds] = seeks.at(-1);
  assert.equal(tick, event.start_tick);
  assert.notEqual(tick, seconds);
  assert.equal(coordinator.lastSeekTick, event.start_tick);
});

test("score-view.js still contains no unit conversion", () => {
  const code = readFileSync(repoUrl("../score-view.js"), "utf-8");
  assert.doesNotMatch(code, /secondsAtTick/);
  assert.doesNotMatch(code, /tickAtSeconds/);
});

test("a seek with no anchors does nothing rather than guessing", () => {
  const transport = new Transport({ now: () => 0 });
  transport.setDuration(4.5);
  const timeline = new TeachingTimeline({ transport });
  const seek = createScoreSeekHandler({ timeline, transport, secondsAtTick });
  assert.equal(seek("ev-1", 480), null);
  assert.equal(transport.positionSeconds(), 0);
});

test("a non-finite tick is refused", async () => {
  const { scoreSeek, transport } = await harness();
  assert.equal(scoreSeek("ev-1", Number.NaN), null);
  assert.equal(transport.positionSeconds(), 0);
});

// --- fretboard selection ----------------------------------------------------

test("a fretboard click forwards its canonical id to selectEvent", async () => {
  const { coordinator, state } = await harness();
  const select = createFretboardSelectionHandler({ coordinator });

  const noteElement = { dataset: { eventId: "ev-2" } };
  const id = select({ closest: () => noteElement });

  assert.equal(id, "ev-2");
  assert.equal(coordinator.selectedEventId, "ev-2");
  assert.equal(state.tab.selected, "ev-2");
  assert.equal(state.notation.selected, "ev-2");
});

test("a click away from a note selects nothing", async () => {
  const { coordinator } = await harness();
  const select = createFretboardSelectionHandler({ coordinator });
  assert.equal(select({ closest: () => null }), null);
  assert.equal(coordinator.selectedEventId, null);
});

test("selection does not alter the active set", async () => {
  const { coordinator, state } = await harness();
  const select = createFretboardSelectionHandler({ coordinator });
  coordinator.applyActiveEventIds(["ev-1"]);
  select({ closest: () => ({ dataset: { eventId: "ev-3" } }) });

  assert.deepEqual(coordinator.activeEventIds, ["ev-1"]);
  assert.deepEqual(state.tab.active, ["ev-1"]);
  assert.equal(state.tab.selected, "ev-3");
});

test("a playhead update does not clear the selection", async () => {
  const { coordinator, state } = await harness();
  coordinator.selectEvent("ev-2");
  coordinator.applyPlayhead({ active_event_ids: ["ev-1"] });
  assert.equal(coordinator.selectedEventId, "ev-2");
  assert.equal(state.tab.selected, "ev-2");
  assert.deepEqual(state.tab.active, ["ev-1"]);
});

// --- diagnostics -------------------------------------------------------------

function diagnosticsFor(coordinator, extra = {}) {
  return buildScoreDiagnostics({
    coordinator,
    limitations: NOTATION_LIMITATIONS,
    ...extra,
  });
}

test("diagnostics expose the required score fields", async () => {
  const { coordinator } = await harness();
  const diagnostics = diagnosticsFor(coordinator, {
    loopRange: { start_tick: 0, end_tick: 1920 },
    repetitionIndex: 2,
  });

  for (const field of [
    "status",
    "canonicalRevisionId",
    "tabLoaded",
    "notationLoaded",
    "activeEventIds",
    "tabActiveEventIds",
    "notationActiveEventIds",
    "selectedEventId",
    "tabDigest",
    "notationDigest",
    "loopRange",
    "repetitionIndex",
    "tabError",
    "notationError",
    "limitations",
  ]) {
    assert.ok(field in diagnostics, `diagnostics missing ${field}`);
  }
  assert.equal(diagnostics.canonicalRevisionId, REVISION.revision_id);
  assert.equal(diagnostics.tabDigest, TAB.digest);
  assert.equal(diagnostics.repetitionIndex, 2);
});

test("diagnostics report active and selected simultaneously", async () => {
  const { coordinator } = await harness();
  coordinator.applyPlayhead({ active_event_ids: ["ev-2"] });
  coordinator.selectEvent("ev-1");

  const diagnostics = diagnosticsFor(coordinator);
  assert.deepEqual(diagnostics.activeEventIds, ["ev-2"]);
  assert.equal(diagnostics.selectedEventId, "ev-1");
  assert.deepEqual(diagnostics.tabActiveEventIds, ["ev-2"]);
  assert.deepEqual(diagnostics.notationActiveEventIds, ["ev-2"]);
});

test("diagnostics report the notation limitations rather than hiding them", async () => {
  const { coordinator } = await harness();
  const diagnostics = diagnosticsFor(coordinator);
  assert.ok(diagnostics.limitations.includes("MVP2C_NOTATION_REGISTER_LIMITATION"));
  assert.ok(diagnostics.limitations.includes("MVP2C_NOTATION_ACCIDENTAL_LIMITATION"));
});

test("mutating a diagnostics snapshot cannot reach product state", async () => {
  const { coordinator, state } = await harness();
  coordinator.applyPlayhead({ active_event_ids: ["ev-1"] });
  coordinator.selectEvent("ev-2");

  const diagnostics = diagnosticsFor(coordinator, { loopRange: { start_tick: 0, end_tick: 960 } });
  diagnostics.activeEventIds.push("ev-9");
  diagnostics.tabActiveEventIds.push("ev-9");
  diagnostics.selectedEventId = "ev-tampered";
  diagnostics.limitations.push("INVENTED");
  diagnostics.loopRange.end_tick = 1;

  assert.deepEqual(coordinator.activeEventIds, ["ev-1"]);
  assert.equal(coordinator.selectedEventId, "ev-2");
  assert.deepEqual(state.tab.active, ["ev-1"]);
  assert.equal(NOTATION_LIMITATIONS.includes("INVENTED"), false);
  assert.deepEqual(diagnosticsFor(coordinator).activeEventIds, ["ev-1"]);
});

test("diagnostics report what each view actually lit, not what was requested", async () => {
  const { coordinator } = await harness({ failures: { tabMount: true } });
  coordinator.applyPlayhead({ active_event_ids: ["ev-1"] });
  const diagnostics = diagnosticsFor(coordinator);

  assert.equal(diagnostics.tabLoaded, false);
  assert.deepEqual(diagnostics.tabActiveEventIds, []);
  assert.deepEqual(diagnostics.notationActiveEventIds, ["ev-1"]);
  assert.deepEqual(diagnostics.activeEventIds, ["ev-1"]);
});

// --- coexistence -------------------------------------------------------------

test("exactly one follower is registered for both score views", async () => {
  const { timeline } = await harness();
  const followers = timeline.diagnostics().followers;
  assert.deepEqual(followers, ["score-views"]);
  assert.equal(followers.length, 1);
});

test("score views follow play and pause through the shared transport", async () => {
  const { transport, timeline, coordinator, state, advance } = await harness();
  transport.play();
  advance(1000);
  timeline.setActiveEventIds(["ev-2"]);
  timeline.publish("frame", 1000);
  assert.deepEqual(state.tab.active, ["ev-2"]);
  assert.deepEqual(state.notation.active, ["ev-2"]);

  transport.pause();
  timeline.setActiveEventIds(["ev-2"]);
  timeline.publish("pause", 1000);
  assert.deepEqual(coordinator.activeEventIds, ["ev-2"]);
});

test("a rate change leaves projection identity untouched", async () => {
  const { transport, timeline, coordinator } = await harness();
  const before = snapshotIdentity(coordinator);

  for (const rate of [0.5, 0.75, 1, 1.5]) {
    transport.setRate(rate);
    timeline.setActiveEventIds(["ev-1"]);
    timeline.publish("rate", 0);
  }
  assert.deepEqual(snapshotIdentity(coordinator), before);
});

test("three or more loop repetitions leave projection identity untouched", async () => {
  const { transport, timeline, coordinator, advance } = await harness();
  const before = snapshotIdentity(coordinator);

  transport.setLoop({ startSeconds: 0, endSeconds: 1.5, enabled: true });
  transport.play();
  for (let repetition = 0; repetition < 4; repetition += 1) {
    advance(1600);
    transport.positionSeconds();
    timeline.setActiveEventIds(["ev-1"]);
    timeline.publish("frame", repetition * 1600);
  }

  // The loop really did run, so the invariance below is about a lesson that
  // repeated rather than one that sat still.
  assert.ok(transport.repetitionCount >= 3, `only ${transport.repetitionCount} repetitions`);
  assert.deepEqual(snapshotIdentity(coordinator), before);
});

function snapshotIdentity(coordinator) {
  return {
    revision: coordinator.revisionId,
    tabDigest: coordinator.tabDigest,
    notationDigest: coordinator.notationDigest,
    tabEvents: coordinator.tabPayload.events.length,
    notationEvents: coordinator.notationPayload.measures.reduce(
      (total, measure) => total + measure.events.length,
      0,
    ),
  };
}

test("a missing TAB artifact does not prevent notation from being reached", async () => {
  // Revision agreement needs all three, so an absent TAB disables the score
  // panel -- and the failure is reported rather than thrown at the lesson.
  const { coordinator } = await harness({
    overrides: { [`projections/${DEMO}/tab.json`]: new Error("404") },
  });
  assert.equal(coordinator.status, "unavailable");
  assert.equal(coordinator.reason, "score_artifacts_unavailable");
});

test("a failed TAB renderer leaves notation live", async () => {
  const { coordinator, state } = await harness({ failures: { tabMount: true } });
  coordinator.applyPlayhead({ active_event_ids: ["ev-1"] });
  assert.equal(coordinator.views.notation.mounted, true);
  assert.deepEqual(state.notation.active, ["ev-1"]);
});

test("a failed notation renderer leaves TAB live", async () => {
  const { coordinator, state } = await harness({ failures: { notationMount: true } });
  coordinator.applyPlayhead({ active_event_ids: ["ev-1"] });
  assert.equal(coordinator.views.tab.mounted, true);
  assert.deepEqual(state.tab.active, ["ev-1"]);
});

test("a failed score view leaves the transport and timeline working", async () => {
  const { transport, timeline, coordinator, advance } = await harness({
    failures: { tabMount: true, notationMount: true },
  });
  assert.equal(coordinator.status, "unavailable");

  transport.play();
  advance(500);
  assert.ok(transport.positionSeconds() > 0);
  assert.equal(timeline.ready, true);
  assert.equal(timeline.diagnostics().playhead !== null, true);
});

// --- authority guards --------------------------------------------------------

test("score modules acquire no timing authority", () => {
  for (const file of ["score-view.js", "tab-view.js", "notation-view.js", "score-shell.js"]) {
    const code = readFileSync(repoUrl(`../${file}`), "utf-8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/(^|[^:])\/\/.*$/gm, "$1");
    for (const forbidden of [
      "microseconds_per_quarter",
      "ticks_per_quarter",
      "Date.now",
      "performance.now",
      "setInterval",
      "requestAnimationFrame",
    ]) {
      assert.equal(code.includes(forbidden), false, `${file} must not use ${forbidden}`);
    }
  }
});

test("only the shell module names the conversion seam", () => {
  const shell = readFileSync(repoUrl("../score-shell.js"), "utf-8");
  assert.match(shell, /secondsAtTick/);
  for (const file of ["score-view.js", "tab-view.js", "notation-view.js"]) {
    assert.doesNotMatch(readFileSync(repoUrl(`../${file}`), "utf-8"), /secondsAtTick/);
  }
});

test("the shell holds no score state of its own", () => {
  const code = readFileSync(repoUrl("../score-shell.js"), "utf-8");
  // Factories and a snapshot builder; no module-level mutable bindings.
  assert.doesNotMatch(code, /^let\s/m);
  assert.doesNotMatch(code, /^var\s/m);
});

test("app.js wires the score views without owning them", () => {
  const code = readFileSync(repoUrl("../app.js"), "utf-8");
  assert.match(code, /new ScoreViewCoordinator\(/);
  assert.match(code, /teachingTimeline\.addFollower\(scoreView\.follower\(\)\)/);
  assert.match(code, /createScoreSeekHandler\(/);
  assert.match(code, /createFretboardSelectionHandler\(/);
  assert.match(code, /scoreViews:/);
  // One score follower registration, not one per renderer.
  assert.equal((code.match(/scoreView\.follower\(\)/g) || []).length, 1);
  // No second conversion helper.
  assert.equal((code.match(/secondsAtTick/g) || []).length, 2);
});

test("every lesson load reaches the score views, including a lesson change", () => {
  // Regression for a defect the golden browser proof found: loadSession took an
  // optional demo id, the lesson-change handler omitted it, and switching
  // lessons left the score panel idle while every other surface reloaded. The
  // id now comes from the applied payload, so no call site can forget it.
  const code = readFileSync(repoUrl("../app.js"), "utf-8");

  assert.doesNotMatch(code, /async function loadSession\(paths,/);
  assert.match(code, /await loadScoreViews\(state\.payload\?\.demo_id/);

  // Every loadSession call site passes paths only. Counted at bracket depth so
  // an array-literal argument's own commas are not mistaken for a second one.
  for (const match of code.matchAll(/loadSession\(/g)) {
    let depth = 0;
    let topLevelCommas = 0;
    for (let i = match.index + "loadSession(".length; i < code.length; i += 1) {
      const character = code[i];
      if ("([{".includes(character)) depth += 1;
      else if (")]}".includes(character)) {
        if (depth === 0) break;
        depth -= 1;
      } else if (character === "," && depth === 0) topLevelCommas += 1;
    }
    assert.equal(topLevelCommas, 0, "a loadSession call still passes a second argument");
  }
});

test("index.html mounts the score containers and its stylesheet", () => {
  const html = readFileSync(repoUrl("../index.html"), "utf-8");
  assert.match(html, /id="tabView"/);
  assert.match(html, /id="notationView"/);
  assert.match(html, /id="scoreUnavailable"/);
  assert.match(html, /score-view\.css/);
});

test("presentTeachingGuidance fans ids without touching transport or activity", async () => {
  const { coordinator, transport, state } = await harness();
  coordinator.applyPlayhead({ active_event_ids: ["ev-1"] });
  const rate = transport.playbackRate;
  presentTeachingGuidance({
    coordinator,
    projection: {
      items: [{ canonical_event_id: "ev-3" }],
      next_action: { action_type: "slow_down", target_rate: 0.75 },
      guidance_digest: "sha256:guide",
    },
  });
  assert.deepEqual(coordinator.guidedEventIds, ["ev-3"]);
  assert.deepEqual(state.tab.guided, ["ev-3"]);
  assert.deepEqual(coordinator.activeEventIds, ["ev-1"]);
  assert.equal(transport.playbackRate, rate);
  assert.equal(transport.loop, null);
});

test("diagnostics expose guidance observationally without becoming authority", async () => {
  const { coordinator } = await harness();
  coordinator.applyGuidance({
    items: [{ canonical_event_id: "ev-2" }],
    next_action: { action_type: "isolate_passage", focus_start_tick: 960, focus_end_tick: 1920 },
    guidance_digest: "sha256:guide",
  });
  const diagnostics = buildScoreDiagnostics({
    coordinator,
    limitations: NOTATION_LIMITATIONS,
    loopRange: { enabled: false },
    repetitionIndex: 0,
  });
  assert.equal(diagnostics.guidanceStatus, "ready");
  assert.equal(diagnostics.guidanceDigest, "sha256:guide");
  assert.deepEqual(diagnostics.guidedEventIds, ["ev-2"]);
  assert.equal(diagnostics.guidanceAction, "isolate_passage");
  assert.deepEqual(diagnostics.guidanceRange, { startTick: 960, endTick: 1920 });
  diagnostics.guidedEventIds.push("ev-9");
  assert.deepEqual(coordinator.guidedEventIds, ["ev-2"]);
  assert.equal(diagnostics.tabDigest, TAB.digest);
  assert.equal(diagnostics.notationDigest, NOTATION.digest);
  assert.equal(diagnostics.canonicalRevisionId, REVISION.revision_id);
});

test("accepting a recommendation records disposition and does not mutate Transport", async () => {
  const { coordinator, transport } = await harness();
  coordinator.applyGuidance({
    items: [{ canonical_event_id: "ev-1" }],
    next_action: { action_type: "slow_down", target_rate: 0.75 },
    guidance_digest: "sha256:guide",
  });
  const digest = coordinator.diagnostics().guidanceDigest;
  const tab = coordinator.tabDigest;
  const calls = [];
  const accept = createGuidanceDispositionHandler({
    guidedSessionApi: {
      recordDisposition: async (sessionId, disposition) => {
        calls.push({ sessionId, disposition });
        return {
          session_id: sessionId,
          status: "AWAITING_ACTION",
          attempts: [
            {
              action: {
                action_disposition: disposition,
                execution_status: "PENDING",
              },
            },
          ],
          current_attempt_index: 0,
        };
      },
    },
    getSessionId: () => "session-do015-accept",
  });
  assert.equal(transport.playbackRate, 1);
  const session = await accept("ACCEPTED");
  assert.deepEqual(calls, [{ sessionId: "session-do015-accept", disposition: "ACCEPTED" }]);
  assert.equal(session.attempts[0].action.action_disposition, "ACCEPTED");
  assert.equal(session.attempts[0].action.execution_status, "PENDING");
  assert.equal(transport.playbackRate, 1);
  assert.equal(transport.loop, null);
  assert.equal(coordinator.diagnostics().guidanceDigest, digest);
  assert.equal(coordinator.tabDigest, tab);
});

test("accepting isolate does not set a Transport loop", async () => {
  const { coordinator, transport } = await harness();
  const action = {
    action_type: "isolate_passage",
    focus_start_tick: 960,
    focus_end_tick: 1920,
    message_key: "action.isolate_passage",
  };
  coordinator.applyGuidance({
    items: [{ canonical_event_id: "ev-3" }],
    next_action: action,
    guidance_digest: "sha256:guide",
  });
  const accept = createGuidanceDispositionHandler({
    guidedSessionApi: {
      recordDisposition: async () => ({
        session_id: "session-do015-isolate",
        status: "AWAITING_ACTION",
        attempts: [
          {
            action: {
              recommended_action: action,
              action_disposition: "ACCEPTED",
              execution_status: "PENDING",
            },
          },
        ],
        current_attempt_index: 0,
      }),
    },
    getSessionId: () => "session-do015-isolate",
  });
  await accept("ACCEPTED");
  assert.equal(transport.loop, null);
  assert.equal(transport.playbackRate, 1);
  assert.equal(coordinator.diagnostics().guidanceAction, "isolate_passage");
});

test("applying an accepted recommendation mutates Transport and preserves score identity", async () => {
  const { coordinator, transport } = await harness();
  coordinator.applyGuidance({
    items: [{ canonical_event_id: "ev-1" }],
    next_action: { action_type: "slow_down", target_rate: 0.5 },
    guidance_digest: "sha256:guide",
  });
  const digest = coordinator.diagnostics().guidanceDigest;
  const tab = coordinator.tabDigest;
  const notation = coordinator.notationDigest;
  const revision = coordinator.revisionId;
  let session = {
    session_id: "session-do015-apply",
    status: "AWAITING_ACTION",
    canonical_revision_id: revision,
    current_attempt_index: 0,
    attempts: [
      {
        attempt_id: "attempt-0",
        performance_session_id: "performance-session-0",
        evaluation_digest: "sha256:eval",
        guidance_digest: digest,
        action: {
          recommended_action: { action_type: "slow_down", target_rate: 0.5 },
          action_disposition: "ACCEPTED",
          execution_status: "PENDING",
        },
      },
    ],
  };
  const apply = createGuidedApplyHandler({
    getSession: () => session,
    setSession: (next) => {
      session = next;
    },
    recordExecution: async (_id, executionStatus, executedAction) => ({
      ...session,
      status: "AWAITING_ATTEMPT",
      attempts: [
        {
          ...session.attempts[0],
          action: {
            ...session.attempts[0].action,
            execution_status: executionStatus,
            executed_action: executedAction,
          },
        },
      ],
    }),
    getRuntime: () => ({ transport }),
  });
  await apply();
  assert.equal(transport.playbackRate, 0.5);
  assert.equal(session.status, "AWAITING_ATTEMPT");
  assert.equal(coordinator.diagnostics().guidanceDigest, digest);
  assert.equal(coordinator.tabDigest, tab);
  assert.equal(coordinator.notationDigest, notation);
  assert.equal(coordinator.revisionId, revision);
});
