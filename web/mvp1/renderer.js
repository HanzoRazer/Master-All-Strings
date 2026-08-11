/**
 * Zero-authority fretboard renderer.
 * Draws only fields present in FretboardScrollProjectionV1.
 * No fingering, no tick/tempo math, no candidate selection.
 */

function clamp(value, lo, hi) {
  return Math.min(hi, Math.max(lo, value));
}

export class FretboardRenderer {
  constructor(roots) {
    this.roots = roots;
    this.projection = null;
    this.pixelsPerSecond = 140;
  }

  load(projection) {
    this.projection = projection;
    this._buildStatic();
  }

  _buildStatic() {
    const projection = this.projection;
    const { laneLabels, scrollCanvas, playLine, gutterNotes, neckMap, instrumentTitle } =
      this.roots;
    laneLabels.replaceChildren();
    scrollCanvas.querySelectorAll(".string-lane, .note").forEach((node) => node.remove());
    gutterNotes.replaceChildren();
    neckMap.replaceChildren();

    if (!projection) return;

    instrumentTitle.textContent = projection.instrument.display_name;
    const lanes = [...projection.instrument.lanes].sort(
      (a, b) => a.display_order - b.display_order,
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

    const selected = projection.notes.filter((note) => note.status === "selected");
    selected.forEach((note) => {
      const el = document.createElement("div");
      el.className = "note";
      if (note.is_open_string) el.classList.add("open");
      if (note.selection_origin === "teacher_override") el.classList.add("override");
      el.dataset.eventId = note.event_id;
      el.dataset.onset = String(note.onset_seconds);
      el.dataset.release = String(note.release_seconds);
      const fretText = note.is_open_string ? "open" : String(note.fret_number);
      el.innerHTML = `<span>${note.pitch_label}</span><strong>${fretText}</strong>`;
      const laneIndex = lanes.findIndex((lane) => lane.string_id === note.string_id);
      const y = (laneIndex + 0.5) * laneHeight;
      el.style.top = `${y}px`;
      // x is set during renderFrame from onset_seconds and transport position
      el.style.left = "0px";
      scrollCanvas.appendChild(el);
    });

    projection.notes
      .filter((note) => note.status === "unplayable")
      .forEach((note) => {
        const item = document.createElement("div");
        item.className = "gutter-note";
        item.textContent = `${note.pitch_label} @ ${note.onset_seconds.toFixed(2)}s — ${note.unresolved_reason}`;
        gutterNotes.appendChild(item);
      });

    this._buildNeckMap(projection, lanes);
  }

  _buildNeckMap(projection, lanes) {
    const { neckMap } = this.roots;
    const frets = projection.instrument.frets || [];
    frets.forEach((fret) => {
      const mark = document.createElement("div");
      mark.className = "neck-fret";
      mark.style.left = `${8 + fret.normalized_position * 88}%`;
      neckMap.appendChild(mark);
    });
    lanes.forEach((lane, index) => {
      const line = document.createElement("div");
      line.className = "neck-string";
      line.style.top = `${((index + 0.5) / lanes.length) * 100}%`;
      neckMap.appendChild(line);
    });
    const dot = document.createElement("div");
    dot.className = "neck-dot";
    dot.id = "neckDot";
    dot.style.left = "8%";
    dot.style.top = "50%";
    neckMap.appendChild(dot);
  }

  renderFrame(positionSeconds) {
    const projection = this.projection;
    if (!projection) return;
    const viewport = this.roots.scrollViewport;
    const width = viewport.clientWidth || 600;
    const playFraction = projection.timeline.play_line_fraction ?? 0.22;
    const playX = width * playFraction;
    const pps = this.pixelsPerSecond;

    viewport.querySelectorAll(".note").forEach((el) => {
      const onset = Number(el.dataset.onset);
      const release = Number(el.dataset.release);
      const x = playX + (onset - positionSeconds) * pps;
      el.style.left = `${x}px`;
      const active = positionSeconds >= onset && positionSeconds < release;
      el.classList.toggle("active", active);
    });

    const active = projection.notes.find(
      (note) =>
        note.status === "selected" &&
        positionSeconds >= note.onset_seconds &&
        positionSeconds < note.release_seconds,
    );
    const dot = this.roots.neckMap.querySelector("#neckDot");
    if (dot && active) {
      const lanes = [...projection.instrument.lanes].sort(
        (a, b) => a.display_order - b.display_order,
      );
      const laneIndex = lanes.findIndex((lane) => lane.string_id === active.string_id);
      const y = ((laneIndex + 0.5) / Math.max(lanes.length, 1)) * 100;
      const x = 8 + clamp(active.normalized_position ?? 0, 0, 1) * 88;
      dot.style.left = `${x}%`;
      dot.style.top = `${y}%`;
      dot.style.opacity = "1";
    } else if (dot) {
      dot.style.opacity = "0.35";
    }
  }

  resize() {
    if (!this.projection) return;
    const positionAwareNotes = [...this.roots.scrollCanvas.querySelectorAll(".note")].map(
      (el) => ({
        onset: el.dataset.onset,
        release: el.dataset.release,
        active: el.classList.contains("active"),
      }),
    );
    this._buildStatic();
    // Active class is restored on next renderFrame.
    void positionAwareNotes;
  }
}
