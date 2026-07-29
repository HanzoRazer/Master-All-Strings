# Projection Authority Boundary

Why piano roll, notation, TAB, and MIDI are **views** of canonical music and never
stores of it.

Companion to [ADR-0008](../decisions/ADR-0008-CANONICAL-SCORE-REVISION-IDENTITY.md) D10
and [ADR-0007](../decisions/ADR-0007-EMBEDDED-PERFORMANCE-RUNTIME.md) D8.

## The rule

```text
              CanonicalScoreRevisionV1          <- the only authority
                        |
        +---------+-----+-----+---------+
        v         v           v         v
   piano roll  notation      TAB      MIDI      <- four readings, zero authority
        |         |           |         |
        +---------+-----+-----+---------+
                        |
                        X   no path back
```

A projection cites a revision. A revision never cites a projection. There is no
function anywhere that accepts a projection payload and returns a revision.

## Why this needs saying

Every one of these views is a plausible place to put a score, and each becomes one
quietly:

- A **piano roll** is an editable grid. Give it a note list it can write to and it is
  the score database by the end of the week.
- **Notation** looks the most like "the music" to a musician, so a notation editor
  feels like the natural home for the authoritative version.
- **TAB** is what a guitarist reads, which makes it tempting to treat fret positions as
  the real content rather than a derivation.
- **MIDI** is a file format people already exchange, so "just save the MIDI" is a short
  step from "the MIDI is the score."

Each would work, briefly. Then a second one appears, the two disagree, and there is no
principled way to say which is right — because both are authorities and neither cites
the other.

## What a projection result must carry

```text
request_id
document_id
revision_id            <- the exact state this reading is of
projection_type
projection_version     <- the projector changed, the music did not
fidelity_level
payload
warnings
unsupported_features
projection_digest
```

`projection_version` is separate from `revision_id` on purpose. A projector improving
its output must not look like the music changing.

## Fidelity is declared, never assumed

| Level | Means |
| --- | --- |
| `STRUCTURAL` | positions, ordering, and traceable identity — no interpretation claimed |
| `SEMANTIC_MINIMUM` | a correct minimal semantic reading of the revision |
| `FULL` | the complete domain reading |

What DO-007B delivers, and nothing more:

| Projection | Fidelity | Explicitly does not claim |
| --- | --- | --- |
| piano roll | complete for supported `MusicalEvent` fields | editing; it is read-only |
| MIDI | `SEMANTIC_MINIMUM` | playback, device I/O, scheduling, Standard MIDI File bytes |
| notation | `STRUCTURAL` | engraving, layout, beaming, harmonic spelling intelligence |
| TAB | `STRUCTURAL` | optimal or recommended fingering |

A projection that cannot represent something reports it in `unsupported_features`
rather than approximating. `cents_offset` is the running example: preserved exactly in
the piano roll, reported as `MICROTONAL_PLAYBACK_NOT_RENDERED` by MIDI,
`MICROTONAL_NOTATION_NOT_SPELLED` by notation, and `MICROTONAL_POSITION_UNRESOLVED` by
TAB when MSME cannot represent it. In no case is the note silently treated as
equal-tempered.

## TAB and the temptation to pick

`generate_candidates` returns every playable position in deterministic enumeration
order, and its docstring is explicit that index zero carries no preference. TAB
projection must honour that.

| Status | Means |
| --- | --- |
| `OBSERVED_POSITION` | a divided pickup reported the string, and it agrees with the profile |
| `DETERMINISTIC_RESOLUTION` | exactly one candidate exists under the requested policy |
| `UNRESOLVED_MULTIPLE_CANDIDATES` | several are playable; no policy authorized to choose |
| `UNPLAYABLE_ON_PROFILE` | no candidate exists for this pitch on this instrument |
| `MISSING_INSTRUMENT_PROFILE` | the request did not supply the context TAB requires |
| `OBSERVED_STRING_PROFILE_CONFLICT` | the observed string cannot produce this pitch here |

Taking the first candidate would produce output that looks complete and is arbitrary —
worse than saying "unresolved", because it cannot be distinguished from a real answer.
Fingering optimization is a policy decision, and no Dev Order has authorized one.

## How edits get in

Not through a projection.

```text
Creative Engine
    ScoreEditProposal        (Creative-owned; intent)
            |
            v
    ScoreEditCommandSet      (Core-owned, Creative-produced; validated vocabulary)
            |
            v
    Musical Core  ->  new CanonicalScoreRevisionV1
```

The command set is Core-owned even though Creative produces it: the engine owning the
canonical model owns the vocabulary for changing it, even when another engine speaks
it. That is the same asymmetry `ProjectionRequestV1` and `CanonicalIngestionRequestV1`
use.

An interactive piano roll is therefore legitimate — it renders a Core projection and
emits Core-owned edit commands. What it must never do is keep its own note collection
and write it back as the score.

## Enforcement

- A projection payload type is not accepted by any revision-creating function.
- `ProjectionResultV1` is produced only by Musical Core; another engine producing one
  would be a second interpretation authority.
- `ProjectionRequestV1` may be produced by Creative, Educational, or Performance —
  requesting a reading is not authority over it.
- Projection operations do not mutate their source revision, asserted by test.
