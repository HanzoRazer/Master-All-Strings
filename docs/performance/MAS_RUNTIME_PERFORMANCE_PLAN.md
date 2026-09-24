# MAS-PERF-001 — runtime performance characterization

Measure first. Ten performance risks were identified by reading the code, not
by running it, and the point of this tranche is to turn statements about
computational complexity into measured facts.

**No runtime file changes.** A benchmark that reveals a twenty-fold
opportunity does not authorize taking it. A production diff is a stop
condition.

## Why measurement comes before the obvious fix

Each of the three highest-risk items changes behaviour, not just cost. A
scheduling cursor changes *when* notes are scheduled across seek, loop wrap,
restart and rate change — four state transitions where an off-by-one drops a
note silently. Moving from `left` to `transform` changes layout semantics.
Viewport culling changes what exists in the DOM, which the accessibility and
diagnostics paths read.

`web/mvp1/**` is also the certified DO-015 product surface. Stage 9's
reproducible browser witness drives `app.js` through the real UI event path and
pins its digests in frozen evidence. A renderer change has to re-run that
witness and show lifecycle and digests unchanged. Knowing which changes are
worth that is the job of this tranche.

## Workloads

Three sizes, used by every scalable measurement, so later work shares one
vocabulary:

```text
100      today's lessons
1,000    a long or dense lesson
10,000   a size nothing in the repository reaches yet
```

Generated deterministically from an event count and a fixed grammar — no
clocks, no random identities. The same count produces the same bytes, which is
asserted by a test rather than assumed, and recorded as a digest beside every
measurement.

Benchmark lessons are not demos. They live under `tests/performance/` and are
never added to the demo manifest, `resources/mvp1/demos`, or the browser demo
catalog. A ten-thousand-event synthetic scale is not something a learner should
ever be offered.

## What each number is, and is not

Measurements come from repeated samples: warm-up runs discarded, then a fixed
number of measured iterations, reported as median, p95, min and max. A single
elapsed reading is not evidence.

Node measurements run against the in-repo DOM stub. That measures JavaScript
traversal and the number of style writes issued. **It does not measure browser
layout, style recalculation or paint**, which is where the renderer's real cost
would live if it has one. Where a question needs a real browser to answer, the
classification is `INSUFFICIENT_EVIDENCE` rather than a number dressed up as
one.

Node has no Linux CI here, so Node figures are Windows-only, recorded as such.

## Classification

Every risk ends with exactly one verdict, and every verdict cites measurements:

| Verdict | Means |
| --- | --- |
| `MATTERS_NOW` | material at 100 events, or measurably eats the frame or audio budget |
| `MATTERS_AT_SCALE` | small at 100, material by 1,000 or 10,000 |
| `NOT_MATERIAL_IN_MEASURED_RANGE` | no meaningful cost through 10,000 |
| `INSUFFICIENT_EVIDENCE` | the harness cannot answer it credibly |

`NOT_MATERIAL_IN_MEASURED_RANGE` and `INSUFFICIENT_EVIDENCE` are results, not
failures. A tranche that returned ten positive findings from ten guesses would
be suspicious.

## Not a CI gate

Timing thresholds belong nowhere near the correctness build: they vary by
machine and background load, and a gate that goes red for reasons nobody
controls teaches people to ignore red. CI may check that the harness imports,
that fixtures are deterministic, and that the evidence has the right shape. It
may not fail because a frame took 3.6 ms.

`.github/workflows/verify.yml` is a deferred-hygiene path frozen by DO-012A and
is untouched here regardless.

## Boundaries

| | |
| --- | --- |
| Owns | measurement, workloads, evidence, classification |
| Does not own | optimization, runtime behaviour, scheduling or rendering semantics, cache policy |
| Base | `b982f12` |
| Branch | `cursor/mas-runtime-performance-baseline-cc05` |
| Merge / tag / release | not authorized |

DO-016 (#43) is outside this scope and is not touched. DO-015 certification and
publication evidence are not touched.
