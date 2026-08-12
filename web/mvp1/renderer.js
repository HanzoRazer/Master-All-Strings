/**
 * Zero-authority fretboard renderer.
 * Draws only fields present in FretboardScrollProjectionV1.
 * No fingering, no tick/tempo math, no candidate selection.
 */

function clamp(value, lo, hi) {
  return Math.min(hi, Math.max(lo, value));
}

// Neck map horizontal inset, in percent, matching .neck-map padding in styles.css.
const NECK_INSET_PCT = 8;
const NECK_SPAN_PCT = 88;

const ZONE_PRESENTATION_CLASSES = Object.freeze({
  ZONE_1: "zone-1",
  ZONE_2: "zone-2",
  TRITONE_ANCHOR: "tritone-anchor",
  HALF_STEP_CROSSING: "half-step-crossing",
});

export function zonePresentationClasses(zoneSemantics) {
  if (!zoneSemantics) return [];
  const semanticIds = [
    zoneSemantics.zone_id,
    ...(zoneSemantics.semantic_roles || []),
  ];
  return [...new Set(semanticIds)]
    .map((semanticId) => ZONE_PRESENTATION_CLASSES[semanticId])
    .filter(Boolean);
}

export function oneStringViewProjection(projection, teachingProjection) {
  const teachingByEvent = new Map(
    (teachingProjection?.events || []).map((event) => [event.event_id, event]),
  );
  return {
    ...projection,
    notes: projection.notes.map((note) => {
      const teaching = teachingByEvent.get(note.event_id);
      if (!teaching || teaching.status !== "playable") {
        return {
          ...note,
          status: "unplayable",
          lane_display_order: null,
          string_id: null,
          fret_number: null,
          relative_semitone_position: null,
          normalized_position: null,
          is_open_string: null,
          selection_origin: null,
          unresolved_reason:
            teaching?.unresolved_reason || "missing_one_string_projection",
        };
      }
      return {
        ...note,
        status: "selected",
        lane_display_order: teaching.display_order,
        string_id: teaching.requested_string_id,
        fret_number: teaching.physical_fret_number,
        relative_semitone_position: teaching.relative_semitone_position,
        normalized_position: teaching.normalized_position,
        is_open_string: teaching.is_open_string,
        selection_origin: null,
        unresolved_reason: null,
      };
    }),
  };
}

export function observedEvidencePresentation(event) {
  return Object.freeze({
    observedEventId: event.observed_event_id,
    presentationRole: "OBSERVED",
    label: `Observed MIDI ${event.midi_note}`,
    onsetSeconds: event.practice_onset_seconds,
  });
}

export class FretboardRenderer {
  constructor(roots) {
    this.roots = roots;
    this.projection = null;
    this.pixelsPerSecond = 140;
    // Note elements are cached at load so the frame loop never queries the DOM.
    this.notes = [];
    // A pooled marker per *active note*, not per lane. Under the MVP's
    // chord_aware_selection limitation several simultaneous notes can be
    // selected on the same string, and the neck map must show that rather than
    // hide it behind a single marker.
    this.neckDots = [];
    this.laneCenters = [];
    this.loop = null;
    this.loopRegion = null;
    this.lastPositionSeconds = 0;
    this.zoneOverlayEnabled = false;
  }

  load(projection) {
    this.projection = projection;
    this._buildStatic();
  }

  _sortedLanes() {
    return [...this.projection.instrument.lanes].sort(
      (a, b) => a.display_order - b.display_order,
    );
  }

  _buildStatic() {
    const projection = this.projection;
    const {
      laneLabels,
      scrollCanvas,
      playLine,
      gutterNotes,
      neckMap,
      instrumentTitle,
    } = this.roots;
    laneLabels.replaceChildren();
    scrollCanvas
      .querySelectorAll(".string-lane, .note, .loop-region")
      .forEach((node) => node.remove());
    gutterNotes.replaceChildren();
    neckMap.replaceChildren();
    this.notes = [];
    this.neckDots = [];
    this.laneCenters = [];
    this.loopRegion = null;

    if (!projection) return;

    scrollCanvas.classList.toggle("zone-overlay-on", this.zoneOverlayEnabled);
    neckMap.classList.toggle("zone-overlay-on", this.zoneOverlayEnabled);

    instrumentTitle.textContent = projection.instrument.display_name;
    const lanes = this._sortedLanes();
    const laneIndexById = new Map(
      lanes.map((lane, index) => [lane.string_id, index]),
    );
    const laneCount = Math.max(lanes.length, 1);
    const viewport = this.roots.scrollViewport;
    const height = viewport.clientHeight || 280;
    const laneHeight = height / laneCount;

    lanes.forEach((lane, index) => {
      const label = document.createElement("div");
      label.className = "lane-label";
      label.style.height = `${laneHeight}px`;
      label.textContent = `${lane.display_label}`;
      laneLabels.appendChild(label);

      const row = document.createElement("div");
      row.className = "string-lane";
      row.style.top = `${index * laneHeight}px`;
      row.style.height = `${laneHeight}px`;
      row.dataset.stringId = lane.string_id;
      scrollCanvas.appendChild(row);
    });

    const playFraction = projection.timeline.play_line_fraction ?? 0.22;
    playLine.style.left = `${playFraction * 100}%`;

    if (this.loop?.enabled) {
      this.loopRegion = document.createElement("div");
      this.loopRegion.className = "loop-region";
      scrollCanvas.appendChild(this.loopRegion);
    }

    projection.notes
      .filter((note) => note.status === "selected")
      .forEach((note) => {
        const laneIndex = laneIndexById.get(note.string_id);
        if (laneIndex === undefined) {
          // The projection contract forbids this; skip rather than draw off-lane.
          return;
        }
        const el = document.createElement("div");
        el.className = "note";
        if (note.is_open_string) el.classList.add("open");
        if (note.selection_origin === "teacher_override")
          el.classList.add("override");
        el.dataset.eventId = note.event_id;
        const zoneClasses = zonePresentationClasses(note.zone_semantics);
        el.classList.add(...zoneClasses);
        if (note.zone_semantics) {
          el.dataset.zoneId = note.zone_semantics.zone_id;
          el.dataset.semanticRoles = (
            note.zone_semantics.semantic_roles || []
          ).join(" ");
        }

        const pitch = document.createElement("span");
        pitch.textContent = note.pitch_label;
        const fret = document.createElement("strong");
        fret.textContent = note.is_open_string
          ? "open"
          : String(note.fret_number);
        el.append(pitch, fret);

        el.style.top = `${(laneIndex + 0.5) * laneHeight}px`;
        // x is set during renderFrame from onset_seconds and transport position
        el.style.left = "0px";
        scrollCanvas.appendChild(el);

        this.notes.push({
          eventId: note.event_id,
          el,
          laneIndex,
          onset: note.onset_seconds,
          release: note.release_seconds,
          normalized: clamp(note.normalized_position ?? 0, 0, 1),
          active: false,
          zoneClasses,
        });
      });

    const unplayable = projection.notes.filter(
      (note) => note.status === "unplayable",
    );
    unplayable.forEach((note) => {
      const item = document.createElement("div");
      item.className = "gutter-note";
      item.textContent = `${note.pitch_label} @ ${note.onset_seconds.toFixed(2)}s — ${note.unresolved_reason}`;
      gutterNotes.appendChild(item);
    });
    // Do not show an empty danger-styled panel on a clean lesson.
    this.roots.unplayableGutter?.classList.toggle(
      "hidden",
      unplayable.length === 0,
    );

    this._buildNeckMap(projection, lanes);
  }

  _buildNeckMap(projection, lanes) {
    const { neckMap } = this.roots;
    const frets = projection.instrument.frets || [];
    frets.forEach((fret) => {
      const mark = document.createElement("div");
      mark.className = "neck-fret";
      mark.style.left = `${NECK_INSET_PCT + fret.normalized_position * NECK_SPAN_PCT}%`;
      neckMap.appendChild(mark);
    });
    lanes.forEach((lane, index) => {
      const center = ((index + 0.5) / Math.max(lanes.length, 1)) * 100;
      this.laneCenters.push(center);
      const line = document.createElement("div");
      line.className = "neck-string";
      line.style.top = `${center}%`;
      neckMap.appendChild(line);
    });
  }

  /** Grow the neck-marker pool so every simultaneously active note gets one. */
  _ensureNeckDots(count) {
    while (this.neckDots.length < count) {
      const dot = document.createElement("div");
      dot.className = "neck-dot";
      dot.style.opacity = "0";
      this.roots.neckMap.appendChild(dot);
      this.neckDots.push(dot);
    }
  }

  renderFrame(positionSeconds) {
    const projection = this.projection;
    if (!projection) return;
    const viewport = this.roots.scrollViewport;
    const width = viewport.clientWidth || 600;
    const playFraction = projection.timeline.play_line_fraction ?? 0.22;
    const playX = width * playFraction;
    const pps = this.pixelsPerSecond;
    this.lastPositionSeconds = positionSeconds;

    if (this.loopRegion && this.loop) {
      const startX = playX + (this.loop.startSeconds - positionSeconds) * pps;
      const endX = playX + (this.loop.endSeconds - positionSeconds) * pps;
      this.loopRegion.style.left = `${startX}px`;
      this.loopRegion.style.width = `${Math.max(0, endX - startX)}px`;
    }

    const activeNotes = [];

    for (const note of this.notes) {
      note.el.style.left = `${playX + (note.onset - positionSeconds) * pps}px`;
      const active =
        positionSeconds >= note.onset && positionSeconds < note.release;
      if (active !== note.active) {
        note.el.classList.toggle("active", active);
        note.active = active;
      }
      if (active) activeNotes.push(note);
    }

    // One marker per active note, so simultaneous notes are never under-reported
    // — including several on one string, which the projection legitimately emits.
    this._ensureNeckDots(activeNotes.length);
    this.neckDots.forEach((dot, index) => {
      const note = activeNotes[index];
      if (!note) {
        dot.style.opacity = "0";
        return;
      }
      dot.style.left = `${NECK_INSET_PCT + note.normalized * NECK_SPAN_PCT}%`;
      dot.style.top = `${this.laneCenters[note.laneIndex] ?? 50}%`;
      dot.className = `neck-dot ${note.zoneClasses.join(" ")}`.trim();
      dot.style.opacity = "1";
    });
  }

  resize() {
    if (!this.projection) return;
    // Lane geometry is pixel-based, so a viewport change means a static rebuild.
    // Note positions and active classes are restored on the next renderFrame.
    this._buildStatic();
  }

  setObservedEvidence(events = []) {
    this.roots.scrollCanvas
      .querySelectorAll(".observed-note")
      .forEach((node) => node.remove());
    for (const event of events) {
      if (!Number.isFinite(event.practice_onset_seconds)) continue;
      const presentation = observedEvidencePresentation(event);
      const marker = document.createElement("div");
      marker.className = "observed-note";
      marker.dataset.observedEventId = presentation.observedEventId;
      marker.dataset.presentationRole = presentation.presentationRole;
      marker.style.left = `${presentation.onsetSeconds * this.pixelsPerSecond}px`;
      marker.textContent = presentation.label;
      this.roots.scrollCanvas.append(marker);
    }
  }

  setLoop(loop) {
    this.loop = loop?.enabled ? { ...loop } : null;
    if (this.projection) this._buildStatic();
  }

  setZoneOverlay(enabled) {
    this.zoneOverlayEnabled = Boolean(enabled);
    this.roots.scrollCanvas.classList.toggle(
      "zone-overlay-on",
      this.zoneOverlayEnabled,
    );
    this.roots.neckMap.classList.toggle(
      "zone-overlay-on",
      this.zoneOverlayEnabled,
    );
  }

  diagnostics() {
    return Object.freeze({
      positionSeconds: this.lastPositionSeconds,
      activeEventIds: this.notes
        .filter((note) => note.active)
        .map((note) => note.eventId),
      zoneOverlayEnabled: this.zoneOverlayEnabled,
      zoneSemanticEventIds: this.notes
        .filter((note) => note.zoneClasses.length > 0)
        .map((note) => note.eventId),
    });
  }
}
