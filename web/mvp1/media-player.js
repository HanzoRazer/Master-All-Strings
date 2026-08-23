/**
 * Lesson Media presentation controls (DO-011), with DO-012 synchronization.
 *
 * Two explicit modes, and nothing in between:
 *
 *   DETACHED     - exactly MVP 2A. Media plays, pauses, seeks, and rates on its
 *                  own, including the media-only 1.25x step. The shared
 *                  transport is never touched.
 *   SYNCHRONIZED - the shared transport owns play state, position, rate, and
 *                  looping. Media-local controls either route through it or
 *                  step aside, so there is never a second thing to argue with.
 *
 * Synchronization is opt-in and requires an explicit binding. Media that has no
 * binding cannot be synchronized and says so rather than guessing.
 */

/** MVP 2A media-only rates. 1.25x has no shared-transport equivalent. */
const DETACHED_RATES = [0.5, 0.75, 1.0, 1.25, 1.5];

/** The shared transport's supported set. Nothing here is approximated. */
const SHARED_RATES = [0.5, 0.75, 1.0, 1.5];

export const MediaSyncMode = Object.freeze({
  DETACHED: "detached",
  SYNCHRONIZED: "synchronized",
});

export class MediaPlayerController {
  constructor({
    root,
    onStatus,
    // DO-012 seams. All optional: without them the controller is MVP 2A.
    onSeekLesson,
    onTransportPlay,
    onTransportPause,
    onTransportRate,
    onBindingChange,
  } = {}) {
    this.root = root;
    this.onStatus = onStatus || (() => {});
    this.onSeekLesson = onSeekLesson || null;
    this.onTransportPlay = onTransportPlay || null;
    this.onTransportPause = onTransportPause || null;
    this.onTransportRate = onTransportRate || null;
    this.onBindingChange = onBindingChange || (() => {});
    this.items = [];
    this.activeIndex = 0;
    this.loop = { enabled: false, start: 0, end: 0 };
    this.syncMode = MediaSyncMode.DETACHED;
    this._bound = false;
  }

  clear() {
    const video = this.root.querySelector("[data-media-video]");
    if (video) {
      try {
        video.pause();
      } catch (_) {
        /* ignore */
      }
      video.removeAttribute("src");
      video.load();
    }
    this.items = [];
    this.activeIndex = 0;
    this.loop = { enabled: false, start: 0, end: 0 };
    this.syncMode = MediaSyncMode.DETACHED;
    this.root.querySelector("[data-media-status]").textContent = "No teaching media";
    this.root.querySelector("[data-media-body]").replaceChildren();
    this.root.querySelector("[data-media-cues]").replaceChildren();
    this._updateSyncControls();
    this.onBindingChange(null);
    this.root.hidden = true;
  }

  /** The active item's binding, or null when this media cannot be synchronized. */
  activeBinding() {
    const item = this.items[this.activeIndex];
    return item?.timeline_binding || null;
  }

  get element() {
    return this.root.querySelector("[data-media-video]");
  }

  /**
   * Switch modes. Requesting SYNCHRONIZED without a binding is refused rather
   * than inferred, and the caller is told which mode it actually got.
   */
  setSyncMode(mode) {
    if (mode === MediaSyncMode.SYNCHRONIZED && !this.activeBinding()) {
      this.syncMode = MediaSyncMode.DETACHED;
      this.onStatus("This media has no lesson binding; staying detached");
    } else {
      this.syncMode =
        mode === MediaSyncMode.SYNCHRONIZED
          ? MediaSyncMode.SYNCHRONIZED
          : MediaSyncMode.DETACHED;
    }
    if (this.syncMode === MediaSyncMode.DETACHED) {
      // Leaving synchronized mode must not touch the shared transport, and the
      // media-only rate list comes back.
      this.loop.enabled = false;
    }
    this._renderRateOptions();
    this._updateSyncControls();
    return this.syncMode;
  }

  get synchronized() {
    return this.syncMode === MediaSyncMode.SYNCHRONIZED;
  }

  async loadForLesson(lessonKey) {
    this.clear();
    if (!lessonKey) return;
    let payload;
    try {
      const response = await fetch(`/api/v1/lessons/${encodeURIComponent(lessonKey)}/media`, {
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`media HTTP ${response.status}`);
      payload = await response.json();
    } catch (error) {
      this.root.hidden = false;
      this.root.querySelector("[data-media-status]").textContent =
        "Teaching media unavailable. Practice lesson remains available.";
      this.onStatus(String(error.message || error));
      return;
    }
    this.items = payload.items || [];
    this.root.hidden = this.items.length === 0;
    if (payload.message) {
      this.root.querySelector("[data-media-status]").textContent = payload.message;
    } else if (this.items.length === 0) {
      this.root.querySelector("[data-media-status]").textContent = "No teaching media for this lesson";
      this.root.hidden = true;
      return;
    } else {
      this.root.querySelector("[data-media-status]").textContent = "Teaching media ready";
    }
    this._ensureBindings();
    this.select(0);
  }

  _ensureBindings() {
    if (this._bound) return;
    this._bound = true;
    const video = this.root.querySelector("[data-media-video]");
    this.root.querySelector("[data-media-play]").addEventListener("click", () => {
      // Synchronized: the transport starts everything, including this element.
      if (this.synchronized && this.onTransportPlay) this.onTransportPlay();
      else video.play();
    });
    this.root.querySelector("[data-media-pause]").addEventListener("click", () => {
      if (this.synchronized && this.onTransportPause) this.onTransportPause();
      else video.pause();
    });
    this.root.querySelector("[data-media-rate]").addEventListener("change", (event) => {
      const rate = Number(event.target.value) || 1;
      if (this.synchronized && this.onTransportRate) {
        // Only the shared set is offered while synchronized, so this never
        // silently approximates an unsupported rate.
        this.onTransportRate(rate);
      } else {
        video.playbackRate = rate;
      }
    });
    this.root.querySelector("[data-media-loop-apply]").addEventListener("click", () => {
      if (this.synchronized) {
        this.onStatus("Looping is owned by the practice loop while synchronized");
        return;
      }
      const start = Number(this.root.querySelector("[data-media-loop-start]").value);
      const end = Number(this.root.querySelector("[data-media-loop-end]").value);
      const duration = Number.isFinite(video.duration) ? video.duration : Infinity;
      if (!(end > start) || start < 0 || end > duration) {
        this.onStatus("Invalid media loop bounds");
        this.loop.enabled = false;
        return;
      }
      this.loop = { enabled: true, start, end };
      video.currentTime = start;
      video.play();
      this.onStatus(`Media loop ${start}s–${end}s`);
    });
    this.root.querySelector("[data-media-loop-clear]").addEventListener("click", () => {
      this.loop.enabled = false;
      this.onStatus("Media loop cleared");
    });
    video.addEventListener("timeupdate", () => {
      // The media-local loop is a DETACHED feature. While synchronized the
      // practice loop is authoritative and this must not fight it.
      if (!this.loop.enabled || this.synchronized) return;
      if (video.currentTime >= this.loop.end) {
        video.currentTime = this.loop.start;
      }
    });
  }

  /** Report follower health beside the sync toggle. */
  renderHealth(health) {
    const node = this.root.querySelector("[data-sync-health]");
    if (!node) return;
    if (!health) {
      node.textContent = "Detached";
      node.dataset.status = "detached";
      return;
    }
    node.dataset.status = health.status;
    if (health.drift_ms === null || health.drift_ms === undefined) {
      node.textContent = SYNC_STATUS_LABELS[health.status] || health.status;
      return;
    }
    node.textContent = `${SYNC_STATUS_LABELS[health.status] || health.status} · ${health.drift_ms.toFixed(0)} ms`;
  }

  _updateSyncControls() {
    const controls = this.root.querySelector("[data-sync-controls]");
    if (!controls) return;
    const binding = this.activeBinding();
    // Offering a sync toggle for media that cannot be synchronized would be a
    // control that does nothing.
    controls.hidden = !binding;
    const toggle = this.root.querySelector("#syncEnabled");
    if (toggle) toggle.checked = this.synchronized;
    for (const selector of ["[data-media-loop-start]", "[data-media-loop-end]", "[data-media-loop-apply]", "[data-media-loop-clear]"]) {
      const node = this.root.querySelector(selector);
      if (node) {
        node.disabled = this.synchronized;
        node.dataset.transportOwned = String(this.synchronized);
      }
    }
    if (!binding) this.renderHealth(null);
  }

  _renderRateOptions() {
    const rate = this.root.querySelector("[data-media-rate]");
    if (!rate) return;
    const previous = Number(rate.value) || 1;
    const values = this.synchronized ? SHARED_RATES : DETACHED_RATES;
    rate.replaceChildren();
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = String(value);
      option.textContent = `${value.toFixed(2)}×`;
      if (value === previous || (!values.includes(previous) && value === 1)) {
        option.selected = true;
      }
      rate.appendChild(option);
    });
    rate.dataset.transportOwned = String(this.synchronized);
  }

  select(index) {
    if (!this.items.length) return;
    this.activeIndex = Math.max(0, Math.min(index, this.items.length - 1));
    const item = this.items[this.activeIndex];
    const body = this.root.querySelector("[data-media-body]");
    const video = this.root.querySelector("[data-media-video]");
    const cues = this.root.querySelector("[data-media-cues]");
    const controls = this.root.querySelector("[data-media-video-controls]");
    body.replaceChildren();
    cues.replaceChildren();
    this.loop.enabled = false;
    // A different asset means a different binding, so synchronization does not
    // carry over silently.
    this.syncMode = MediaSyncMode.DETACHED;

    const selector = document.createElement("select");
    selector.setAttribute("aria-label", "Teaching media item");
    this.items.forEach((entry, i) => {
      const option = document.createElement("option");
      option.value = String(i);
      option.textContent = `${entry.role || "media"}: ${entry.media.title}`;
      if (i === this.activeIndex) option.selected = true;
      selector.appendChild(option);
    });
    selector.addEventListener("change", () => this.select(Number(selector.value)));
    body.appendChild(selector);

    if (!item.available) {
      const note = document.createElement("p");
      note.className = "hint";
      note.textContent =
        item.diagnostic ||
        "Teaching media unavailable. Practice lesson remains available.";
      body.appendChild(note);
      controls.hidden = true;
      video.hidden = true;
      this._updateSyncControls();
      this.onBindingChange(null);
      return;
    }

    const media = item.media;
    if (media.media_type === "text") {
      controls.hidden = true;
      video.hidden = true;
      const pre = document.createElement("pre");
      pre.className = "media-text";
      pre.textContent = media.source.text_body || "";
      body.appendChild(pre);
    } else if (media.media_type === "image") {
      controls.hidden = true;
      video.hidden = true;
      const img = document.createElement("img");
      img.alt = media.title;
      img.src = item.public_url;
      img.className = "media-image";
      body.appendChild(img);
    } else if (media.media_type === "video") {
      controls.hidden = false;
      video.hidden = false;
      video.src = item.public_url;
      video.load();
      this._renderRateOptions();
      if (typeof media.duration_seconds === "number") {
        this.root.querySelector("[data-media-loop-end]").value = String(media.duration_seconds);
      }
      (media.cues || []).forEach((cue) => {
        const button = document.createElement("button");
        button.type = "button";
        const bound = cue.lesson_time_seconds !== null && cue.lesson_time_seconds !== undefined;
        button.textContent = `${cue.time_seconds.toFixed(1)}s · ${cue.label}`;
        button.dataset.cueId = cue.cue_id;
        button.dataset.transportBound = String(bound);
        if (bound) button.title = `Seeks the lesson to ${cue.lesson_time_seconds.toFixed(2)}s`;
        button.addEventListener("click", () => {
          // A bound cue seeks the lesson; an unbound cue seeks only the media.
          // Never inferred -- the binding is declared in the sidecar or absent.
          if (bound && this.onSeekLesson) {
            this.onSeekLesson(cue.lesson_time_seconds);
            this.onStatus(`Cue ${cue.label} · lesson ${cue.lesson_time_seconds.toFixed(2)}s`);
          } else {
            video.currentTime = cue.time_seconds;
            this.onStatus(`Jumped to cue ${cue.label}`);
          }
        });
        cues.appendChild(button);
      });
    }
    this._updateSyncControls();
    this.onBindingChange(this.activeBinding());
  }
}

const SYNC_STATUS_LABELS = Object.freeze({
  synced: "In sync",
  drifting: "Drifting",
  correcting: "Correcting",
  degraded: "Media degraded",
  detached: "Detached",
  unavailable: "Media unavailable",
  out_of_binding_range: "Past the clip",
});
