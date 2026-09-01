import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  NOTATION_LIMITATIONS,
  STAFF_BOTTOM_STEP,
  STAFF_TOP_STEP,
  UNSPELLABLE_GLYPH,
  applyActiveEventIds,
  applyGuidedEventIds,
  applySelectedEventId,
  hasUndisplayedTempoChanges,
  initialTempoBpm,
  ledgerStepsFor,
  notationEventAt,
  notationEventIds,
  notationLayoutModel,
  parseDisplayPitch,
  renderNotationSvg,
  seekTickForEvent,
  yForStep,
} from "../notation-view.js";

const repoUrl = (path) => fileURLToPath(new URL(path, import.meta.url));
const load = (path) => JSON.parse(readFileSync(repoUrl(path), "utf-8"));

const GOLDEN = load("../projections/half_steps_one_string/notation.json").payload;
// Tempo context is the fretboard projection, which publishes Core-authored
// `tempo_bpm`. The canonical revision stores microseconds per quarter, and
// converting that in the browser is forbidden by the renderer-authority guard.
const TEMPO_CONTEXT = load("../projections/half_steps_one_string.json").projection;
const OPEN_STRINGS = load("../projections/open_strings/notation.json").payload;

const EXAMPLES = "../../../resources/projections/examples/";
const METER_CHANGE = load(`${EXAMPLES}meter_change_notation.json`);
const GLOBAL_REST = load(`${EXAMPLES}global_rest_notation.json`);
const UNSUPPORTED = load(`${EXAMPLES}unsupported_duration_notation.json`);
const TIE = load(`${EXAMPLES}unsupported_tie_notation.json`);

// --- staff structure ---------------------------------------------------------

test("the staff has five lines", () => {
  const svg = renderNotationSvg(GOLDEN, { tempoContext: TEMPO_CONTEXT });
  assert.equal(svg.match(/notation-staff-line/g).length, 5);
});

test("treble staff spans E4 to F5 as diatonic steps", () => {
  assert.equal(STAFF_BOTTOM_STEP, parseDisplayPitch("E4").step);
  assert.equal(STAFF_TOP_STEP, parseDisplayPitch("F5").step);
});

test("each measure gets a barline", () => {
  const model = notationLayoutModel(METER_CHANGE, {});
  const svg = renderNotationSvg(METER_CHANGE, {});
  assert.equal(model.measures.length, 2);
  assert.equal(svg.match(/notation-barline/g).length, 2);
});

test("a shorter measure is drawn narrower", () => {
  // 3/4 is 1440 ticks against 4/4's 1920; the bar must not be equal width.
  const model = notationLayoutModel(METER_CHANGE, {});
  assert.ok(model.measures[1].width < model.measures[0].width);
});

test("the opening time signature is printed once", () => {
  const svg = renderNotationSvg(GOLDEN, {});
  assert.equal(svg.match(/notation-meter-numerator/g).length, 1);
});

test("a meter change reprints the time signature, an unchanged meter does not", () => {
  const changed = renderNotationSvg(METER_CHANGE, {});
  assert.equal(changed.match(/notation-meter-change/g).length, 2);
  assert.doesNotMatch(renderNotationSvg(TIE, {}), /notation-meter-change/);
});

// --- notes -------------------------------------------------------------------

test("notes render a notehead", () => {
  const svg = renderNotationSvg(GOLDEN, {});
  assert.ok(svg.match(/notation-notehead/g).length >= 1);
});

test("a quarter note is filled and stemmed; a whole note is hollow and stemless", () => {
  const quarter = notationLayoutModel(GOLDEN, {}).events.find((e) => e.kind === "note");
  assert.equal(quarter.displayDuration, "quarter");
  assert.equal(quarter.hollow, false);
  assert.equal(quarter.stemmed, true);

  const whole = notationLayoutModel(TIE, {}).events.find((e) => e.kind === "note");
  assert.equal(whole.displayDuration, "whole");
  assert.equal(whole.hollow, true);
  assert.equal(whole.stemmed, false);
});

test("stems are present for stemmed notes", () => {
  assert.match(renderNotationSvg(GOLDEN, {}), /notation-stem/);
});

test("canonical event ids survive into the rendered output", () => {
  const svg = renderNotationSvg(GOLDEN, {});
  for (const id of notationEventIds(GOLDEN)) {
    assert.ok(svg.includes(`data-canonical-event-id="${id}"`));
  }
});

// --- display spelling authority (8.14) ---------------------------------------

test("an adversarial Fb4 is placed on F, not corrected to E4 from MIDI 64", () => {
  // The central no-inference case. MIDI 64 sounds E4, but Core said Fb4, and a
  // renderer that consulted the MIDI number would place it a diatonic step low
  // and drop the flat.
  const adversarial = {
    ...GLOBAL_REST,
    measures: [
      {
        ...GLOBAL_REST.measures[0],
        events: [
          {
            schema_version: "1.0.0",
            event_kind: "note",
            start_tick: 0,
            duration_ticks: 480,
            canonical_event_id: "ev-adversarial",
            midi_note: 64,
            display_pitch: "Fb4",
            display_duration: "quarter",
            derivation: null,
          },
        ],
      },
    ],
  };
  const event = notationLayoutModel(adversarial, {}).events[0];

  assert.equal(event.step, parseDisplayPitch("F4").step);
  assert.notEqual(event.step, parseDisplayPitch("E4").step);
  assert.equal(event.y, yForStep(parseDisplayPitch("F4").step));
  assert.equal(event.accidental, "b");
  assert.equal(event.accidentalGlyph, "♭");
  assert.match(renderNotationSvg(adversarial, {}), /♭/);
});

test("the module never reads midi_note, ticks, or raw tempo units", () => {
  const code = readFileSync(repoUrl("../notation-view.js"), "utf-8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
  for (const forbidden of [
    "midi_note",
    "midiNote",
    // The renderer-authority guard: the browser converts neither ticks nor tempo.
    "microseconds_per_quarter",
    "ticks_per_quarter",
  ]) {
    assert.equal(code.includes(forbidden), false, `must not reference ${forbidden}`);
  }
});

test("display pitch parses letter, accidental and octave", () => {
  assert.deepEqual(parseDisplayPitch("C#4"), {
    letter: "C",
    accidental: "#",
    octave: 4,
    step: 28,
  });
  assert.equal(parseDisplayPitch("nonsense"), null);
  assert.equal(parseDisplayPitch(null), null);
});

// --- accidentals (ruling 4) --------------------------------------------------

test("a repeated accidental in one measure is drawn every time", () => {
  // Non-inferential by decision: conventional engraving would carry the sharp
  // through the bar, making the printed glyph depend on neighbouring notes
  // rather than on this note's Core-authored spelling.
  const repeated = {
    ...GLOBAL_REST,
    measures: [
      {
        ...GLOBAL_REST.measures[0],
        events: ["ev-a", "ev-b"].map((id, index) => ({
          schema_version: "1.0.0",
          event_kind: "note",
          start_tick: index * 480,
          duration_ticks: 480,
          canonical_event_id: id,
          midi_note: 61,
          display_pitch: "C#4",
          display_duration: "quarter",
          derivation: null,
        })),
      },
    ],
  };
  const model = notationLayoutModel(repeated, {});
  assert.deepEqual(
    model.events.map((e) => e.accidentalGlyph),
    ["♯", "♯"],
  );
  assert.equal(renderNotationSvg(repeated, {}).match(/notation-accidental/g).length, 2);
});

test("a natural note carries no accidental glyph", () => {
  const model = notationLayoutModel(GOLDEN, {});
  const natural = model.events.find((e) => e.displayPitch === "E4");
  assert.equal(natural.accidentalGlyph, "");
});

test("the accidental limitation is declared rather than hidden", () => {
  assert.ok(NOTATION_LIMITATIONS.includes("MVP2C_NOTATION_ACCIDENTAL_LIMITATION"));
  assert.deepEqual(notationLayoutModel(GOLDEN, {}).limitations, NOTATION_LIMITATIONS);
});

// --- register and ledger lines (ruling 3) ------------------------------------

test("notes inside the staff need no ledger lines", () => {
  assert.deepEqual(ledgerStepsFor(parseDisplayPitch("G4").step), []);
  assert.deepEqual(ledgerStepsFor(STAFF_BOTTOM_STEP), []);
  assert.deepEqual(ledgerStepsFor(STAFF_TOP_STEP), []);
});

test("middle C sits on one ledger line below the staff", () => {
  assert.deepEqual(ledgerStepsFor(parseDisplayPitch("C4").step), [
    parseDisplayPitch("C4").step,
  ]);
});

test("a low guitar pitch needs many ledger lines, as the limitation says", () => {
  // F#1 is the corpus floor. Concert-pitch treble staff puts it ten lines down.
  const steps = ledgerStepsFor(parseDisplayPitch("F#1").step);
  assert.equal(steps.length, 10);
  assert.ok(NOTATION_LIMITATIONS.includes("MVP2C_NOTATION_REGISTER_LIMITATION"));
});

test("the real open-strings lesson renders its low notes with ledger lines", () => {
  const svg = renderNotationSvg(OPEN_STRINGS, {});
  assert.match(svg, /notation-ledger/);
});

test("the canvas grows to contain notes below the staff", () => {
  const low = notationLayoutModel(OPEN_STRINGS, {});
  const inside = notationLayoutModel(GOLDEN, {});
  assert.ok(low.height > inside.height);
});

test("ledger lines are placed on the same parity as staff lines", () => {
  for (const step of ledgerStepsFor(parseDisplayPitch("F#1").step)) {
    assert.equal((STAFF_BOTTOM_STEP - step) % 2, 0);
  }
});

// --- rests -------------------------------------------------------------------

test("a derived rest renders without a canonical event id", () => {
  const model = notationLayoutModel(GLOBAL_REST, {});
  const rest = model.events.find((e) => e.kind === "rest");
  assert.equal(rest.canonicalEventId, null);
  assert.equal(rest.derivation, "global_silence");
  assert.match(renderNotationSvg(GLOBAL_REST, {}), /notation-rest/);
});

test("a spellable rest gets a duration-specific glyph class", () => {
  assert.match(renderNotationSvg(GLOBAL_REST, {}), /notation-rest-eighth/);
});

test("an unspellable rest gets a placeholder, never a nearest glyph", () => {
  const model = notationLayoutModel(UNSUPPORTED, {});
  const rest = model.events.find((e) => e.kind === "rest");
  assert.equal(rest.displayDuration, null);
  assert.equal(rest.spellable, false);

  const svg = renderNotationSvg(UNSUPPORTED, {});
  assert.match(svg, /notation-unspellable/);
  assert.ok(svg.includes(UNSPELLABLE_GLYPH));
  // No substitution of a plausible rest value.
  assert.doesNotMatch(svg, /notation-rest-quarter/);
  assert.doesNotMatch(svg, /notation-rest-eighth/);
});

test("an unspellable rest keeps its exact tick span", () => {
  const rest = notationLayoutModel(UNSUPPORTED, {}).events.find((e) => e.kind === "rest");
  assert.equal(rest.durationTicks, 435);
});

test("an unspellable note keeps its span and is marked", () => {
  const note = notationLayoutModel(UNSUPPORTED, {}).events.find((e) => e.kind === "note");
  assert.equal(note.durationTicks, 45);
  assert.equal(note.spellable, false);
});

test("unsupported evidence stays visible in the model (8.15)", () => {
  const model = notationLayoutModel(UNSUPPORTED, {});
  assert.ok(model.unsupportedFeatures.length >= 1);
  assert.ok(model.unsupportedFeatures.some((f) => f.code === "unsupported_display_duration"));
});

test("rests are never active, having no canonical identity", () => {
  const model = notationLayoutModel(GLOBAL_REST, { activeEventIds: ["ev-1", "ev-2"] });
  assert.equal(model.events.filter((e) => e.kind === "rest").every((e) => !e.active), true);
});

// --- tempo (ruling 2) --------------------------------------------------------

test("the initial tempo comes from the canonical revision", () => {
  const bpm = initialTempoBpm(TEMPO_CONTEXT);
  assert.equal(typeof bpm, "number");
  assert.equal(notationLayoutModel(GOLDEN, { tempoContext: TEMPO_CONTEXT }).tempoLabel, `♩ = ${bpm}`);
  assert.match(renderNotationSvg(GOLDEN, { tempoContext: TEMPO_CONTEXT }), /notation-tempo/);
});

test("the bpm is read from Core, never computed here", () => {
  assert.equal(initialTempoBpm({ tempo_changes: [{ tick: 0, tempo_bpm: 120 }] }), 120);
  // No tempo field at all means no label, rather than a default invented here.
  assert.equal(initialTempoBpm({ tempo_changes: [{ tick: 0 }] }), null);
});

test("the earliest tempo wins regardless of array order", () => {
  assert.equal(
    initialTempoBpm({
      tempo_changes: [
        { tick: 960, tempo_bpm: 150 },
        { tick: 0, tempo_bpm: 120 },
      ],
    }),
    120,
  );
});

test("without tempo context no tempo is invented", () => {
  const model = notationLayoutModel(GOLDEN, {});
  assert.equal(model.tempoBpm, null);
  assert.equal(model.tempoLabel, null);
  assert.doesNotMatch(renderNotationSvg(GOLDEN, {}), /notation-tempo/);
});

test("later tempo changes are reported as undisplayed rather than dropped silently", () => {
  assert.equal(hasUndisplayedTempoChanges(TEMPO_CONTEXT), false);
  assert.equal(
    hasUndisplayedTempoChanges({
      tempo_changes: [
        { tick: 0, tempo_bpm: 120 },
        { tick: 960, tempo_bpm: 150 },
      ],
    }),
    true,
  );
});

// --- active highlighting -----------------------------------------------------

test("highlighting follows activeEventIds alone", () => {
  const ids = notationEventIds(GOLDEN);
  const model = notationLayoutModel(GOLDEN, { activeEventIds: [ids[2]] });
  assert.deepEqual(
    model.events.filter((e) => e.active).map((e) => e.canonicalEventId),
    [ids[2]],
  );
});

test("an event at tick 0 is not active merely for starting first", () => {
  const ids = notationEventIds(GOLDEN);
  const model = notationLayoutModel(GOLDEN, { activeEventIds: [ids[1]] });
  const first = model.events.find((e) => e.kind === "note" && e.startTick === 0);
  assert.equal(first.active, false);
});

test("changing the active set moves nothing", () => {
  const a = notationLayoutModel(GOLDEN, { activeEventIds: [] });
  const b = notationLayoutModel(GOLDEN, { activeEventIds: notationEventIds(GOLDEN) });
  assert.deepEqual(
    a.events.map((e) => [e.x, e.y, e.displayPitch]),
    b.events.map((e) => [e.x, e.y, e.displayPitch]),
  );
});

test("an unknown active id highlights nothing", () => {
  const model = notationLayoutModel(GOLDEN, { activeEventIds: ["nope"] });
  assert.equal(model.events.some((e) => e.active), false);
});

// --- seeking -----------------------------------------------------------------

test("the seek target is the canonical start tick", () => {
  for (const id of notationEventIds(GOLDEN)) {
    assert.equal(seekTickForEvent(GOLDEN, id), notationEventAt(GOLDEN, id).start_tick);
  }
});

test("an unknown event yields no seek target", () => {
  assert.equal(seekTickForEvent(GOLDEN, "nope"), null);
  assert.equal(notationEventAt(GOLDEN, "nope"), null);
});

test("seeking works across a meter change", () => {
  const ids = notationEventIds(METER_CHANGE);
  assert.equal(seekTickForEvent(METER_CHANGE, ids.at(-1)), 2880);
});

// --- no clock ----------------------------------------------------------------

test("the module's code never reads a clock or touches the transport", () => {
  const code = readFileSync(repoUrl("../notation-view.js"), "utf-8")
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
    assert.equal(code.includes(forbidden), false, `must not reference ${forbidden}`);
  }
});

test("the module imports nothing", () => {
  assert.doesNotMatch(readFileSync(repoUrl("../notation-view.js"), "utf-8"), /^\s*import\s/m);
});

// --- determinism and safety --------------------------------------------------

test("rendering twice produces byte-identical output", () => {
  const options = { tempoContext: TEMPO_CONTEXT, activeEventIds: ["ev-2"] };
  assert.equal(renderNotationSvg(GOLDEN, options), renderNotationSvg(GOLDEN, options));
});

test("coordinates are fixed precision", () => {
  for (const event of notationLayoutModel(OPEN_STRINGS, {}).events) {
    assert.equal(Math.round(event.x * 100) / 100, event.x);
    assert.equal(Math.round(event.y * 100) / 100, event.y);
  }
});

test("every bundled lesson renders without throwing", () => {
  for (const demo of [
    "ascending_scale",
    "descending_scale",
    "open_strings",
    "first_position",
    "position_shift",
    "string_crossing",
    "simultaneous_notes",
    "multiple_candidates",
    "unplayable_note",
    "teacher_override",
    "half_steps_one_string",
  ]) {
    const payload = load(`../projections/${demo}/notation.json`).payload;
    const tempoContext = load(`../projections/${demo}.json`).projection;
    assert.ok(renderNotationSvg(payload, { tempoContext }).startsWith("<svg"));
  }
});

test("projection text is escaped rather than executed", () => {
  const hostile = {
    ...GOLDEN,
    canonical_revision_id: 'rev-1" onload="alert(1)',
    display_policy: "<script>",
  };
  const svg = renderNotationSvg(hostile, {});
  assert.doesNotMatch(svg, /<script>/);
  assert.doesNotMatch(svg, /onload="alert/);
});

test("an empty projection renders a staff rather than throwing", () => {
  const svg = renderNotationSvg({ ...GOLDEN, measures: [] }, {});
  assert.equal(svg.match(/notation-staff-line/g).length, 5);
  assert.doesNotMatch(svg, /notation-notehead/);
});

test("the rendered SVG carries the cited revision and display policy", () => {
  const svg = renderNotationSvg(GOLDEN, {});
  assert.ok(svg.includes(`data-canonical-revision-id="${GOLDEN.canonical_revision_id}"`));
  assert.ok(svg.includes(`data-display-policy="${GOLDEN.display_policy}"`));
});

test("applyActiveEventIds toggles only the ids given", () => {
  const groups = ["ev-1", "ev-2"].map((id) => {
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
  assert.equal(groups[0].classList.has("notation-active"), false);
  assert.equal(groups[1].classList.has("notation-active"), true);
  assert.deepEqual(applyActiveEventIds(null, ["ev-1"]), []);
});

test("applyGuidedEventIds is independent of activity and selection", () => {
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
  applyActiveEventIds(root, ["ev-1"]);
  applySelectedEventId(root, "ev-2");
  assert.deepEqual(applyGuidedEventIds(root, ["ev-3"]), ["ev-3"]);
  assert.equal(groups[0].classList.has("notation-active"), true);
  assert.equal(groups[0].classList.has("notation-guided"), false);
  assert.equal(groups[1].classList.has("notation-selected"), true);
  assert.equal(groups[2].classList.has("notation-guided"), true);
});

test("an unrenderable guided id lights no neighbouring notation event", () => {
  const groups = ["ev-1", "ev-2"].map((id) => {
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
  assert.deepEqual(applyGuidedEventIds(root, ["ev-ghost"]), []);
  assert.equal(groups[0].classList.has("notation-guided"), false);
  assert.equal(groups[1].classList.has("notation-guided"), false);
});

test("derived rests never receive event-level guidance", () => {
  const rest = load("../../../resources/projections/examples/global_rest_notation.json");
  const model = notationLayoutModel(rest, { guidedEventIds: ["ev-1", "ev-2"] });
  for (const event of model.events) {
    if (event.kind === "rest") {
      assert.equal(event.canonicalEventId, null);
      assert.equal(event.guided, false);
    }
  }
});
