# MAS-PERF-001 — runtime performance baseline

Ten risks were identified by reading the code. This measured them at 100, 1,000
and 10,000 events and classified each one. **No runtime file changed.**

The headline: **nothing here matters at the size the product ships today.** At
100 events every measured path costs well under a millisecond. The interesting
question turned out to be which risks grow, and the answer is not the one the
code reading suggested — the renderer's frame loop dominates everything else,
and the duplicate scan that looked suspicious next to it is noise.

## Environment

| | |
| --- | --- |
| OS | Windows (developer machine, not an isolated host) |
| Python | 3.11.9 |
| Node | v24.11.0 |
| Node on Linux | `NOT_PRESENT` — this repository has no Linux CI for Node |
| Workloads | 100 / 1,000 / 10,000 events, deterministic, digests in the evidence |
| Sampling | 10 warm-up, 30–50 measured iterations; median and p95 reported |

Full numbers, including min and max and every scenario, are in
`MAS_RUNTIME_PERFORMANCE_BASELINE.json`.

> **Re-measured after DO-016 merged.** `local_server.py` is a measured
> surface (M9), so the whole baseline was retaken on the merged tree rather
> than carried over. The media asset branch itself is byte-identical; the
> numbers moved within run-to-run variance and no classification changed.

## Decision table

| Risk | 100 | 1,000 | 10,000 | Classification | Next action |
| --- | ---: | ---: | ---: | --- | --- |
| M1 Audio scheduler full scan | 0.015 ms | 0.065 ms | 0.562 ms | `MATTERS_AT_SCALE` | leave; revisit near 10k |
| M2 Fretboard frame updates | 0.027 ms | 0.248 ms | **5.526 ms** | `MATTERS_AT_SCALE` | browser profile first |
| M3 Main loop's second scan | 0.006 ms | 0.023 ms | 0.061 ms | `NOT_MATERIAL_IN_MEASURED_RANGE` | do not restructure |
| M4 TAB/notation active scan | 0.010 ms | 0.067 ms | 0.679 ms | `MATTERS_AT_SCALE` | measure the selector first |
| M5 Full SVG mount (notation) | 2.5 ms | 21.3 ms | **241.7 ms** | `MATTERS_AT_SCALE` | measure the parse first |
| M6 Media catalog lookup | 0.099 ms | 1.822 ms | 11.660 ms | `MATTERS_AT_SCALE` | index when catalogs grow |
| M7 Manifest reload | 0.698 ms | — | — | `NOT_MATERIAL_IN_MEASURED_RANGE` | leave |
| M8 Provenance lookup | 0.004 ms | 0.036 ms | 0.380 ms | `MATTERS_AT_SCALE` | index only if queried per event |
| M9 Media serving (100 MB ×4) | — | — | 378 ms | `MATTERS_AT_SCALE` | stream for memory, not speed |
| M10 Event lookup | 0.0051 ms | 0.0206 ms | 0.1838 ms | `NOT_MATERIAL_IN_MEASURED_RANGE` | leave |

Figures are medians. M6 columns are media-record counts, M9 is a 100 MB file at
four concurrent requests, M7 is the real manifest and does not scale with
lesson size.

## What the numbers changed about the review's picture

**The renderer is the one that matters.** At 10,000 notes a frame costs 5.5 ms
of JavaScript, p95 6.8 ms — a third of a 16.7 ms budget spent before the
browser styles, lays out or paints anything. Style writes are exactly one per
note per frame (103, 1,005 and 10,006), so the claim was precisely right.

**The scheduler is real but small.** Linear as described, and at 10,000 events
it burns about 22 ms of CPU per second of playback, roughly 2% of a core, doing
work it has already done. Worth fixing eventually; not worth the four state
transitions a cursor introduces today.

**The duplicate scan is not a problem.** `activeEventIds()` costs 0.061 ms at
10,000 notes — 1.1% of the frame it follows. The review reasoned from structure
("another O(N) pass") to concern, and the measurement does not support it. This
is the clearest case for having measured first: restructuring the loop to share
the active set would have added coupling for a 1% gain.

**Mounting a large score is a visible freeze.** 242 ms for a 10,000-event
notation mount, before the `innerHTML` parse that follows. At 1,000 events it
is 21 ms, which is a noticeable but acceptable lesson switch.

**The Python paths are latent, not live.** The catalog's O(R×M) is confirmed
and irrelevant at the size this repository ships. Provenance lookup only
becomes expensive in the quadratic case — a query per event — and no such path
exists today.

**Media serving is a memory question, not a speed one.** 100 MB serves in
194 ms, and four concurrent requests sustain about 1.0 GB/s on loopback. What
the measurement shows is the shape: each in-flight request holds its whole file,
so four concurrent 100 MB requests is roughly 400 MB resident.

## What this could not measure

Three things, named rather than estimated:

- **Style recalculation, layout and paint.** The Node benchmarks drive stub
  elements whose `style` is a counting object. The traversal figures are a
  floor on the renderer's real cost, not the cost itself.
- **`querySelectorAll` over a real SVG tree.** M4's numbers cover the loop that
  follows the selector, not the selector. For a 10,000-element tree the
  selector is likely the larger half.
- **`innerHTML` parsing and DOM construction.** M5 measures building and
  serializing the string, which is what the process does before handing the
  browser several megabytes of SVG to parse.

Each of those needs a real browser profile. This tranche did not invent numbers
for them, and the two optimizations they bear on — viewport culling and an
id-to-element map — should not be built until they exist.

The five lower-priority observations (tempo sorting, `seen.includes()`,
per-note allocation, zone-set construction, `cache: "no-store"`) were not
measured, by the order's instruction not to expand the tranche for them.

## Reproducing this

```bash
python scripts/performance/run_mas_performance_baseline.py
python scripts/performance/run_mas_performance_baseline.py --quick   # developer smoke
```

The runner refuses to overwrite the authoritative baseline from a `--quick`
run, captures the environment with every measurement, and fails if any
benchmark modifies a file outside `docs/performance/`.

**These are not CI gates.** No timing threshold is asserted anywhere, and a
test enforces that. A build that goes red because a laptop was busy teaches
people to ignore red.

## Recommended sequence, if optimization is authorized

1. **Browser profile of `renderFrame()` at 1,000 and 10,000 notes.** It is the
   only item where the measured cost is already material and the unmeasured
   cost is probably larger.
2. **The three index changes** — catalog, provenance, manifest — are
   behaviour-preserving, testable for exact-output equivalence, and touch no
   certified browser surface. They can proceed on complexity grounds if wanted,
   though only the catalog has a measured cost worth the change.
3. **Everything else waits** for the browser profile, because the fixes change
   behaviour: a scheduling cursor has four state transitions to get right, and
   viewport culling changes what exists in the DOM for the accessibility and
   diagnostics paths to read.

`web/mvp1/**` is the certified DO-015 product surface, so any of this has to
re-run Stage 9's reproducible browser witness and show lifecycle and digests
unchanged.
