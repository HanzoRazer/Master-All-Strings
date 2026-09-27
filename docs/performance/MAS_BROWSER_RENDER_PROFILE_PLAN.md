# MAS-PERF-002R — browser render profile

MAS-PERF-001 measured the renderer and the score views against stub elements
and named three things only a real browser can answer. This order answers them
in headed Chrome, or says plainly where it cannot.

**Measurement only.** No production renderer, notation, TAB, scheduler, lesson
or certified DO-015 artifact changes. A product file in the diff is a stop
condition, not a review comment.

## Disposition of the earlier attempt

An earlier MAS-PERF-002 was committed in a Cursor cloud-agent checkout and
reported at head `707527e0c8d1dcb00fb714dbbf574b0cc9ae4d51`. That commit was
never pushed, is not in any reachable object store, and the checkout that was
asked to publish it had never contained it. The attempt is **unrecoverable and
superseded by MAS-PERF-002R**. Its reported numbers were planning leads only;
every measurement this order publishes was produced anew.

## Base and branch

| | |
| --- | --- |
| Base | `c832aef28035c79f4c1ebbf20adf9ed802d8cd3b` (`origin/main`, PR #47 merge) |
| Branch | `cursor/mas-browser-render-profile-r01` |
| Open pull requests at branch time | none |
| Merge / tag / release / optimization | not authorized |

DO-016 Stage 2 is outside this order.

## Allowed surfaces

| Path | Role |
| --- | --- |
| `docs/development/IN_FLIGHT.md` | register row |
| `docs/performance/MAS_BROWSER_RENDER_PROFILE_*` | plan, evidence, report |
| `web/mvp1/tests/performance/browser_render_profile*` | the page, its measurement module, and the DevTools-protocol driver |
| `web/mvp1/tests/performance/browser_crypto_shim.js` | lets the unmodified fixtures load in a browser |
| `scripts/performance/run_mas_browser_profile.py` | serving, browser launch, metadata, summaries, evidence |
| `tests/performance/test_browser_render_profile_evidence.py` | evidence shape and reasoning checks |

Everything else is read-only here. In particular `web/mvp1/renderer.js`,
`notation-view.js`, `tab-view.js`, `app.js`, the MAS-PERF-001 benchmarks and
baseline, the DO-015 frozen artifacts, and `.github/workflows/verify.yml`.

The fixtures in `benchmark-fixtures.js` import `node:crypto`. Rather than edit
them, the profile page maps that one specifier to a test-only shim with an
import map, so the browser builds and digests exactly the bytes Node and Python
do.

## Workloads

The MAS-PERF-001 grammar, unchanged: workload version `1.0.0` at 100, 1,000 and
10,000 events. The digest of each size is recorded three times — by the Python
generator, by Node, and by the page itself — and a mismatch between any two
stops the run. The 10,000-event case is a stress case, not a claim about the
lessons in use today.

## Browser and environment

Headed Chrome, identified by its reported version, driven over the DevTools
protocol from Node with no new dependency. The fixtures are served with
cross-origin isolation headers so `performance.now()` resolves at the browser's
finest available granularity, and the page records whether isolation actually
took effect.

Recorded with every run: OS, CPU, browser version and user agent, viewport,
device scale factor, display refresh rate where the OS reports one, base SHA,
workload digests, harness version, Chrome flags and the collection commands.

## Operations

| Risk | Operation | Series |
| --- | --- | --- |
| M2 | `renderFrame()` inside an animation frame | JavaScript duration; forced style/layout duration after it |
| M2 | frame window: the app's loop, `renderFrame()` only, per animation frame | frame timestamps and deltas; per-frame JavaScript; long tasks |
| M4 | TAB and notation `applyActiveEventIds()` on a mounted real SVG tree | full update; the selector alone; forced style/layout after |
| M5 | replace the TAB and notation trees, as `mount*View()` does | string build; `innerHTML` replacement; forced style/layout after |

Cold mount and active update are separate operations with separate series. An
active update's selector time is never folded into a mount.

## Samples and clocks

Every operation discards **five warm-ups** and retains **20 samples**, reported
as median, p95, min and max with the raw samples beside them. Summaries are
computed from the raw samples by the runner, not reported by the page.

The 10,000-event frame window is taken twice, on two fresh page loads.

Clocks are kept apart:

- **JavaScript duration** — `performance.now()` around a synchronous call.
- **Forced style/layout** — `performance.now()` around a layout read issued
  immediately after the call, so the browser must bring style and layout up to
  date synchronously. It is its own measurement, not a remainder.
- **Frame timestamps** — the `requestAnimationFrame` callback argument, and the
  deltas between consecutive ones.
- **Long tasks** — `PerformanceObserver` entries, stored whole.
- **Trace events** — a separately collected DevTools trace on its own page
  load, so tracing overhead never touches the sampled numbers.

No duration is derived by subtracting one clock from another. Paint time in
particular is never inferred from a frame delta minus a JavaScript duration.

## Long tasks

For every long-task entry the evidence stores start time, duration, name,
attribution, container and the time origin. Each is placed against the sampled
window — the first and last retained frame timestamps — as one of:

| Placement | Means |
| --- | --- |
| `before_window` / `after_window` | wholly outside the sampled frames |
| `crosses_window_start` / `crosses_window_end` | spans a boundary; not attributable to any one delta |
| `inside_delta` | wholly within one retained delta, which is named |
| `spans_deltas` | inside the window but across more than one delta |

A task before or across the sampling boundary is never described as occurring
inside one of the 20 deltas. An `unknown` attribution stays `unknown`.

## Classification

The MAS-PERF-001 verdicts, unchanged:

| Verdict | Means |
| --- | --- |
| `MATTERS_NOW` | material at 100 events, or measurably eats the frame budget |
| `MATTERS_AT_SCALE` | small at 100, material by 1,000 or 10,000 |
| `NOT_MATERIAL_IN_MEASURED_RANGE` | no meaningful cost through 10,000 |
| `INSUFFICIENT_EVIDENCE` | this harness cannot answer it credibly |

Paint and compositing receive a finding only if the trace attributes the work
to the frames in question; otherwise `INSUFFICIENT_EVIDENCE`. Memory is
`NOT_MEASURED` unless the browser exposes a comparable metric reliably. Every
verdict cites evidence present in the JSON.

## Stop conditions

- an open pull request or register row owns this surface;
- a workload digest differs between Python, Node and the page;
- a required measurement cannot be reproduced;
- a protected product file enters the diff.

Anything the browser cannot supply is recorded as unavailable and the run
continues with the findings it does support.

## Not a CI gate

Timing never fails a build. The evidence tests check identity, sample counts,
citations, clock separation and honest missing-data states — never a
millisecond threshold.
