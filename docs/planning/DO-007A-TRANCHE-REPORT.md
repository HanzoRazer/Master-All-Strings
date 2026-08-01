# DO-007A Tranche Report

Canonical score authority and the real ingestion seam. Written so a fresh engineer can
reconstruct the state without conversation history.

**Tranche:** DO-007A, commits A1–A5. **Engine:** Musical Core.
**Base:** `main` after PR #13. **Production behavior:** unchanged.

## Delivered

| Commit | Content |
| --- | --- |
| A1 | ADR-0008, canonical score architecture, projection authority boundary; `producer` → `producers`, projection contract rename, `canonical-music` → `partial` |
| A2 | `ScoreDocumentV1`, `CanonicalScoreRevisionV1`, `TempoChangeV1`, `MeterChangeV1`, provenance contracts |
| A3 | Canonicalization, tick-grid conversion, digest, document-ID authorities |
| A4 | Repository port, in-memory implementation, `CanonicalRevisionService` |
| A5 | Ingestion contracts, `DIRECT_EVENT_IMPORT_V1`, idempotency, the real DO-006 seam, migration note, this report |

**Verification:** 1220 tests · coverage 96.88% (floor 95%) · ruff clean · mypy strict
clean · governance validator OK · views match the registry. **Every commit
independently green** — the DO-006 mistake was not repeated.

## The definition-of-done proof

Executable today, in `tests/core/ingestion/test_do006_integration.py`:

```text
RawPerformanceCaptureV1
    -> CanonicalIngestionRequestV1     (Core-owned, Performance-produced)
    -> CanonicalIngestionService
    -> ScoreDocumentV1                 document_id minted by Core
    -> CanonicalScoreRevisionV1        revision_id minted by Core
```

Asserted: Performance supplies no revision id (the field does not exist), Core mints
both identities, the raw capture is byte-identical afterward, source nanoseconds and
conversion metadata survive in provenance, MIDI channel stays provenance and never
becomes `voice_id`, observed source string survives, FIFO pairing is deterministic,
unmatched note-ons and note-offs are rejected explicitly, and a repeat creates no second
revision.

## Two problems found and fixed

**A Core-owned contract lived in the Performance package.** The registry has always
recorded `CanonicalIngestionRequestV1` as `owning_engine: MUSICAL_CORE`, but DO-006
defined the class in `performance/contracts/ingestion.py`. Harmless while Core had no
consumer; fatal once it did, because `core` would have had to import from `performance`.
Moved to `core/ingestion/contracts.py` and re-exported by Performance. A test parses
every Core ingestion module and asserts no `performance` import appears.

**The request carried an answer.** `canonical_revision_id` was an optional field Core
was meant to fill in, protected by a `with_revision` helper that refused to overwrite.
The field is gone. A request is what Performance asks; a revision id is what Core
answers, and it now arrives on `CanonicalIngestionResultV1`. "Performance may not mint
one" is enforced by the absence of a field rather than by a helper that says no.

Both are documented in
[DO-006-INGESTION-SEAM-TO-DO-007.md](../migration/DO-006-INGESTION-SEAM-TO-DO-007.md).

## Decisions a reviewer should check

1. **Tick-grid rounding is not quantization**, and the distinction is enforced. Integer
   arithmetic throughout — an AST test asserts no true division in the conversion path.
   The tie rule is `ROUND_HALF_AWAY_FROM_ZERO`, named rather than inherited, because
   Python's `round` is banker's rounding. A note played 30 ms late converts to tick 1018,
   not 960, and a test walks several offsets asserting none lands on a beat.
2. **Missing tempo is rejected, never defaulted.** Assuming 120 BPM would put a
   fabricated tempo into the content digest, indistinguishable from a declared one.
3. **The digest includes lineage, not only music.** Without `document_id` and
   `revision_number` inside it, reverting to earlier content would reproduce the
   original revision's id under a different number — two revisions sharing one identity.
   `created_at` and provenance are excluded. Both lists are exported as constants and
   asserted.
4. **MIDI channel is never mapped to `voice_id`.** A channel may carry a divided-pickup
   string, device routing, or an articulation; equating it with a voice manufactures
   musical structure from a transport detail.
5. **Unmatched note-ons are rejected, never synthesized.** DO-006 preserved them
   deliberately as evidence; inventing an ending would destroy that. Pairing is FIFO by
   (channel, note), documented and tested.
6. **The repository is not the invariant authority.** Three tests prove it accepts an
   orphan revision numbered 9, stores an unverifiable digest, and contains no lineage
   vocabulary. Domain policy lives in `CanonicalRevisionService` so a future persistent
   adapter does not have to reimplement it.
7. **`canonical-music` moved `partial` → `implemented` only in A5**, and a test imports
   every artefact the promotion claims rather than taking the status at its word.

## Not delivered

**All four projections remain `planned`.** Piano roll, MIDI, notation, and TAB are
DO-007B. Nothing in this tranche projects anything, and no projection payload type
exists yet.

**No persistence.** `InMemoryCanonicalScoreRepository` only. No database, ORM,
filesystem authority, or network service — the port exists so the storage decision can be
made later against a settled model.

**No schemas or fixtures for the score contracts.** Deferred to DO-007B's conformance
commit, where they land alongside the projection schemas.

**The isolated Performance proof keeps its test double.** `test_projection_proof.py`
proves what Performance does at the seam without depending on Core's implementation; a
test asserts it still uses a double, so the two suites do not quietly converge.

## Next

DO-007B — projection contracts and registry, piano roll, semantic-minimum MIDI,
structural notation, structural TAB, schemas, and governance closure. It consumes the
contracts accepted here and must not redefine documents, revisions, ingestion policies,
event provenance, or timing conversion.

ADR-0008 remains **Proposed** until governance accepts it.
