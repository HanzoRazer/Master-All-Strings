# MAS-PERF-002R — browser render profile

MAS-PERF-001 measured the fretboard renderer and the score views against stub
elements and named what only a browser could answer. This order answered it in
a headed Chrome, at 100, 1,000 and 10,000 events. **No product file changed.**

The headline: **the renderer's cost is in the browser, not in its JavaScript.**
At 1,000 notes the fretboard falls from 60 to 30 frames a second while
`renderFrame()` itself takes about a millisecond; the trace puts the rest in
paint. At 10,000 it runs at about two and a half frames a second, and
layerization is the largest single stage. The score views tell the same story
more quietly: the parts MAS-PERF-001 could not see are as large as the parts it
could.

## The earlier attempt

An earlier MAS-PERF-002 was reported complete in a Cursor cloud-agent checkout
at head `707527e0c8d1dcb00fb714dbbf574b0cc9ae4d51`. That commit was never
pushed and is **unrecoverable**: it is on no remote, in no local object store,
and was absent from the checkout asked to publish it. This order supersedes it.
**Every measurement below was produced anew by MAS-PERF-002R**; none of the
earlier attempt's reported numbers is used as evidence.

## Environment

| | |
| --- | --- |
| OS | Windows 11 (10.0.26100), developer machine, not an isolated host |
| CPU | Intel Core i7-6700HQ @ 2.60 GHz, 8 logical |
| Browser | Chrome 153.0.8010.54, headed, throwaway profile, DevTools protocol |
| Display | 60 Hz, device scale factor 1, viewport 1264 × 805 |
| Page | cross-origin isolated (finest `performance.now()`), visible and focused |
| Measured commit | `cd51f66`, clean tree, base `c832aef` |
| Workloads | MAS-PERF-001 grammar 1.0.0; Python, Node and page digests agree at every size |
| Sampling | 5 warm-ups discarded, 20 samples kept, each sample in its own animation frame |

Full numbers, raw samples, long-task records and trace reductions are in
`MAS_BROWSER_RENDER_PROFILE_EVIDENCE.json`. Figures below are medians unless
marked.

## Decision table

| Risk | 100 | 1,000 | 10,000 | Classification | Next action |
| --- | ---: | ---: | ---: | --- | --- |
| M2 fretboard frame (frame delta) | 16.66 ms | **33.32 ms** | **~400 ms** | `MATTERS_AT_SCALE` | cull or move the canvas, measured with this harness |
| M4 active update (TAB / notation) | 0.22 / 0.16 ms | 1.16 / 1.53 ms | 8.19 / 13.66 ms | `MATTERS_AT_SCALE` | count update frequency first; then an id map |
| M5 notation mount (string / parse / layout) | 3.6 / 3.6 / 5.4 ms | 22 / 24 / 25 ms | 206 / 226 / 215 ms | `MATTERS_AT_SCALE` | reduce elements mounted, not just the string |
| PAINT paint and compositing (per frame) | Paint 1.6 ms | Paint 14.4 ms | Layerize 257 ms | `MATTERS_AT_SCALE` | judge any M2 change on these stages |
| MEMORY DOM nodes added (score / fretboard) | 1,033 / 431 | 10,001 / 4,032 | 99,718 / 40,032 | `INSUFFICIENT_EVIDENCE` | heap snapshot if it becomes a question |

## M2 — the fretboard frame

| | 100 | 1,000 | 10,000 |
| --- | ---: | ---: | ---: |
| `renderFrame()` JavaScript | 0.26 ms | 1.10 ms | 6.71 ms |
| forced style/layout after it | 0.92 ms | 5.77 ms | 37.75 ms |
| frame delta, run 1 (p95) | 16.66 (33.31) ms | 33.32 (33.35) ms | 399.85 (433.31) ms |
| frame delta, run 2 (p95) | — | — | 416.47 (433.25) ms |
| long tasks observed in the window | 0 | 0 | 26 run 1, 27 run 2 |

The JavaScript agrees with MAS-PERF-001's stub figure (5.5 ms at 10,000), so
the stub measured the loop correctly. What it could not see is what matters: at
1,000 notes the loop costs about a millisecond and the frame still takes two
vsync intervals.

At 10,000 every frame is one long task of roughly 400 ms, attribution
`unknown` in a `window` container. Placed against the retained frames, 19 of
run 1's tasks start in one delta and end after the next frame timestamp, so
they are recorded as **spanning deltas** and assigned to neither; the rest lie
before the window (the warm-up frames and the renderer load), across its start
or end, or after it. No task is described as occurring inside one delta unless
it lies wholly within it, and one in run 2 does.

At 100 notes one of the twenty deltas in run 1 is 33.3 ms. It is a single
dropped frame, not a trend, and no long task accompanied it.

## M4 — active updates on a mounted score

| | 100 | 1,000 | 10,000 |
| --- | ---: | ---: | ---: |
| TAB `applyActiveEventIds()` | 0.22 ms | 1.16 ms | 8.19 ms |
| TAB selector alone | 0.02 ms | 0.13 ms | 1.03 ms |
| notation `applyActiveEventIds()` | 0.16 ms | 1.53 ms | 13.66 ms |
| notation selector alone | 0.06 ms | 0.50 ms | 5.09 ms |
| forced style/layout after update, TAB / notation | 0.31 / 0.10 ms | 0.46 / 0.24 ms | 3.16 / 1.50 ms |

The selector was measured in its own frames, not derived from the update. It is
the smaller part at every size. MAS-PERF-001 guessed the selector "likely the
larger half" at 10,000; it is not. The cost is the per-group attribute read and
class toggle across every group in the tree — which MAS-PERF-001's stub loop put
at 0.679 ms and a real SVG tree puts at 8 to 14 ms.

This is an update cost, not a frame cost: how often playback issues one was not
measured here, and it decides whether the 1,000-event figure matters.

## M5 — replacing the rendered score

| notation | 100 | 1,000 | 10,000 |
| --- | ---: | ---: | ---: |
| build the SVG string | 3.62 ms | 22.23 ms | 206.38 ms |
| `innerHTML` replacement | 3.62 ms | 24.47 ms | 226.38 ms |
| forced style/layout after | 5.39 ms | 25.30 ms | 214.90 ms |

| TAB | 100 | 1,000 | 10,000 |
| --- | ---: | ---: | ---: |
| build the SVG string | 2.10 ms | 14.28 ms | 92.99 ms |
| `innerHTML` replacement | 2.08 ms | 14.71 ms | 123.17 ms |
| forced style/layout after | 2.86 ms | 19.08 ms | 174.73 ms |

The string build agrees with MAS-PERF-001 (241.7 ms at 10,000 in Node, 206.4 ms
here). The two stages Node could not measure are each as large again. The trace
records `ParseHTML` at 354.5 ms for both views together at 10,000.

Each stage is reported on its own clock reading; they are not added into a
total. A mount runs on lesson load, not per frame: at 1,000 events it is a
noticeable pause, at 10,000 a freeze.

## Paint and compositing

The trace decoded at every size and is **attributable per frame**. The frame
window is bracketed by user-timing marks, cut at the page's own
`FireAnimationFrame` events on the renderer main thread, and the warm-up frames
are dropped as they are from the samples.

| per-frame median | 100 | 1,000 | 10,000 |
| --- | ---: | ---: | ---: |
| UpdateLayoutTree | 0.39 ms | 2.18 ms | 19.10 ms |
| Layout | 0.33 ms | 2.09 ms | 19.53 ms |
| PrePaint | 0.48 ms | 4.85 ms | 42.40 ms |
| Paint | 1.64 ms | 14.40 ms | 124.24 ms |
| Layerize | 0.24 ms | 3.83 ms | 256.81 ms |
| Raster started | 0.29 ms | 0.52 ms | 0.39 ms |

These are trace-clock figures, taken on a separate page load with tracing on.
They locate where frame time goes; they are not durations to add to or subtract
from the untraced samples, and paint time is not inferred anywhere from a frame
delta. Raster is attributed by start time and may belong to an earlier frame.

## Memory

A reliable metric was captured: the JS heap and DOM node count after a forced
collection, from `Performance.getMetrics`. Node counts grow linearly — about ten
per event for the two score views and four for the fretboard. The JS heap
barely moves (at most about 1 MB at 10,000). Because 99,718 nodes move it by
0.6 MB, it evidently excludes the DOM's own storage, so the byte cost of the
trees is **not measured**. That is why the verdict is `INSUFFICIENT_EVIDENCE`
rather than a claim either way.

## Compared with MAS-PERF-001

| | MAS-PERF-001 (Node stub) | MAS-PERF-002R (Chrome) |
| --- | --- | --- |
| M2 at 10,000 | 5.5 ms of JavaScript; browser cost unknown | 6.7 ms of JavaScript; frames about 400 ms, paint and layerize dominant |
| M4 at 10,000 | 0.679 ms loop; selector unmeasured | 8.2 to 13.7 ms update; selector 1.0 to 5.1 ms of it |
| M5 at 10,000 | 241.7 ms string build; parse unmeasured | 206 ms string, 226 ms parse, 215 ms layout (notation) |

Every MAS-PERF-001 classification for these three risks stands. What changes is
the reason: the browser work is the larger half in every case, which moves the
case for optimizing M2 from "probably" to "measured".

## What this could not measure

- **The byte cost of the DOM.** See Memory.
- **How often active updates happen during playback.** M4's per-update cost is
  measured; its frequency is not.
- **Attribution of long tasks.** Chrome reports every one as `unknown`.
- **Anything beyond this machine.** One CPU, one display, one Chrome build.

## Reproducing this

```bash
python scripts/performance/run_mas_browser_profile.py
python scripts/performance/run_mas_browser_profile.py --sizes 100 --output smoke.json   # quick check
```

The runner serves `web/mvp1` cross-origin isolated, launches headed Chrome with
a throwaway profile, stops if the Python, Node and page digests disagree, and
fails if the run changes any file outside `docs/performance/`. A re-run drops
the verdicts deliberately; they are judgements, added after reading the
numbers, and the evidence tests fail until they are made again.

**These are not CI gates.** No timing threshold is asserted anywhere.

## Recommended sequence, if optimization is authorized

1. **M2 first.** It is the only risk that costs frames during playback, and at
   1,000 notes it already does. Compare viewport culling with a transform-based
   canvas move, using this harness for before and after, and judge both on
   frame deltas and the per-frame paint and layerize stages. Re-run the DO-015
   Stage 9 witness.
2. **Count M4's update frequency** before changing it.
3. **M5 when lesson sizes grow**, aiming at the number of elements mounted
   rather than the string alone.

Nothing here was optimized, tagged or released, and DO-016 Stage 2 was not
touched.
