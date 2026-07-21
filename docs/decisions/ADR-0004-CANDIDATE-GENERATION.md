# ADR-0004: Candidate Generation

## Status
Accepted

## Context

The Musical Spatial Mapping Engine must answer two different questions. *Where can this note be played?* is a question about the instrument. *Which position should we recommend?* is a question about preference and, eventually, pedagogy. Collapsing them produces an engine that cannot explain its own output.

This ADR records the decisions settled for the first of those questions.

## Decision

Candidate generation produces every valid playable position for one canonical musical event on one configured instrument, and nothing else.

### Ambiguity is preserved

Several playable positions is the normal case, not a problem to resolve. All of them are returned. Selection is a separate operation in a later Dev Order.

### Order is enumeration, not ranking

Candidates are sorted by `(display_order, relative_semitone_position)`. This is a stable enumeration and carries no meaning about quality, recommendation, or ease. Index zero is not the preferred position. `display_order` is primary deliberately: ordering by position first would implicitly privilege lower positions, which is a preference judgment generation is not authorized to make.

### `display_order` is carried on the candidate

`SpatialPosition` records the `display_order` of its originating string. A candidate must stay interpretable outside the sequence that produced it: if enumeration order were carried only by tuple position, permuting a candidate list would destroy it, and a permutation-stable selector could not reproduce it.

### Unplayable is an answer, not an error

An event with no playable position returns an empty tuple. That is a true statement about the instrument. Errors are reserved for unsupported modes and internally inconsistent data.

### Bounds take the tightest declared limit

The effective upper bound is the minimum of the limits that are actually declared: the per-string maximum, `physical_fret_count` (fretted only), the constraint maximum, and the MIDI domain. An omitted optional maximum is not incomplete tuning data — the open pitch still defines the string and MIDI supplies a finite ceiling. Strict validation rejects malformed declared values; it does not reinterpret an optional field as required.

### The capo becomes the effective nut

Position relative to the capo determines open-string identity; position from the nut determines geometry. A note stopped at the capo is therefore an open string with a nonzero distance from the nut. The contract carries both quantities separately for exactly this reason.

A fractional capo is rejected on fretted instruments. A capo clamps behind a fret, so a fractional value is internally inconsistent — and it is silently corrupting rather than obviously wrong: positions from the nut remain integral, so nothing else would flag it, while no candidate could ever reach relative position zero and the instrument would quietly lose every open-string candidate.

### Semitone anchors and microtonal displacement stay separate

`relative_semitone_position` and `physical_semitone_position_from_nut` are semitone anchors. `cents_offset` carries microtonal displacement separately and unchanged. `normalized_position` and `distance_from_nut_mm` derive from the anchor and ignore the offset.

Generation answers where the canonical note is anchored on the instrument. It does not certify performance technique. Whether a cents offset requires bending, alternate setup, or is unattainable belongs to a later feasibility layer, and displacing the geometry by the offset would assert where a finger must land.

### Fretless is first-class

Exactly one candidate per viable string, never a sampled continuum. `IMAGINARY_SEMITONE` for exact semitone targets — authoritative for ordinary chromatic fretless instruction — and `CONTINUOUS_POSITION` for cents-displaced ones. The reference type describes the position measured from the nut, which the semitone markers are anchored to.

### One `StringProfile` per distinct playing location

Generation emits one candidate per admissible `StringProfile`. It assumes a profile
declares one entry per distinct playing location — a course representative, not each
physical string. The shipped mandolin profile follows this: four entries for four
courses, with `string_id` equal to `course_id`.

A profile that instead declares each physical string of a unison course separately
produces one candidate per string, and those candidates are identical in course,
pitch, and fret while differing only in `string_id` and `display_order` — two entries
for one playing location. Collapsing them would require deciding which representative
survives, which is a selection judgment this phase does not own.

The assumption is recorded rather than enforced: no shipped profile violates it, and
adding validation would reject a legitimate future profile that models physical
strings deliberately. Distinguishing physical strings from logical courses is
deferred to a Dev Order that can define the semantics for both.

### Hybrid fails explicitly

`FingerboardMode.HYBRID` raises rather than being silently treated as fretted or fretless. Schema permission is not executable behavior. Support requires a representative profile, a defined transition model between discrete and continuous regions, evidence or an explicit product decision, and dedicated tests.

## Consequences

Generation is `O(n)` in the number of strings and holds no state. Its output is a complete, interpretation-free candidate set that a later selector can rank without re-deriving playability.

Because ordering carries no preference, any consumer treating index zero as a recommendation is reading meaning that is not there. The public docstring states this, and the constraint is worth preserving under future change.

Structured rejection diagnostics are reserved for a later Dev Order: `CandidateRejectionCode` exists but is deliberately not surfaced, since exposing it would require a second public result shape.

## Rejected alternatives

**Returning a single position.** Would embed selection policy in generation and discard the ambiguity that makes the engine useful for instruction.

**Ordering by position before string.** Reads as "prefer lower positions," which is a preference, not a property of the instrument.

**Folding `cents_offset` into the position.** Would make the contract's separate `cents_offset` field redundant and would assert performance technique.

**Rejecting microtonal events on fretted instruments.** Would require an arbitrary tolerance and an interpretive judgment about playability.

**Inferring hybrid behavior from fretted and fretless.** Would invent semantics with no supporting evidence.
