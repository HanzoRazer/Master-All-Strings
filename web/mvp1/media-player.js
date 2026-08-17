/** Lesson Media presentation controls (DO-011). Musical transport stays separate. */

const RATES = [0.5, 0.75, 1.0, 1.25, 1.5];

export class MediaPlayerController {
  constructor({ root, onStatus }) {
    this.root = root;
    this.onStatus = onStatus || (() => {});
    this.items = [];
    this.activeIndex = 0;
    this.loop = { enabled: false, start: 0, end: 0 };
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
    this.root.querySelector("[data-media-status]").textContent = "No teaching media";
    this.root.querySelector("[data-media-body]").replaceChildren();
    this.root.querySelector("[data-media-cues]").replaceChildren();
    this.root.hidden = true;
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
    this.root.querySelector("[data-media-play]").addEventListener("click", () => video.play());
    this.root.querySelector("[data-media-pause]").addEventListener("click", () => video.pause());
    this.root.querySelector("[data-media-rate]").addEventListener("change", (event) => {
      video.playbackRate = Number(event.target.value) || 1;
    });
    this.root.querySelector("[data-media-loop-apply]").addEventListener("click", () => {
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
      if (!this.loop.enabled) return;
      if (video.currentTime >= this.loop.end) {
        video.currentTime = this.loop.start;
      }
    });
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
      const rate = this.root.querySelector("[data-media-rate]");
      rate.replaceChildren();
      RATES.forEach((value) => {
        const option = document.createElement("option");
        option.value = String(value);
        option.textContent = `${value.toFixed(2)}×`;
        if (value === 1) option.selected = true;
        rate.appendChild(option);
      });
      if (typeof media.duration_seconds === "number") {
        this.root.querySelector("[data-media-loop-end]").value = String(media.duration_seconds);
      }
      (media.cues || []).forEach((cue) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = `${cue.time_seconds.toFixed(1)}s · ${cue.label}`;
        button.addEventListener("click", () => {
          video.currentTime = cue.time_seconds;
          this.onStatus(`Jumped to cue ${cue.label}`);
        });
        cues.appendChild(button);
      });
    }
  }
}
