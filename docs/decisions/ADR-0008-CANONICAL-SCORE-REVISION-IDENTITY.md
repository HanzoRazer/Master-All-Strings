# ADR-0008 — Canonical Score Revision Identity

- **Status:** Proposed
- **Owner:** DO-007
- **Engine:** Musical Core
- **Depends on:** [ADR-0003](ADR-0003-MUSIC-CANONICAL.md) (music is canonical), [ADR-0006](ADR-0006-FOUR-ENGINE-ARCHITECTURE.md) (four engines), [ADR-0007](ADR-0007-EMBEDDED-PERFORMANCE-RUNTIME.md) (embedded performance runtime)

## Problem

Musical Core is the constitutional authority for canonical music, but it has no way to
say *which* music, or *which version of it*. What exists is `MusicalEvent` — a single
pitch with a start, a duration, a velocity, and an optional voice. There is no score
document, no revision, no lineage, and no identity that another engine can cite.

That gap is load-bearing, and DO-006 hit it directly. The Performance Engine can
capture a take and build a `CanonicalIngestionRequestV1`, but nothing can answer it:
there is no revision to mint and no document to attach one to. DO-006 proved that seam
against a test double and said so plainly. Every projection — piano roll, notation,
TAB, MIDI — is registered to Musical Core and marked `planned`, because a projection
of nothing is not implementable.

The risk of leaving it open is not that features are missing. It is that the first
component to need a score will build one where it happens to be standing. A piano-roll
editor with an editable note list, or a Performance session that treats its capture as
the score, becomes a second authority the moment it persists anything.

## Context

The registry already assigns every relevant capability to Musical Core, and the
dependency matrix already forbids Core from depending on Educational, Creative, or
Performance. What is missing is not governance. It is the object the governance
describes.

Two distinctions do the real work in this decision, and conflating either one is how
score models usually go wrong.

**A work is not a version of that work.** A player refers to "my arrangement" across
months of edits; a projection must refer to one exact state or it cannot be reproduced.
These need separate identities with separate lifetimes.

**A view is not a store.** Piano roll, notation, TAB, and MIDI are four readings of the
same content. The moment one of them can be written back directly, it stops being a
reading.

## Decision

### D1 — A score document and a score revision are different objects

`ScoreDocumentV1` is the continuing identity of a musical work. `CanonicalScoreRevisionV1`
is one immutable state of it.

```text
ScoreDocumentV1                 CanonicalScoreRevisionV1
    document_id  = score-123        revision_id        = rev-003
    current_revision_id = rev-003   document_id        = score-123
    revision_count = 3              parent_revision_id = rev-002
                                    revision_number    = 3
```

The document survives every edit. The revision never changes.

### D2 — Musical Core is the only revision authority

Only Musical Core may mint `score_document_id`, `canonical_revision_id`,
`revision_number`, and `content_digest`. Performance, Creative, and Educational may
*reference* those identities and may never generate replacements.

This is the rule DO-006 anticipated: a Performance ingestion request carries no
revision id outbound, and receives one only from Core's answer.

### D3 — Revisions are immutable

An accepted change produces a new revision id, an incremented revision number, a new
content digest, a parent reference, and a recorded provenance event. Nothing is edited
in place. Revision 1 has no parent; every later revision requires one from the same
document; revision numbers are contiguous.

### D4 — `MusicalEvent` is reused, not replaced

The existing canonical event stays exactly as it is. DO-007 adds supporting types
around it — tempo, meter, provenance — and does not duplicate `event_id`, `midi_note`,
`start_tick`, `duration_ticks`, `velocity`, `cents_offset`, or `voice_id`.

A second note model would be a second canonical music model, which is the failure this
ADR exists to prevent.

### D5 — Canonical ordering is part of identity

Events sort by `start_tick`, then `voice_id` with `None` first, then `midi_note`, then
`duration_ticks`, then `event_id`. Tempo and meter changes sort by tick. Callers may
submit unordered input; Core normalizes before digesting, so two callers who supply the
same content in different order get the same revision.

### D6 — Revision identity is content-addressed

```text
content_digest = sha256(canonical_serialization)
revision_id    = "rev-" + first 24 hex characters of content_digest
```

The full digest is always stored even though the public id uses a prefix. Document ids
are *not* content-addressed, because a document survives content changes.

Volatile values — creation timestamps — are excluded from the digest. Canonical musical
content is included in full.

### D7 — Identity comes from an injected authority, never global randomness

`DocumentIdAuthority` is injected. A deterministic implementation serves tests; a
UUID-backed one serves normal use. No timestamp is ever used as identity.

### D8 — Timing conversion is tick-grid rounding, not musical quantization

Captured performance carries monotonic nanoseconds. Canonical music carries integer
ticks. The conversion is unavoidable and is classified precisely:

> **Tick-grid rounding** — the required numerical conversion from continuous elapsed
> time into the integer tick domain `MusicalEvent` uses.
>
> **Musical quantization** — intentional movement of events toward musically meaningful
> rhythmic locations.

DO-007 authorizes the former at 960 PPQ against a declared tempo, and prohibits the
latter. Nothing is snapped to a beat, subdivision, note value, measure, rhythmic
template, or inferred groove.

Every conversion retains its own evidence — source nanoseconds, converted ticks, PPQ,
tempo, rounding policy, and rounding delta — in revision provenance, so the arithmetic
is auditable rather than asserted.

### D9 — Instrument-specific capture evidence lives in provenance, not in the event

MIDI channel and observed source string are preserved per event in
`SourceEventProvenanceV1`, attached to the revision's provenance. They do not become
fields on `MusicalEvent`, which stays a representation-independent pitch-and-time
contract.

MIDI channel is **not** mapped to `voice_id` automatically. A channel may indicate a
divided-pickup string, device routing, or articulation; voices may share a channel and
channels may be reused. Equating them would invent a musical structure the source never
stated.

### D10 — Projections are derived and can never become authority

A projection result cites `source_document_id`, `source_revision_id`, `projection_type`,
`projection_version`, and `projection_digest`. A projection payload may never be
accepted as a new canonical revision. Any future edit travels through a separate
edit-command or proposal contract.

This is what stops a piano-roll UI or a notation editor from quietly becoming the score
database.

### D11 — Fidelity is stated, never implied

Each projection declares `STRUCTURAL`, `SEMANTIC_MINIMUM`, or `FULL`. DO-007 delivers
only the levels it can defend: a complete piano roll, semantic-minimum MIDI, and
structural notation and TAB. Notation does not claim engraving; MIDI does not claim
playback; TAB does not claim optimal fingering.

### D12 — Persistence is deferred behind a port

`CanonicalScoreRepositoryPort` with an in-memory implementation. No database, ORM,
filesystem authority, or network service. Choosing storage before the model is settled
would fix the wrong thing first.

## Consequences

**Accepted.** Content-addressed revisions mean any change to canonical content changes
the revision id — including a change that a musician would consider trivial. That is
the correct behavior for a citable identity, and it means callers must not treat
revision ids as human-meaningful version numbers; `revision_number` is for that.

**Accepted.** The provenance side map grows with event count, and its determinism must
be maintained separately from the events themselves.

**Open.** `canonical-music` moves to `partial` on this ADR's arrival, because the
registry previously overstated it: an atomic event existed, a canonical score did not.
It returns to `implemented` only when documents, revisions, digests, lineage, the
repository port, and real ingestion all land and pass.

**Enabled.** Once a revision exists and is citable, Creative edits become proposals
against a known base, Educational interpretation can reference exactly what it read,
and Performance can hand a capture across a seam that answers.

## Rejected alternatives

**Store the score as a mutable document.** Rejected: a projection could then cite a
document that has since changed underneath it, making every downstream record
unreproducible.

**Make the revision id a sequence number only.** Rejected: sequence numbers cannot
detect corruption or duplicate content, and two divergent edits could produce the same
number.

**Put channel and string on `MusicalEvent`.** Rejected under D9: it contaminates a
universal contract with guitar-specific capture detail that most consumers must then
ignore.

**Map channel to voice.** Rejected: it manufactures musical structure from a transport
detail, and would be indistinguishable from a real voice assignment afterward.

**Let a projection payload be submitted as a revision.** Rejected under D10: it is the
exact mechanism by which a view becomes a second store.

**Wait for a persistence choice.** Rejected under D12: the repository port makes the
model testable now, and a storage decision made before the model is settled optimizes
the wrong constraint.
