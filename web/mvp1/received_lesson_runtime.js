/** One practice runtime for one accepted preparation bundle.

Composes the existing transport, timeline, fretboard renderer, reference
scheduler, and score coordinator. It does not copy their algorithms, and it
does not fetch demo files or write artifacts.
*/

import { AudioScheduler } from "./audio_scheduler.js";
import { ReferenceSynth } from "./audio.js";
import { FretboardRenderer } from "./renderer.js";
import { createFretboardSelectionHandler, createScoreSeekHandler } from "./score-shell.js";
import { ScoreViewCoordinator } from "./score-view.js";
import { secondsAtTick, TeachingTimeline } from "./teaching-timeline.js";
import { Transport } from "./transport.js";
import { RECEIVED_SCORE_KEY } from "./lesson_delivery_validation.js";

export { RECEIVED_SCORE_KEY };

/**
 * In-memory `loadJson` for the coordinator. `received` is a lookup key, not
 * a demo identity. Any other path is refused.
 *
 * @param {object} bundle
 */
export function createMemoryScoreLoader(bundle) {
  const key = RECEIVED_SCORE_KEY;
  const files = new Map([
    [`projections/${key}/canonical_revision.json`, bundle.score.canonical_revision],
    [`projections/${key}/tab.json`, bundle.score.tab],
    [`projections/${key}/notation.json`, bundle.score.notation],
    [`projections/${key}.json`, bundle.projection],
  ]);
  return async (path) => {
    if (!files.has(path)) throw new Error("unexpected score path");
    return structuredClone(files.get(path));
  };
}

/**
 * @param {object} options
 * @param {object} options.bundle
 * @param {object} options.roots
 * @param {() => boolean} [options.isCurrent]
 */
export async function mountReceivedLessonRuntime(options) {
  const {
    bundle,
    roots,
    isCurrent = () => true,
    requestAnimationFrame = globalThis.requestAnimationFrame?.bind(globalThis),
    cancelAnimationFrame = globalThis.cancelAnimationFrame?.bind(globalThis),
    now,
    setIntervalFn,
    clearIntervalFn,
    ReferenceSynth: Synth = ReferenceSynth,
    renderers,
    onPlayback = () => {},
    onFrame = () => {},
  } = options;

  if (typeof requestAnimationFrame !== "function" || typeof cancelAnimationFrame !== "function") {
    throw new TypeError("runtime requires animation frame scheduling");
  }

  const transport = new Transport(now ? { now } : {});
  const timeline = new TeachingTimeline({ transport });
  const synth = new Synth();
  let scheduledNotes = 0;
  const scheduler = new AudioScheduler({
    transport,
    synth,
    ...(setIntervalFn ? { setIntervalFn } : {}),
    ...(clearIntervalFn ? { clearIntervalFn } : {}),
    onDiagnostic: (item) => {
      if (item?.type === "scheduled") scheduledNotes += 1;
    },
  });
  scheduler.setEnabled(false);
  const renderer = new FretboardRenderer(roots.fretboard);
  const coordinator = new ScoreViewCoordinator({
    loadJson: createMemoryScoreLoader(bundle),
    containers: { tab: roots.tab, notation: roots.notation },
    ...(renderers ? { renderers } : {}),
    onSeek: (canonicalEventId, tick) => {
      if (interactionLocked || disposed) return null;
      return seekFromScore(canonicalEventId, tick);
    },
  });

  let frameId = null;
  let disposed = false;
  let soundToken = 0;
  let interactionLocked = false;
  const seekFromScore = createScoreSeekHandler({ timeline, transport, secondsAtTick });
  const selectFromFretboard = createFretboardSelectionHandler({ coordinator });

  function onFretboardClick(event) {
    if (disposed) return;
    selectFromFretboard(event.target);
  }

  const unsubscribeStatus = transport.subscribe((event) => {
    if (disposed) return;
    if (event.type === "play") onPlayback("playing");
    if (event.type === "pause" || event.type === "restart") onPlayback("paused");
    if (event.type === "complete" || event.type === "loop-complete") onPlayback("ended");
  });

  function tick(nowMs) {
    if (disposed) return;
    const seconds = transport.positionSeconds(nowMs);
    renderer.renderFrame(seconds);
    if (timeline.ready) {
      timeline.setActiveEventIds(renderer.activeEventIds());
      timeline.publish("frame", nowMs);
    }
    onFrame({
      positionSeconds: seconds,
      repetitionCount: transport.repetitionCount,
      playing: transport.playing,
      scheduledNotes,
    });
    frameId = requestAnimationFrame(tick);
  }

  const runtime = {
    transport,
    timeline,
    renderer,
    scheduler,
    synth,
    coordinator,
    get disposed() {
      return disposed;
    },
    play() {
      if (disposed) return false;
      return transport.play();
    },
    pause() {
      if (disposed) return false;
      return transport.pause();
    },
    restart() {
      if (disposed || interactionLocked) return;
      transport.restart();
    },
    seek(seconds) {
      if (disposed || interactionLocked) return;
      transport.seek(seconds);
    },
    setRate(rate) {
      if (disposed || interactionLocked) return;
      transport.setRate(rate);
    },
    setLoopEnabled(enabled) {
      if (disposed || interactionLocked || !transport.loop) return;
      const loop = transport.loop;
      transport.setLoop({
        startSeconds: loop.startSeconds,
        endSeconds: loop.endSeconds,
        enabled: Boolean(enabled),
        targetRepetitions: loop.targetRepetitions,
      });
      renderer.setLoop(transport.loop);
    },
    setVolume(value) {
      if (disposed) return;
      synth.setVolume(value);
    },
    async enableSound() {
      const token = ++soundToken;
      try {
        await synth.initialize();
      } catch (error) {
        if (!disposed && token === soundToken) scheduler.setEnabled(false);
        return { ok: false, error, stale: disposed || token !== soundToken };
      }
      if (disposed || token !== soundToken) {
        try {
          synth.panic();
        } catch {
          // A replaced runtime must not keep the voices this init started.
        }
        return { ok: false, stale: true };
      }
      scheduler.setEnabled(true);
      return { ok: true };
    },
    disableSound() {
      soundToken += 1;
      scheduler.setEnabled(false);
    },
    silence() {
      soundToken += 1;
      scheduler.setEnabled(false);
      try {
        synth.panic();
      } catch {
        // Silencing is best-effort. A failed panic must not keep the attempt open.
      }
    },
    setInteractionLock(locked) {
      interactionLocked = Boolean(locked);
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      soundToken += 1;
      transport.pause();
      if (frameId != null) cancelAnimationFrame(frameId);
      frameId = null;
      scheduler.destroy();
      unsubscribeStatus();
      timeline.dispose();
      roots.fretboard.scrollCanvas.removeEventListener("click", onFretboardClick);
      renderer.load(null);
      roots.tab.replaceChildren();
      roots.notation.replaceChildren();
    },
  };

  try {
    transport.setDuration(bundle.playback.total_seconds);
    const loop = bundle.practice.policy.loop;
    transport.setLoop({
      startSeconds: bundle.practice.runtime.loop_start_seconds,
      endSeconds: bundle.practice.runtime.loop_end_seconds,
      enabled: loop.enabled,
      targetRepetitions: loop.target_repetitions,
    });
    timeline.setLesson({
      lessonId: RECEIVED_SCORE_KEY,
      anchors: bundle.projection.timeline_anchors,
    });
    scheduler.loadPlan(bundle.playback);
    scheduler.start();
    renderer.load(bundle.projection.projection);
    renderer.setLoop(transport.loop);
    timeline.addFollower(coordinator.follower());
    roots.fretboard.scrollCanvas.addEventListener("click", onFretboardClick);
    const score = await coordinator.load(RECEIVED_SCORE_KEY);
    if (!isCurrent() || disposed) {
      runtime.dispose();
      return null;
    }
    runtime.score = score;
    frameId = requestAnimationFrame(tick);
    return runtime;
  } catch (error) {
    runtime.dispose();
    throw error;
  }
}
