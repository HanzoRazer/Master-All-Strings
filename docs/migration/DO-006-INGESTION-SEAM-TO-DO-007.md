# Migrating the DO-006 ingestion seam to DO-007

What changed at the Performance-to-Musical-Core boundary, why, and what a caller has to
do about it.

**Scope:** breaking changes to `CanonicalIngestionRequestV1` and
`performance.ingestion`. No behaviour outside the seam changed, and the raw capture
contract is untouched.

## Why it changed

DO-006 built the Performance half of a seam that had nothing on the other side, and it
made two decisions that only became wrong once Core grew a real ingestion service.

**The Core-owned contract lived in the Performance package.** The registry has always
recorded `CanonicalIngestionRequestV1` as `owning_engine: MUSICAL_CORE`,
`producers: [PERFORMANCE_ENGINE]` — the same asymmetry `ScoreEditCommandSet` uses. But
the class was defined in `performance/contracts/ingestion.py`. Harmless while Core had
no consumer; fatal the moment it did, because `core` would have had to import from
`performance` and break the dependency matrix.

**The request carried a revision id Core was supposed to fill in.** A request is what
Performance *asks*; a revision id is what Core *answers*. Modelling the answer as a
mutable field on the question meant Performance held a field it was forbidden to
populate, protected only by a `with_revision` helper that refused to overwrite.

## What changed

| DO-006 | DO-007 |
| --- | --- |
| `CanonicalIngestionRequestV1` defined in `performance/contracts/ingestion.py` | Defined in `core/ingestion/contracts.py`, re-exported by Performance |
| `canonical_revision_id: str \| None` on the request | **Field removed.** Core answers with `CanonicalIngestionResultV1` |
| `request.with_revision(id)` | **Removed.** Read `result.revision_id` |
| `tempo_context: float` (BPM) | `tempo_microseconds_per_quarter: int` |
| `meter_context: MeterV1` (Performance) | `meter: MeterChangeV1` (Core) |
| request carried a digest only | also carries `source_events` and `capture_origin_ns` |
| — | `ProjectionType` moved to Core alongside the request |

### The request now carries its events

Core cannot import `RawPerformanceCaptureV1` — that contract genuinely is
Performance-owned — so it cannot read a capture directly. The request therefore carries
the note events in a Core-owned neutral form, `SourceMidiEventV1`, that Performance
fills in from its capture.

The raw capture never crosses the boundary, is never handed over, and is never mutated.
Core works from a restatement, and the digest is what ties the restatement back to the
record it came from.

Only note-on and note-off cross. Controller, pitch-bend, program-change, and
channel-pressure events stay in the capture: `DIRECT_EVENT_IMPORT_V1` has no canonical
representation for them, and moving them into a "converted" pile would misreport what
was ingested.

### Tempo became an integer

`tempo_context: float` became `tempo_microseconds_per_quarter: int`, matching
`TempoChangeV1`. A float BPM would let two tempo maps a musician considers identical
produce different content digests, because 120.0 and 119.99999999999999 are different
floats and the tempo map is inside the digest.

### A capture origin is required

Elapsed time needs an origin, and `RawPerformanceCaptureV1` records `started_at` as an
ISO wall clock with no monotonic counterpart. `build_ingestion_request` defaults
`capture_origin_ns` to the earliest event timestamp — the only origin the capture
actually evidences — and a caller with a real recorded origin should pass it.

## Migrating a call site

```python
# DO-006
request = build_ingestion_request(
    capture,
    request_id="req-1",
    instrument_profile_id="guitar-standard-6",
    tuning_profile_id="standard-e",
    requested_at=now,
)
revision_id = request.with_revision(core_supplied_id).canonical_revision_id

# DO-007
request = build_ingestion_request(
    capture,
    request_id="req-1",
    requested_at=now,
    beats_per_minute=120.0,          # or pass the tempo you recorded
    instrument_profile_id="guitar-standard-6",
    tuning_profile_id="standard-e",
)
result = ingestion_service.ingest(request, completed_at=now)
revision_id = result.revision_id     # Core minted it; may be None if rejected
document_id = result.document_id
```

Always check `result.status` before trusting `revision_id`. A capture with unmatched
note-ons yields `ACCEPTED_WITH_REJECTIONS` and a revision that is real but incomplete;
`result.revision_is_complete_for_input` answers that directly.

## What did not change

- `RawPerformanceCaptureV1`, `CapturedMidiEventV1`, and every other Performance contract.
- Raw capture immutability, closure semantics, and fault attachment.
- The readiness lifecycle and `stop()`-during-capture behaviour from DO-006's fix pass.
- The rule itself: Performance may reference a revision id, never mint one. It is now
  enforced by the absence of a field rather than by a helper that refuses.

## Tests

`tests/performance/test_projection_proof.py` **keeps its Musical Core double.** Its job
is to prove what Performance does at the seam without depending on Core's
implementation. It was updated to the new contract shape, not converted to real Core.

`tests/core/ingestion/test_do006_integration.py` is the end-to-end proof with the double
removed. It depends on Core by design: if the ingestion seam breaks, that test should
fail. A test asserts the isolated Performance proof still uses a double, so the two do
not quietly converge.
