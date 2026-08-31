/**
 * Read-only standard notation rendering (DO-013C Stage 3).
 *
 * The renderer converts Core-authored evidence into geometry. It never replaces
 * that evidence with a different musical reading:
 *
 *   display_pitch      -> staff position and accidental glyph
 *   display_duration   -> notehead, stem, flag, dot, rest form
 *   measure + meter    -> bar geometry and time signature
 *   canonical_event_id -> identity, and the join key with every other view
 *   activeEventIds     -> which notes are lit right now
 *
 * Staff position comes from `display_pitch`, never from `midi_note`. That is the
 * whole point: a projection saying `Fb4` over MIDI 64 must land on the F line
 * with a flat, because Core decided the spelling and this module only places it.
 * Reading the MIDI number instead would silently "correct" it to E4.
 *
 * Two deliberate V1 limitations, both recorded rather than hidden:
 *
 *   MVP2C_NOTATION_REGISTER_LIMITATION - one treble staff in concert register,
 *   so low guitar pitches need many ledger lines. F#1 sits ten below the staff.
 *   Octave-transposing notation and alternate clefs are future work.
 *
 *   MVP2C_NOTATION_ACCIDENTAL_LIMITATION - an accidental is drawn for every note
 *   whose display_pitch carries one. Conventional engraving would carry it
 *   through the bar, but that makes the printed glyph depend on neighbouring
 *   notes rather than on this note's Core-authored spelling.
 *
 * Pure functions only; the DOM binder at the bottom is the sole part that
 * touches `document`. Nothing here reads a clock.
 */

export const NOTATION_LIMITATIONS = Object.freeze([
  "MVP2C_NOTATION_REGISTER_LIMITATION",
  "MVP2C_NOTATION_ACCIDENTAL_LIMITATION",
]);

export const STAFF_GEOMETRY = Object.freeze({
  lineGap: 8,
  staffTopY: 34,
  leftGutter: 54,
  rightGutter: 18,
  measureMinWidth: 120,
  noteheadRx: 4.6,
  noteheadRy: 3.4,
  stemLength: 26,
  padding: 18,
});

/** Diatonic index within an octave. Letter order, not semitones. */
const LETTER_STEPS = Object.freeze({ C: 0, D: 1, E: 2, F: 3, G: 4, A: 5, B: 6 });

/** Treble staff: bottom line E4, top line F5, as absolute diatonic steps. */
export const STAFF_BOTTOM_STEP = 4 * 7 + LETTER_STEPS.E; // 30
export const STAFF_TOP_STEP = 5 * 7 + LETTER_STEPS.F; // 38

const ACCIDENTAL_GLYPH = Object.freeze({ "#": "♯", b: "♭", "": "" });

/** Durations drawn with a hollow notehead. */
const HOLLOW = new Set(["whole", "dotted_whole", "half", "dotted_half"]);
/** Durations drawn without a stem. */
const STEMLESS = new Set(["whole", "dotted_whole"]);
/** Flag count per duration. Simple flags only -- D8 forbids beams. */
const FLAGS = Object.freeze({
  eighth: 1,
  dotted_eighth: 1,
  sixteenth: 2,
  dotted_sixteenth: 2,
  thirty_second: 3,
  dotted_thirty_second: 3,
});

/** Placeholder for a duration the V1 grammar cannot spell exactly. */
export const UNSPELLABLE_GLYPH = "?";

export function escapeXml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function round2(value) {
  return Math.round(value * 100) / 100;
}

/**
 * Split a Core-authored display pitch into letter, accidental and octave.
 *
 * Layout interpretation of an already-decided spelling. This is the only place
 * pitch is read, and `midi_note` is deliberately not consulted anywhere in this
 * module.
 */
export function parseDisplayPitch(displayPitch) {
  const match = /^([A-G])(#{1,2}|b{1,2})?(-?\d+)$/.exec(String(displayPitch ?? ""));
  if (!match) return null;
  const [, letter, accidental = "", octave] = match;
  return {
    letter,
    accidental,
    octave: Number(octave),
    // Absolute diatonic step: what decides the line or space, and what makes
    // Fb4 and E4 different positions despite being the same sounding pitch.
    step: Number(octave) * 7 + LETTER_STEPS[letter],
  };
}

/** Vertical position of a diatonic step. */
export function yForStep(step) {
  return round2(
    STAFF_GEOMETRY.staffTopY + (STAFF_TOP_STEP - step) * (STAFF_GEOMETRY.lineGap / 2),
  );
}

/**
 * Diatonic steps needing a ledger line for a note at `step`.
 *
 * Pure geometry. Ledger lines carry no musical meaning of their own; they let a
 * Core-authored pitch be placed truthfully on the staff this tranche uses.
 */
export function ledgerStepsFor(step) {
  const steps = [];
  if (step < STAFF_BOTTOM_STEP) {
    for (let s = STAFF_BOTTOM_STEP - 2; s >= step; s -= 2) steps.push(s);
  } else if (step > STAFF_TOP_STEP) {
    for (let s = STAFF_TOP_STEP + 2; s <= step; s += 2) steps.push(s);
  }
  return steps;
}

/**
 * The initial tempo in BPM, read from Core-authored tempo context.
 *
 * Read, never computed. The canonical revision stores tempo as microseconds per
 * quarter, and turning that into BPM here would be the browser converting tempo
 * -- which `test_browser_never_converts_ticks_or_tempo` forbids outright, and
 * rightly: a second place that knows how tempo works is a second tempo
 * authority. The fretboard projection already publishes `tempo_bpm` beside it,
 * so the label comes from there and this function only picks the earliest entry.
 *
 * V1 shows the first tempo only; later changes are reported as undisplayed.
 */
export function initialTempoBpm(tempoContext) {
  const changes = tempoContext?.tempo_changes ?? [];
  if (changes.length === 0) return null;
  const first = [...changes].sort((a, b) => a.tick - b.tick)[0];
  return first?.tempo_bpm ?? null;
}

/** True when the context carries tempo changes this view does not draw. */
export function hasUndisplayedTempoChanges(tempoContext) {
  return (tempoContext?.tempo_changes ?? []).length > 1;
}

/** Measure widths, proportional to tick span so a 3/4 bar is visibly shorter. */
function measureWidths(measures) {
  const spans = measures.map((m) => Math.max(1, m.end_tick - m.start_tick));
  const total = spans.reduce((sum, span) => sum + span, 0) || 1;
  // Total width scales with the number of bars, so bars keep a usable size as a
  // lesson grows instead of being squeezed into a fixed span.
  const available = measures.length * STAFF_GEOMETRY.measureMinWidth;
  return spans.map((span) => round2((span / total) * available));
}

/**
 * Build the placed model for one notation projection.
 *
 * `activeEventIds` is the only input to `active`, matched by canonical event id.
 * Rests carry no canonical id and are therefore never active -- correctly, since
 * no canonical event is sounding during one.
 */
export function notationLayoutModel(payload, options = {}) {
  const { activeEventIds = [], tempoContext = null } = options;
  const active = new Set(activeEventIds);
  const measures = payload?.measures ?? [];
  const widths = measureWidths(measures);

  let x = STAFF_GEOMETRY.leftGutter;
  const placedMeasures = [];
  const events = [];
  let minStep = STAFF_BOTTOM_STEP;
  let maxStep = STAFF_TOP_STEP;

  measures.forEach((measure, index) => {
    const width = widths[index];
    const span = Math.max(1, measure.end_tick - measure.start_tick);
    placedMeasures.push({
      measureIndex: measure.measure_index,
      startTick: measure.start_tick,
      endTick: measure.end_tick,
      meter: measure.meter,
      x: round2(x),
      width,
      barlineX: round2(x + width),
    });

    for (const event of measure.events ?? []) {
      const offset = (event.start_tick - measure.start_tick) / span;
      const eventX = round2(x + offset * width + 18);
      if (event.event_kind === "note") {
        const pitch = parseDisplayPitch(event.display_pitch);
        const step = pitch ? pitch.step : STAFF_BOTTOM_STEP;
        minStep = Math.min(minStep, step);
        maxStep = Math.max(maxStep, step);
        events.push({
          kind: "note",
          canonicalEventId: event.canonical_event_id,
          startTick: event.start_tick,
          durationTicks: event.duration_ticks,
          displayPitch: event.display_pitch,
          displayDuration: event.display_duration,
          // Drawn for every note that carries one; no bar-level carry rules.
          accidental: pitch?.accidental ?? "",
          accidentalGlyph: ACCIDENTAL_GLYPH[pitch?.accidental ?? ""] ?? "",
          step,
          x: eventX,
          y: yForStep(step),
          ledgerSteps: ledgerStepsFor(step),
          hollow: HOLLOW.has(event.display_duration),
          stemmed: !STEMLESS.has(event.display_duration) && event.display_duration !== null,
          flags: FLAGS[event.display_duration] ?? 0,
          dotted: String(event.display_duration ?? "").startsWith("dotted_"),
          spellable: event.display_duration !== null,
          active: active.has(event.canonical_event_id),
          measureIndex: measure.measure_index,
        });
      } else {
        events.push({
          kind: "rest",
          canonicalEventId: null,
          startTick: event.start_tick,
          durationTicks: event.duration_ticks,
          displayDuration: event.display_duration,
          derivation: event.derivation,
          x: eventX,
          y: yForStep(STAFF_BOTTOM_STEP + 4),
          spellable: event.display_duration !== null,
          dotted: String(event.display_duration ?? "").startsWith("dotted_"),
          active: false,
          measureIndex: measure.measure_index,
        });
      }
    }
    x += width;
  });

  const lowestY = yForStep(minStep);
  const highestY = yForStep(maxStep);
  const bpm = initialTempoBpm(tempoContext);

  return {
    canonicalRevisionId: payload?.canonical_revision_id ?? null,
    displayPolicy: payload?.display_policy ?? null,
    measures: placedMeasures,
    events,
    tempoBpm: bpm,
    tempoLabel: bpm === null ? null : `♩ = ${bpm}`,
    undisplayedTempoChanges: hasUndisplayedTempoChanges(tempoContext),
    width: round2(x + STAFF_GEOMETRY.rightGutter),
    height: round2(lowestY + STAFF_GEOMETRY.padding + STAFF_GEOMETRY.stemLength),
    topOverflowY: highestY,
    unsupportedFeatures: payload?.unsupported_features ?? [],
    limitations: NOTATION_LIMITATIONS,
  };
}

function staffLineYs() {
  const ys = [];
  for (let step = STAFF_TOP_STEP; step >= STAFF_BOTTOM_STEP; step -= 2) ys.push(yForStep(step));
  return ys;
}

function noteChildren(event) {
  const children = [];

  for (const step of event.ledgerSteps) {
    const y = yForStep(step);
    children.push({
      tag: "line",
      attrs: {
        class: "notation-ledger",
        x1: round2(event.x - 8),
        y1: y,
        x2: round2(event.x + 8),
        y2: y,
      },
      children: [],
    });
  }

  if (event.accidentalGlyph) {
    children.push({
      tag: "text",
      attrs: {
        class: "notation-accidental",
        x: round2(event.x - 12),
        y: round2(event.y + 3),
      },
      children: [event.accidentalGlyph],
    });
  }

  children.push({
    tag: "ellipse",
    attrs: {
      class: `notation-notehead${event.hollow ? " notation-hollow" : ""}`,
      cx: event.x,
      cy: event.y,
      rx: STAFF_GEOMETRY.noteheadRx,
      ry: STAFF_GEOMETRY.noteheadRy,
    },
    children: [],
  });

  if (event.stemmed) {
    const stemX = round2(event.x + STAFF_GEOMETRY.noteheadRx);
    const stemTop = round2(event.y - STAFF_GEOMETRY.stemLength);
    children.push({
      tag: "line",
      attrs: { class: "notation-stem", x1: stemX, y1: event.y, x2: stemX, y2: stemTop },
      children: [],
    });
    for (let i = 0; i < event.flags; i += 1) {
      const flagY = round2(stemTop + i * 5);
      children.push({
        tag: "path",
        attrs: {
          class: "notation-flag",
          d: `M ${stemX} ${flagY} q 7 3 6 10`,
        },
        children: [],
      });
    }
  }

  if (event.dotted) {
    children.push({
      tag: "circle",
      attrs: {
        class: "notation-dot",
        cx: round2(event.x + 10),
        cy: round2(event.y - 2),
        r: 1.6,
      },
      children: [],
    });
  }

  if (!event.spellable) {
    children.push({
      tag: "text",
      attrs: { class: "notation-unspellable", x: round2(event.x + 10), y: round2(event.y + 4) },
      children: [UNSPELLABLE_GLYPH],
    });
  }

  return children;
}

function restChildren(event) {
  if (!event.spellable) {
    // No nearest-glyph substitution. The rest exists and its tick span is
    // exact; what V1 cannot do is engrave that span, and the marker says so.
    return [
      {
        tag: "text",
        attrs: { class: "notation-rest notation-unspellable", x: event.x, y: event.y },
        children: [UNSPELLABLE_GLYPH],
      },
    ];
  }
  const children = [
    {
      tag: "rect",
      attrs: {
        class: `notation-rest notation-rest-${event.displayDuration}`,
        x: round2(event.x - 5),
        y: round2(event.y - 5),
        width: 10,
        height: 5,
      },
      children: [],
    },
  ];
  if (event.dotted) {
    children.push({
      tag: "circle",
      attrs: { class: "notation-dot", cx: round2(event.x + 9), cy: round2(event.y - 2), r: 1.6 },
      children: [],
    });
  }
  return children;
}

/** The placed model as an SVG element tree. */
export function notationSvgTree(model) {
  const children = [];

  if (model.tempoLabel) {
    children.push({
      tag: "text",
      attrs: { class: "notation-tempo", x: STAFF_GEOMETRY.leftGutter, y: 16 },
      children: [model.tempoLabel],
    });
  }

  for (const y of staffLineYs()) {
    children.push({
      tag: "line",
      attrs: {
        class: "notation-staff-line",
        x1: STAFF_GEOMETRY.leftGutter,
        y1: y,
        x2: round2(model.width - STAFF_GEOMETRY.rightGutter),
        y2: y,
      },
      children: [],
    });
  }

  const staffTop = yForStep(STAFF_TOP_STEP);
  const staffBottom = yForStep(STAFF_BOTTOM_STEP);

  children.push({
    tag: "text",
    attrs: { class: "notation-clef", x: 16, y: round2(staffBottom) },
    children: ["\u{1D11E}"],
  });

  model.measures.forEach((measure, index) => {
    if (index === 0) {
      children.push({
        tag: "text",
        attrs: { class: "notation-meter-numerator", x: round2(measure.x + 4), y: round2(staffTop + 12) },
        children: [String(measure.meter.numerator)],
      });
      children.push({
        tag: "text",
        attrs: { class: "notation-meter-denominator", x: round2(measure.x + 4), y: round2(staffBottom) },
        children: [String(measure.meter.denominator)],
      });
    } else {
      const previous = model.measures[index - 1].meter;
      // A time signature is reprinted only where the meter actually changes.
      if (
        previous.numerator !== measure.meter.numerator ||
        previous.denominator !== measure.meter.denominator
      ) {
        children.push({
          tag: "text",
          attrs: {
            class: "notation-meter-numerator notation-meter-change",
            x: round2(measure.x + 4),
            y: round2(staffTop + 12),
          },
          children: [String(measure.meter.numerator)],
        });
        children.push({
          tag: "text",
          attrs: {
            class: "notation-meter-denominator notation-meter-change",
            x: round2(measure.x + 4),
            y: round2(staffBottom),
          },
          children: [String(measure.meter.denominator)],
        });
      }
    }
    children.push({
      tag: "line",
      attrs: {
        class: "notation-barline",
        x1: measure.barlineX,
        y1: staffTop,
        x2: measure.barlineX,
        y2: staffBottom,
      },
      children: [],
    });
  });

  for (const event of model.events) {
    const attrs = {
      class:
        event.kind === "note"
          ? `notation-event notation-note${event.active ? " notation-active" : ""}`
          : "notation-event notation-rest-group",
      "data-start-tick": event.startTick,
    };
    if (event.canonicalEventId) {
      attrs["data-canonical-event-id"] = event.canonicalEventId;
      attrs.role = "button";
      attrs.tabindex = "0";
    }
    if (event.kind === "rest") attrs["data-derivation"] = event.derivation;
    children.push({
      tag: "g",
      attrs,
      children: event.kind === "note" ? noteChildren(event) : restChildren(event),
    });
  }

  return {
    tag: "svg",
    attrs: {
      class: "notation-view",
      xmlns: "http://www.w3.org/2000/svg",
      viewBox: `0 0 ${model.width} ${model.height}`,
      width: model.width,
      height: model.height,
      "data-canonical-revision-id": model.canonicalRevisionId,
      "data-display-policy": model.displayPolicy,
    },
    children,
  };
}

export function serializeSvg(node) {
  if (typeof node === "string" || typeof node === "number") return escapeXml(node);
  const attrs = Object.entries(node.attrs ?? {})
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => `${key}="${escapeXml(value)}"`)
    .join(" ");
  const open = attrs ? `${node.tag} ${attrs}` : node.tag;
  const inner = (node.children ?? []).map(serializeSvg).join("");
  return inner ? `<${open}>${inner}</${node.tag}>` : `<${open}/>`;
}

export function renderNotationSvg(payload, options = {}) {
  return serializeSvg(notationSvgTree(notationLayoutModel(payload, options)));
}

// --- navigation --------------------------------------------------------------

/** The projection's note for one canonical event, or null. */
export function notationEventAt(payload, canonicalEventId) {
  for (const measure of payload?.measures ?? []) {
    for (const event of measure.events ?? []) {
      if (event.canonical_event_id === canonicalEventId) return event;
    }
  }
  return null;
}

/** Where a click on this event seeks to. Never consults the active set. */
export function seekTickForEvent(payload, canonicalEventId) {
  const event = notationEventAt(payload, canonicalEventId);
  return event ? event.start_tick : null;
}

/** Canonical ids of notes, in score order. Rests have none and are excluded. */
export function notationEventIds(payload) {
  const ids = [];
  for (const measure of payload?.measures ?? []) {
    for (const event of measure.events ?? []) {
      if (event.canonical_event_id) ids.push(event.canonical_event_id);
    }
  }
  return ids;
}

// --- thin DOM binder ---------------------------------------------------------

export function mountNotationView(container, payload, options = {}) {
  if (!container) return null;
  container.innerHTML = renderNotationSvg(payload, options);
  const onSeek = options.onSeek;
  if (typeof onSeek !== "function") return container.firstChild;

  const activate = (target) => {
    const group = target.closest?.("[data-canonical-event-id]");
    if (!group) return;
    const id = group.getAttribute("data-canonical-event-id");
    const tick = seekTickForEvent(payload, id);
    if (tick !== null) onSeek(id, tick);
  };

  container.addEventListener("click", (event) => activate(event.target));
  container.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      activate(event.target);
    }
  });
  return container.firstChild;
}

/** Repaint only active-note classes; touches nothing else. */
export function applyActiveEventIds(root, activeEventIds) {
  if (!root?.querySelectorAll) return [];
  const active = new Set(activeEventIds ?? []);
  const applied = [];
  for (const group of root.querySelectorAll("[data-canonical-event-id]")) {
    const id = group.getAttribute("data-canonical-event-id");
    const isActive = active.has(id);
    group.classList?.toggle("notation-active", isActive);
    if (isActive) applied.push(id);
  }
  return applied;
}

/**
 * Mark one note as selected.
 *
 * Independent of `notation-active`: selection is where a reader is pointing,
 * activity is what the playhead says is sounding. One channel for both would let
 * a click misreport the music.
 *
 * Passing null clears the selection. Returns the id actually marked, or null.
 */
export function applySelectedEventId(root, canonicalEventId) {
  if (!root?.querySelectorAll) return null;
  let marked = null;
  for (const group of root.querySelectorAll("[data-canonical-event-id]")) {
    const id = group.getAttribute("data-canonical-event-id");
    const isSelected = canonicalEventId !== null && id === canonicalEventId;
    group.classList?.toggle("notation-selected", isSelected);
    if (isSelected) marked = id;
  }
  return marked;
}
