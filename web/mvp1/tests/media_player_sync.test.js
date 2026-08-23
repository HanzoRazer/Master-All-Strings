import assert from "node:assert/strict";
import test from "node:test";

import { MediaPlayerController, MediaSyncMode } from "../media-player.js";
import { stubRoot, withStubDocument } from "./dom_stub.js";

const BINDING = {
  schema_version: "1.0.0",
  binding_id: "binding-half-steps-demo",
  lesson_id: "half_steps_one_string",
  media_id: "half-steps-demo-video",
  sync_mode: "synchronized",
  lesson_anchor_seconds: 0,
  media_anchor_seconds: 0,
  lesson_end_seconds: 3.0,
  media_end_seconds: 3.0,
};

function videoItem({ binding = BINDING, cues = [] } = {}) {
  return {
    available: true,
    role: "demonstration",
    public_url: "/media/assets/half_steps_demo.mp4",
    timeline_binding: binding,
    media: {
      media_id: "half-steps-demo-video",
      media_type: "video",
      title: "Half Steps — Demo Clip",
      duration_seconds: 3.0,
      source: { text_body: null },
      cues,
    },
  };
}

function player({ item = videoItem(), calls = {} } = {}) {
  const { root, get } = stubRoot();
  const recorded = {
    seekLesson: [],
    play: 0,
    pause: 0,
    rate: [],
    binding: [],
    status: [],
  };
  const controller = new MediaPlayerController({
    root,
    onStatus: (m) => recorded.status.push(m),
    onSeekLesson: (s) => recorded.seekLesson.push(s),
    onTransportPlay: () => (recorded.play += 1),
    onTransportPause: () => (recorded.pause += 1),
    onTransportRate: (r) => recorded.rate.push(r),
    onBindingChange: (b) => recorded.binding.push(b),
    ...calls,
  });
  controller.items = [item];
  controller._ensureBindings();
  return { controller, root, get, recorded };
}

// --- mode selection ----------------------------------------------------------

test("media starts detached: synchronization is never implied by existing", () => {
  const { controller } = player();
  assert.equal(controller.syncMode, MediaSyncMode.DETACHED);
  assert.equal(controller.synchronized, false);
});

test("unbound media cannot be synchronized and says so", () => {
  const restore = withStubDocument();
  try {
    const { controller, recorded } = player({ item: videoItem({ binding: null }) });
    const actual = controller.setSyncMode(MediaSyncMode.SYNCHRONIZED);
    assert.equal(actual, MediaSyncMode.DETACHED);
    assert.ok(recorded.status.some((m) => m.includes("no lesson binding")));
  } finally {
    restore();
  }
});

test("bound media synchronizes on request", () => {
  const restore = withStubDocument();
  try {
    const { controller } = player();
    assert.equal(controller.setSyncMode(MediaSyncMode.SYNCHRONIZED), MediaSyncMode.SYNCHRONIZED);
  } finally {
    restore();
  }
});

test("the sync control is hidden for media that cannot be synchronized", () => {
  const { controller, get } = player({ item: videoItem({ binding: null }) });
  controller._updateSyncControls();
  assert.equal(get("[data-sync-controls]").hidden, true);
});

// --- rate: the 1.25x question ------------------------------------------------

test("detached mode keeps the MVP 2A media-only 1.25x step", () => {
  const restore = withStubDocument();
  try {
    const { controller, get } = player();
    controller._renderRateOptions();
    const values = get("[data-media-rate]").children.map((o) => Number(o.value));
    assert.deepEqual(values, [0.5, 0.75, 1.0, 1.25, 1.5]);
  } finally {
    restore();
  }
});

test("synchronized mode offers only the shared transport's rates", () => {
  const restore = withStubDocument();
  try {
    const { controller, get } = player();
    controller.setSyncMode(MediaSyncMode.SYNCHRONIZED);
    const values = get("[data-media-rate]").children.map((o) => Number(o.value));
    // 1.25x is absent rather than silently approximated to a supported rate.
    assert.deepEqual(values, [0.5, 0.75, 1.0, 1.5]);
    assert.ok(!values.includes(1.25));
  } finally {
    restore();
  }
});

test("a synchronized rate change routes through the shared transport", () => {
  const restore = withStubDocument();
  try {
    const { controller, get, recorded } = player();
    controller.setSyncMode(MediaSyncMode.SYNCHRONIZED);
    get("[data-media-rate]").fire("change", { target: { value: "0.75" } });
    assert.deepEqual(recorded.rate, [0.75]);
    // The element is not set directly: the transport will drive it.
    assert.equal(get("[data-media-video]").playbackRate, 1);
  } finally {
    restore();
  }
});

test("a detached rate change stays media-local", () => {
  const { controller, get, recorded } = player();
  get("[data-media-rate]").fire("change", { target: { value: "1.25" } });
  assert.deepEqual(recorded.rate, []);
  assert.equal(get("[data-media-video]").playbackRate, 1.25);
});

// --- play / pause ------------------------------------------------------------

test("synchronized play and pause route through the shared transport", () => {
  const restore = withStubDocument();
  try {
    const { controller, get, recorded } = player();
    controller.setSyncMode(MediaSyncMode.SYNCHRONIZED);
    get("[data-media-play]").fire("click");
    get("[data-media-pause]").fire("click");
    assert.equal(recorded.play, 1);
    assert.equal(recorded.pause, 1);
    assert.equal(get("[data-media-video]").playCalls, undefined);
  } finally {
    restore();
  }
});

test("detached play and pause stay media-local (MVP 2A behavior)", () => {
  const { get, recorded } = player();
  get("[data-media-play]").fire("click");
  get("[data-media-pause]").fire("click");
  assert.equal(recorded.play, 0);
  assert.equal(recorded.pause, 0);
  assert.equal(get("[data-media-video]").playCalls, 1);
  assert.equal(get("[data-media-video]").pauseCalls, 1);
});

// --- looping -----------------------------------------------------------------

test("the practice loop owns looping while synchronized", () => {
  const restore = withStubDocument();
  try {
    const { controller, get, recorded } = player();
    controller.setSyncMode(MediaSyncMode.SYNCHRONIZED);
    get("[data-media-loop-apply]").fire("click");
    assert.equal(controller.loop.enabled, false);
    assert.ok(recorded.status.some((m) => m.includes("practice loop")));
  } finally {
    restore();
  }
});

test("media-local looping still works while detached", () => {
  const { controller, get } = player();
  get("[data-media-loop-start]").value = "0.5";
  get("[data-media-loop-end]").value = "2.0";
  get("[data-media-video]").duration = 3.0;
  get("[data-media-loop-apply]").fire("click");
  assert.equal(controller.loop.enabled, true);
  assert.equal(controller.loop.start, 0.5);
});

test("loop controls are marked transport-owned while synchronized", () => {
  const restore = withStubDocument();
  try {
    const { controller, get } = player();
    controller.setSyncMode(MediaSyncMode.SYNCHRONIZED);
    assert.equal(get("[data-media-loop-apply]").disabled, true);
    assert.equal(get("[data-media-loop-apply]").dataset.transportOwned, "true");
    controller.setSyncMode(MediaSyncMode.DETACHED);
    assert.equal(get("[data-media-loop-apply]").disabled, false);
  } finally {
    restore();
  }
});

test("the media-local loop does not fight the practice loop", () => {
  const restore = withStubDocument();
  try {
    const { controller, get } = player();
    // Arm a media loop while detached, then synchronize.
    get("[data-media-loop-start]").value = "0.5";
    get("[data-media-loop-end]").value = "2.0";
    get("[data-media-loop-apply]").fire("click");
    assert.equal(controller.loop.enabled, true);
    controller.setSyncMode(MediaSyncMode.SYNCHRONIZED);

    const video = get("[data-media-video]");
    video.currentTime = 2.5;
    video.fire("timeupdate");
    // Untouched: while synchronized the practice loop is authoritative.
    assert.equal(video.currentTime, 2.5);
  } finally {
    restore();
  }
});

// --- cues --------------------------------------------------------------------

test("a bound cue seeks the lesson, an unbound cue seeks the media", () => {
  const restore = withStubDocument();
  try {
    const item = videoItem({
      cues: [
        { cue_id: "cue-half", time_seconds: 0.2, label: "Half steps", lesson_time_seconds: 0.5 },
        { cue_id: "cue-zone1", time_seconds: 1.0, label: "Zone 1", lesson_time_seconds: null },
      ],
    });
    const { controller, get, recorded } = player({ item });
    controller.select(0);

    const buttons = get("[data-media-cues]").children;
    assert.equal(buttons.length, 2);

    buttons[0].fire("click");
    assert.deepEqual(recorded.seekLesson, [0.5]);

    buttons[1].fire("click");
    // Still one lesson seek: the unbound cue moved only the media.
    assert.deepEqual(recorded.seekLesson, [0.5]);
    assert.equal(get("[data-media-video]").currentTime, 1.0);
  } finally {
    restore();
  }
});

test("a bound cue may point past the clip, because it seeks the lesson", () => {
  const restore = withStubDocument();
  try {
    const item = videoItem({
      cues: [
        {
          cue_id: "cue-one-string",
          time_seconds: 1.8,
          label: "Play on one string",
          lesson_time_seconds: 3.5,
        },
      ],
    });
    const { controller, get, recorded } = player({ item });
    controller.select(0);
    get("[data-media-cues]").children[0].fire("click");
    // 3.5s is past the clip's 3.0s range; the lesson still goes there.
    assert.deepEqual(recorded.seekLesson, [3.5]);
  } finally {
    restore();
  }
});

test("cue buttons record whether they are transport-bound", () => {
  const restore = withStubDocument();
  try {
    const item = videoItem({
      cues: [
        { cue_id: "a", time_seconds: 0.2, label: "A", lesson_time_seconds: 0.5 },
        { cue_id: "b", time_seconds: 1.0, label: "B", lesson_time_seconds: null },
      ],
    });
    const { controller, get } = player({ item });
    controller.select(0);
    const buttons = get("[data-media-cues]").children;
    assert.equal(buttons[0].dataset.transportBound, "true");
    assert.equal(buttons[1].dataset.transportBound, "false");
  } finally {
    restore();
  }
});

// --- lifecycle ---------------------------------------------------------------

test("selecting a different asset drops synchronization rather than carrying it", () => {
  const restore = withStubDocument();
  try {
    const { controller, recorded } = player();
    controller.setSyncMode(MediaSyncMode.SYNCHRONIZED);
    controller.select(0);
    assert.equal(controller.syncMode, MediaSyncMode.DETACHED);
    assert.equal(recorded.binding.at(-1).binding_id, "binding-half-steps-demo");
  } finally {
    restore();
  }
});

test("clearing reports the loss of the binding", () => {
  const { controller, recorded } = player();
  controller.clear();
  assert.equal(recorded.binding.at(-1), null);
  assert.equal(controller.syncMode, MediaSyncMode.DETACHED);
});

// --- health readout ----------------------------------------------------------

test("health is rendered with its status and drift", () => {
  const { controller, get } = player();
  controller.renderHealth({ status: "drifting", drift_ms: 75 });
  const node = get("[data-sync-health]");
  assert.equal(node.dataset.status, "drifting");
  assert.ok(node.textContent.includes("75 ms"));
});

test("an unmeasurable status renders without a fabricated drift number", () => {
  const { controller, get } = player();
  controller.renderHealth({ status: "out_of_binding_range", drift_ms: null });
  const node = get("[data-sync-health]");
  assert.equal(node.dataset.status, "out_of_binding_range");
  assert.ok(!node.textContent.includes("ms"));
  assert.equal(node.textContent, "Past the clip");
});

test("no health at all reads as detached", () => {
  const { controller, get } = player();
  controller.renderHealth(null);
  assert.equal(get("[data-sync-health]").textContent, "Detached");
});
