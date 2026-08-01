# Canonical Score Revision Model

Operational companion to [ADR-0008](../decisions/ADR-0008-CANONICAL-SCORE-REVISION-IDENTITY.md).
The ADR ratifies the identity model; this explains how it is built and driven.

> **Status.** DO-007A delivers documents, revisions, lineage, digests, the repository
> port, and real ingestion. Projections arrive in DO-007B. Nothing here is persisted to
> a database, and no engraving, fingering, or playback is claimed anywhere.

## The two identities

| | Answers | Lifetime |
| --- | --- | --- |
| `ScoreDocumentV1` | *which work?* | survives every edit |
| `CanonicalScoreRevisionV1` | *which exact state of it?* | never changes once created |

A projection that cited only a document would be unreproducible, because the document
moves. A system with only revisions could not express "the same piece, later."

## Diagram 1 — Capture to projections

```text
  RawPerformanceCaptureV1            [Performance Engine — evidence, immutable]
            |
            |  CanonicalIngestionRequestV1   (Core-owned, Performance-produced)
            v
  CanonicalIngestionService          [Musical Core]
            |
            +--> ScoreDocumentV1              document_id minted here
            |
            +--> CanonicalScoreRevisionV1     revision_id minted here
            |         content_digest
            |         provenance ---> SourceEventProvenanceV1 per event
            |
            v
  CanonicalIngestionResultV1         document_id + revision_id returned
            |
            v
  ProjectionRequestV1 -----> piano roll | notation | TAB | MIDI
                                   all four cite ONE revision_id
```

The raw capture is never modified. Ingestion reads it and cites it; that is the whole
of the relationship.

## Diagram 2 — Revision lineage

```text
  rev-a1b2c3...            rev-d4e5f6...            rev-7890ab...
  revision_number 1        revision_number 2        revision_number 3
  parent = None      <---- parent                   parent
        ^                        ^                        ^
        |                        |                        |
        +------------------------+------------------------+
                                 |
                        ScoreDocumentV1
                        document_id = score-...
                        current_revision_id = rev-7890ab...
                        revision_count = 3
```

Revision 1 has no parent. Every later revision requires one belonging to the same
document. Numbers are contiguous — a gap means a revision was lost, which the service
refuses rather than tolerates.

## Diagram 3 — Where identity comes from

```text
  canonical events + tempo map + meter map + ticks_per_quarter
                    |
                    v
       canonicalize (deterministic ordering)
                    |
                    v
       serialize_revision_content  (excludes volatile timestamps)
                    |
                    v
       sha256  ->  content_digest
                    |
                    v
       "rev-" + first 24 hex chars  ->  revision_id
```

Two callers submitting the same content in different order produce the same digest and
therefore the same revision id. The full digest is stored alongside the shortened id.

Every field of `CanonicalScoreRevisionV1` carries a recorded decision about the digest —
`DIGEST_INCLUDED_FIELDS`, `DIGEST_EXCLUDED_FIELDS`, or `DIGEST_DERIVED_FIELDS` — and a
test asserts the three account for the dataclass exactly. A field added without a
decision would silently fall outside identity, so two revisions differing only in it
would share one `revision_id` and one of them would be unreachable. Nothing else would
notice; the test fails on the next field instead of on the next incident.

Because the id carries only the first 24 hex characters of the digest, the repository is
where a prefix collision would surface, and it is checked there: saving a revision whose
id already exists compares the **full digest**, accepts a match as the ordinary retry,
and raises `REVISION_ID_COLLISION` on a genuine divergence. Comparing whole objects
instead would reject a legitimate retry, because the digest excludes `created_at`.

Document ids do not come from content — a document survives its content changing — so
they come from an injected `DocumentIdAuthority`: deterministic in tests, UUID-backed in
normal use, never a timestamp.

## Timing: what the conversion is and is not

Captured performance carries monotonic nanoseconds. Canonical music carries integer
ticks. Something has to bridge them, and the honest name for it matters.

```text
elapsed_ns = event_ns - capture_origin_ns
ticks      = round_half_away_from_zero(elapsed_ns * ppq, mpq * 1000)
```

Integer arithmetic throughout, and the tie rule is named rather than inherited: halves
round **away from zero**, never Python's `round`, which is banker's rounding and would
be impossible to reimplement correctly by accident. The rule lives in one module
(`core.score.rounding`) because tempo conversion needs the same one — `tempo_from_bpm`
feeds the tempo map, the tempo map is inside the digest, and two derivations of
canonical values rounding differently would mean two implementations disagreeing about
a revision id.

**This is tick-grid rounding.** At 120 BPM and 960 PPQ one tick is about 0.52 ms, so the
rounding is numerical, not musical.

**This is not quantization.** Nothing is snapped to a beat, a subdivision, a note value,
a measure, a rhythmic template, or an inferred groove. A note played 30 ms late stays 30
ms late.

The policy refuses to guess its inputs: a missing, zero, non-finite, or ambiguous tempo
is rejected rather than defaulted to 120 BPM. A note whose duration rounds below one
tick is rejected as `DURATION_BELOW_ONE_TICK` rather than silently widened.

Every conversion keeps its own evidence in provenance — source nanoseconds, converted
ticks, PPQ, tempo, rounding policy, and rounding delta — so the arithmetic can be
checked rather than trusted.

## Provenance: keeping capture evidence without contaminating the event

`MusicalEvent` stays a representation-independent pitch-and-time contract. Everything
instrument-specific lives beside it:

```text
CanonicalScoreRevisionV1
    provenance: RevisionProvenanceV1
        event_provenance: (SourceEventProvenanceV1, ...)   deterministic order

SourceEventProvenanceV1
    canonical_event_id
    source_capture_event_ids        the note-on and note-off that produced it
    source_channel
    observed_source_string          from a divided pickup, or None
    source_capture_time_ns
    source_release_time_ns
    converted_start_tick
    converted_duration_ticks
    rounding_delta_start_ns
    rounding_delta_duration_ns
```

**MIDI channel is not mapped to `voice_id`.** A channel may carry a divided-pickup
string, device routing, or an articulation; voices may share a channel, and channels get
reused. `DIRECT_EVENT_IMPORT_V1` leaves `voice_id` as `None` unless the input states a
canonical voice explicitly.

**Observed string stays observed.** It reaches TAB projection as `OBSERVED_POSITION`,
distinct from `COMPUTED_CANDIDATE`, `DETERMINISTIC_RESOLUTION`, and
`UNRESOLVED_CANDIDATES`. An observed string still has to agree with the pitch under the
cited instrument profile and tuning; when it does not, the result reports
`OBSERVED_STRING_PROFILE_CONFLICT` rather than overwriting either source.

## Note pairing

Captured MIDI is note-on and note-off events; canonical music is start plus duration.
Pairing is **FIFO by (channel, MIDI note)**, documented and tested rather than inferred.

| Case | Outcome |
| --- | --- |
| matched on/off pair | one `MusicalEvent` |
| note-on never released | rejected, `UNMATCHED_NOTE_ON` |
| note-off with no open note | rejected, `UNMATCHED_NOTE_OFF` |
| duration rounds below one tick | rejected, `DURATION_BELOW_ONE_TICK` |

Nothing is synthesized. DO-006 preserved unmatched note-ons deliberately as evidence of
what happened; inventing an ending here would destroy that and would violate ADR-0007
D15. Ingestion may still succeed partially, but the result reports what it rejected and
whether the revision is complete relative to accepted input.

## Idempotency

The key is `request_id` plus a **request fingerprint**: a digest over every field that
changes what the ingestion produces. Repeating an identical request returns the existing
result rather than creating a second document or revision. Reusing a `request_id` with
any different result-affecting field is rejected as `INGESTION_IDEMPOTENCY_CONFLICT` —
the same name meaning two things is a defect, not a new version.

The fingerprint covers `capture_id`, `raw_capture_digest`, `capture_origin_ns`,
`tempo_microseconds_per_quarter`, `meter`, the effective `ticks_per_quarter`, the
ingestion policy version, and a digest of the submitted source events.

It has to cover more than the capture digest. The capture digest says which take was
played; it says nothing about the tempo, meter, tick grid, or capture origin the caller
asked Core to interpret that take under, and every one of those changes the revision.
Keying on the capture digest alone meant replaying one capture under a corrected tempo
came back as a duplicate carrying the *uncorrected* revision — silently, and reported as
a success. The source events are fingerprinted rather than trusted to follow the capture
digest for the same reason: the digest is a value the caller asserts, the events are
what Core actually converts.

`requested_at` is excluded on purpose — a retry may legitimately restamp it, and letting
that split the key would defeat the retry safety the key exists for. So are
`source_session_id`, the instrument and tuning profile ids, and
`requested_projection_types`, none of which reach the revision or the result today. When
a profile or a projection request starts affecting what Core stores, it joins the
fingerprint.

Those exclusions are a named list (`FINGERPRINT_EXCLUDED_FIELDS`), not prose, and a test
asserts that every field of `CanonicalIngestionRequestV1` is either fingerprinted or on
it. This is the same drift the digest guard prevents, on the other side of the seam: a
new request field that affects what Core stores but that nobody adds to the key does not
raise and does not fail any existing test — it just quietly stops telling two different
ingestion intents apart, which is the exact defect this key was rewritten to fix.

A rejected request reserves its `request_id` too. A rejection creates nothing, but the
id has been spent; leaving it free would mean the conflict guard only worked on the
happy path. Re-sending the same rejected request is still rejected rather than
conflicting.

A caller that genuinely wants a second interpretation of one capture — a corrected
tempo, a different meter — issues a new `request_id`. That is a distinct ingestion
intent, and it produces a distinct document and revision.

## Persistence

`CanonicalScoreRepositoryPort` with `InMemoryCanonicalScoreRepository` behind it. No
database, ORM, filesystem authority, or network service in DO-007. The port exists so
the storage decision can be made later against a settled model rather than earlier
against a guess.

**Creating a document and its origin revision is one port method, not two calls.** A
document is born already pointing at its origin, so no ordering of two writes is
correct: creating the document first publishes a `current_revision_id` that resolves to
nothing, and saving the revision first is refused because its document does not exist.
`create_document_with_origin_revision` owns that atomicity — the in-memory adapter by
validating fully before it writes anything, a future persistent one inside a
transaction. Leaving the sequencing to the service made the requirement invisible to
whoever writes that adapter, and the service's own comment claimed a guarantee the
ordering did not provide.

There is **no bare `create_document`**. A `ScoreDocumentV1` requires a
`current_revision_id`, so a lone create could only ever store a dangling pointer; keeping
it as a convenience would have left the failure the paired method prevents one call
away. A document is always created with its origin, and a new document's history is
therefore exactly one revision rather than none.

Revision sameness is decided by `content_digest`, and **first write wins**: a retry
differing only in `created_at` or `provenance` is the same revision, the stored one is
kept, and the stored one is what comes back. A caller should read the returned object
rather than assume the submitted one was written.

`tests/core/score/test_repository_contract.py` is the adapter conformance suite. A new
adapter is added to its `ADAPTERS` list and inherits every rule above. That indirection
is necessary because `isinstance` against the `runtime_checkable` port compares method
*names* only — a hollow class with no behaviour passes it, which the suite demonstrates
rather than asserts in prose.
