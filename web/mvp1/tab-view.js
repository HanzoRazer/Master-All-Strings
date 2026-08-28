/**
 * Read-only guitar tablature rendering (DO-013B Stage 2).
 *
 * Every musical decision in this file was made before it: which string and fret
 * an event uses, whether the instrument can play it at all, and which events are
 * sounding right now. This module turns those answers into coordinates.
 *
 * Two responsibilities are kept apart on purpose, because collapsing them is how
 * a renderer quietly becomes a second playhead:
 *
 *   TeachingPlayheadStateV1.activeEventIds  ->  what is highlighted now
 *   canonical event timing in the projection ->  where a click seeks to
 *
 * Highlighting never consults tick positions, and seeking never consults the
 * active set. Nothing here reads the Transport or a clock of any kind; both
 * inputs arrive as data.
 *
 * The exported functions are pure so Node can test them without a DOM. Mounting
 * and event binding live in the thin binder at the bottom, which is the only
 * part that touches `document`.
 */

/** Layout constants. Presentation geometry, not musical values. */
export const TAB_GEOMETRY = Object.freeze({
  width: 720,
  rowHeight: 22,
  topPadding: 18,
  bottomPadding: 14,
  leftGutter: 46,
  rightGutter: 16,
  markerRadius: 9,
});

/** Glyphs for the two statuses that carry no fingering to show. */
export const STATUS_GLYPH = Object.freeze({
  unplayable: "×",
  unresolved: "?",
});

const STATUS_CLASS = Object.freeze({
  playable: "tab-event tab-playable",
  unplayable: "tab-event tab-unplayable",
  unresolved: "tab-event tab-unresolved",
});

/** XML-escape text bound for an SVG text node or attribute. */
export function escapeXml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function round2(value) {
  // Fixed precision keeps the serialized SVG byte-identical across runs and
  // platforms; floating-point drift would otherwise make a golden test flap.
  return Math.round(value * 100) / 100;
}

/**
 * Ordered string rows.
 *
 * Order comes from the instrument's own `lanes`, which already carry
 * `display_order`. Deriving an order from the event list instead would make the
 * grid change shape between lessons that happen to use different strings.
 *
 * When lanes are unavailable the rows fall back to first appearance in the
 * projection. That is a presentation fallback and is reported as such, so a
 * caller can tell the difference between an instrument's layout and a guess at
 * one.
 */
export function tabRows(payload, lanes) {
  const events = payload?.events ?? [];
  if (Array.isArray(lanes) && lanes.length > 0) {
    return {
      derived: false,
      rows: [...lanes]
        .sort((a, b) => a.display_order - b.display_order)
        .map((lane) => ({
          stringId: lane.string_id,
          label: lane.display_label ?? lane.open_pitch_label ?? lane.string_id,
        })),
    };
  }
  const seen = [];
  for (const event of events) {
    if (event.string_id && !seen.includes(event.string_id)) seen.push(event.string_id);
  }
  return { derived: true, rows: seen.map((stringId) => ({ stringId, label: stringId })) };
}

/** Total tick span the projection occupies, used only for horizontal scale. */
export function tabTotalTicks(payload) {
  let total = 0;
  for (const event of payload?.events ?? []) {
    total = Math.max(total, event.start_tick + event.duration_ticks);
  }
  return total;
}

/**
 * Build the placed model for one TAB projection.
 *
 * `activeEventIds` is the sole input to `active`. It is compared by canonical
 * event id and nothing else -- not by index, not by tick range -- so the set that
 * highlights here is literally the set the playhead published.
 */
export function tabLayoutModel(payload, options = {}) {
  const { lanes = null, activeEventIds = [], loopRange = null } = options;
  const active = new Set(activeEventIds);
  const { rows, derived } = tabRows(payload, lanes);
  const rowIndex = new Map(rows.map((row, index) => [row.stringId, index]));

  const totalTicks = tabTotalTicks(payload);
  const plotWidth =
    TAB_GEOMETRY.width - TAB_GEOMETRY.leftGutter - TAB_GEOMETRY.rightGutter;
  const height =
    TAB_GEOMETRY.topPadding + rows.length * TAB_GEOMETRY.rowHeight + TAB_GEOMETRY.bottomPadding;

  const xFor = (tick) =>
    totalTicks <= 0
      ? TAB_GEOMETRY.leftGutter
      : round2(TAB_GEOMETRY.leftGutter + (tick / totalTicks) * plotWidth);
  const yFor = (index) =>
    round2(TAB_GEOMETRY.topPadding + index * TAB_GEOMETRY.rowHeight);

  const events = (payload?.events ?? []).map((event) => {
    // An event with no string cannot sit on a string row. It is placed on a
    // dedicated lane below the staff rather than dropped, because "we do not
    // know where this goes" is information the learner should see.
    const index = rowIndex.has(event.string_id) ? rowIndex.get(event.string_id) : rows.length;
    return {
      canonicalEventId: event.canonical_event_id,
      status: event.status,
      // Read, never derived. The fret shown is the fret that was selected.
      fret: event.fret,
      stringId: event.string_id,
      startTick: event.start_tick,
      durationTicks: event.duration_ticks,
      midiNote: event.midi_note,
      label: event.status === "playable" ? String(event.fret) : STATUS_GLYPH[event.status] ?? "?",
      active: active.has(event.canonical_event_id),
      x: xFor(event.start_tick),
      y: yFor(index),
      rowIndex: index,
    };
  });

  return {
    canonicalRevisionId: payload?.canonical_revision_id ?? null,
    instrumentProfileId: payload?.instrument_profile_id ?? null,
    rowsDerivedFromEvents: derived,
    rows,
    events,
    totalTicks,
    width: TAB_GEOMETRY.width,
    height,
    loop:
      loopRange && Number.isFinite(loopRange.startTick) && Number.isFinite(loopRange.endTick)
        ? { x: xFor(loopRange.startTick), width: round2(xFor(loopRange.endTick) - xFor(loopRange.startTick)) }
        : null,
    unsupportedFeatures: payload?.unsupported_features ?? [],
  };
}

/** The placed model as an SVG element tree: `{tag, attrs, children}`. */
export function tabSvgTree(model) {
  const children = [];

  if (model.loop) {
    children.push({
      tag: "rect",
      attrs: {
        class: "tab-loop",
        x: model.loop.x,
        y: TAB_GEOMETRY.topPadding - 8,
        width: model.loop.width,
        height: model.rows.length * TAB_GEOMETRY.rowHeight,
      },
      children: [],
    });
  }

  model.rows.forEach((row, index) => {
    const y = round2(TAB_GEOMETRY.topPadding + index * TAB_GEOMETRY.rowHeight);
    children.push({
      tag: "line",
      attrs: {
        class: "tab-string",
        x1: TAB_GEOMETRY.leftGutter,
        y1: y,
        x2: TAB_GEOMETRY.width - TAB_GEOMETRY.rightGutter,
        y2: y,
      },
      children: [],
    });
    children.push({
      tag: "text",
      attrs: { class: "tab-string-label", x: 8, y: round2(y + 4) },
      children: [row.label],
    });
  });

  for (const event of model.events) {
    children.push({
      tag: "g",
      attrs: {
        class: `${STATUS_CLASS[event.status] ?? "tab-event"}${event.active ? " tab-active" : ""}`,
        "data-canonical-event-id": event.canonicalEventId,
        // Carried so the binder can seek without re-deriving timing. It is the
        // projection's own tick, not a position read from any clock.
        "data-start-tick": event.startTick,
        role: "button",
        tabindex: "0",
      },
      children: [
        {
          tag: "circle",
          attrs: { cx: event.x, cy: event.y, r: TAB_GEOMETRY.markerRadius },
          children: [],
        },
        {
          tag: "text",
          attrs: { class: "tab-fret", x: event.x, y: round2(event.y + 4) },
          children: [event.label],
        },
      ],
    });
  }

  return {
    tag: "svg",
    attrs: {
      class: "tab-view",
      xmlns: "http://www.w3.org/2000/svg",
      viewBox: `0 0 ${model.width} ${model.height}`,
      width: model.width,
      height: model.height,
      "data-canonical-revision-id": model.canonicalRevisionId,
    },
    children,
  };
}

/** Serialize an element tree deterministically. */
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

/** Convenience: projection plus options straight to an SVG string. */
export function renderTabSvg(payload, options = {}) {
  return serializeSvg(tabSvgTree(tabLayoutModel(payload, options)));
}

// --- navigation --------------------------------------------------------------
//
// Separate from everything above. These answer "where does this canonical event
// begin?", which is a question about the score. They never consult the active
// set, and the active set never consults them.

/** The projection's record for one canonical event, or null. */
export function tabEventAt(payload, canonicalEventId) {
  return (
    (payload?.events ?? []).find(
      (event) => event.canonical_event_id === canonicalEventId,
    ) ?? null
  );
}

/**
 * The tick a click on this event should seek to.
 *
 * Read from the projection's canonical timing. Returns null for an event the
 * projection does not contain, so a caller cannot seek to a fabricated position.
 */
export function seekTickForEvent(payload, canonicalEventId) {
  const event = tabEventAt(payload, canonicalEventId);
  return event ? event.start_tick : null;
}

/** Canonical event ids in projection order; the join key for every other view. */
export function tabEventIds(payload) {
  return (payload?.events ?? []).map((event) => event.canonical_event_id);
}

// --- thin DOM binder ---------------------------------------------------------

/**
 * Mount an SVG string into a container and wire click/keyboard activation.
 *
 * `onSeek` receives a canonical event id and a tick; deciding what to do with
 * them belongs to the caller, which is the only party that holds the Transport.
 */
export function mountTabView(container, payload, options = {}) {
  if (!container) return null;
  container.innerHTML = renderTabSvg(payload, options);
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

/**
 * Repaint only the active-event classes.
 *
 * Highlighting changes many times a second while nothing about the score
 * changes, so re-serializing the whole SVG for it would be wasteful and would
 * also blur the boundary: this function receives ids and touches nothing else.
 */
export function applyActiveEventIds(root, activeEventIds) {
  if (!root?.querySelectorAll) return [];
  const active = new Set(activeEventIds ?? []);
  const applied = [];
  for (const group of root.querySelectorAll("[data-canonical-event-id]")) {
    const id = group.getAttribute("data-canonical-event-id");
    const isActive = active.has(id);
    group.classList?.toggle("tab-active", isActive);
    if (isActive) applied.push(id);
  }
  return applied;
}

/**
 * Mark one event as selected.
 *
 * A separate class from `tab-active`, and deliberately so: selection is a
 * reader's pointer, activity is the playhead's answer. Sharing one channel would
 * let a click overwrite what is sounding, which would make the view lie about
 * the music to show where someone clicked.
 *
 * Passing null clears the selection. Returns the id actually marked, or null.
 */
export function applySelectedEventId(root, canonicalEventId) {
  if (!root?.querySelectorAll) return null;
  let marked = null;
  for (const group of root.querySelectorAll("[data-canonical-event-id]")) {
    const id = group.getAttribute("data-canonical-event-id");
    const isSelected = canonicalEventId !== null && id === canonicalEventId;
    group.classList?.toggle("tab-selected", isSelected);
    if (isSelected) marked = id;
  }
  return marked;
}
