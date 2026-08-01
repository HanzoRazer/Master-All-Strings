# Performance Runtime Responsibility Matrix

Row-by-row ownership for the Embedded Performance Runtime, per
[ADR-0007](../decisions/ADR-0007-EMBEDDED-PERFORMANCE-RUNTIME.md).

Read the two ownership columns as different questions:

- **Constitutional owner** — which engine holds the authority. Governance. Fixed by
  the registry (`governance/engine_architecture_v1.json`).
- **Implementation owner** — which component does the work. Replaceable. May change
  without any constitutional change; that is the point of ADR-0007 D18.

"Runtime" below means whichever adapter is active — Ardour today, a fake runtime in
tests, a lightweight runtime later. Where the implementation owner is *Runtime*, the
constitutional owner still governs what the result may claim.

## Matrix

| Capability | Constitutional owner | Implementation owner | Producer | Consumer | Persistence owner | Failure owner | Versioning authority | Evidence class |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MIDI input | Performance | Runtime + OS MIDI service | Device | Performance | none (transient) | Performance | Performance | evidence source |
| Audio output | Performance | Runtime + OS audio service | Runtime | Player | none (transient) | Performance | Performance | neither |
| Runtime process | Performance | Adapter (process boundary) | Performance | Performance | none | Performance | Performance | neither |
| Synth loading | Performance | Runtime (LV2 host) | Performance | Runtime | synth registry | Performance | Performance | neither |
| Transport | Performance | Runtime | Performance | Runtime | session config | Performance | Performance | neither |
| Performance capture | Performance | Adapter + Performance | Runtime | Performance | Performance | Performance | Performance | evidence |
| Raw capture (`RawPerformanceCaptureV1`) | Performance | Performance | Performance | Educational, Musical Core | Performance | Performance | Performance | **evidence** |
| Performance observation (`PerformanceObservationV1`) | Performance | Performance | Performance | Educational | Performance | Performance | Performance | **evidence** |
| Runtime health (`RuntimeHealthV1`) | Performance | Adapter | Runtime | Performance | Performance | Performance | Performance | evidence |
| Canonical ingestion (`CanonicalIngestionRequestV1`) | **Musical Core** | Performance produces; Core consumes | Performance | Musical Core | Musical Core | Musical Core | **Musical Core** | neither |
| Canonical revision identity | **Musical Core** | Musical Core | Musical Core | all engines | Musical Core | Musical Core | Musical Core | neither |
| Piano roll (semantic projection) | **Musical Core** | Musical Core | Musical Core | Creative, Educational | Musical Core | Musical Core | Musical Core | neither |
| Piano roll (interactive editing) | **Creative** | Creative | Creative | Musical Core (as commands) | Musical Core | Creative | Creative | neither |
| Notation projection | **Musical Core** | Musical Core | Musical Core | Creative, Educational | Musical Core | Musical Core | Musical Core | neither |
| TAB projection | **Musical Core** | Musical Core | Musical Core | Creative, Educational | Musical Core | Musical Core | Musical Core | neither |
| Score editing | **Creative** | Creative | Creative | Musical Core | Musical Core | Creative | Creative (proposals) / Core (commands) | neither |
| Coaching | **Educational** | Educational | Educational | learner | Educational | Educational | Educational | **interpretation** |
| Telemetry | Performance | Performance | Performance | Educational | Performance | Performance | Performance | evidence |
| Phone / tablet control | Performance | Performance controller | Control surface | Performance | none | Performance | Performance | neither |

## Rows that are commonly got wrong

**Canonical ingestion.** The producer is Performance and the owner is Musical Core.
That asymmetry is deliberate and mirrors `ScoreEditCommandSet`, which Creative
produces and Core owns: the engine that owns the canonical model owns the vocabulary
for changing it, even when another engine speaks it. Performance may reference a
`canonical_revision_id` once Core supplies it, and may never mint one.

**Piano roll appears twice.** The semantic projection and the interactive editing
experience are different capabilities with different owners. Collapsing them is how
a second authoritative note model gets created (ADR-0007 D8). Performance appears in
neither row: it may *display* a projection during review via `ProjectionResultV1`,
which already lists Performance as a permitted consumer, but it owns no note model
and maintains no note collection.

**Failure owner is not always the implementation owner.** When Ardour dies during
capture, the runtime caused the failure but **Performance** owns the consequence:
closing the capture as `INTERRUPTED`, attaching the fault, and preserving the events
accepted so far. A runtime cannot decide what a failure means for the record.

**Raw capture has no runtime persistence owner.** Runtime session files are
operational artifacts. They are not the store of record for a performance, and they
are never read back as canonical music.

**Telemetry is evidence, never interpretation.** Performance may not own an
`interpretation`-classified capability at all; the governance validator rejects it.
Latency, faults, and counts are facts. What they mean for a learner is Educational's
under Seam 4.
