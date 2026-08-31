# Score Projection Boundary (DO-013 / MVP 2C)

**Subsystem:** Musical Core projection authority + presentation rendering
**Status:** Implemented — MVP 2C

## Why this document exists

MVP 2B gave the browser one clock. MVP 2C gives it one *score*. The risk in that
step is subtler than the timing one: a view that draws notes is one short step
from deciding what the notes are.

Three separate identities have to stay separate, and most of this document is
about keeping them apart:

```text
lesson content_id     what a teacher authored
document_id           the musical work that lesson denotes
revision_id           one immutable state of that work
```

## Two identities, minted by different things

A stable authored lesson is a stable musical **work**. Re-exporting it must not
invent a new work each time, so the document identity is derived from the
lesson's own stable `content_id`:

```text
content_id   half_steps_one_string
document_id  score-half_steps_one_string
```

That mapping is deterministic and lives in a production ID authority. It is
**not** a content digest — and the distinction is load-bearing:

* `document_id` answers *which work is this?* It survives edits to the music.
* `revision_id` answers *which state of that work?* Musical Core mints it from
  the document identity plus the canonical musical content.

So editing a lesson's notes keeps `document_id` and produces a new
`revision_id`. Renaming the lesson would produce a different work, which is the
correct reading: identity follows the authored name, not the notes.

Because `created_at` and `provenance` are excluded from Core's content digest,
the revision identity is reproducible across exports without freezing a
timestamp. Identical musical content yields an identical `revision_id`, which is
what makes the exported artifacts byte-stable.

## Authored content is not captured performance

Musical Core already has an ingestion path, and it does not fit here.
`CanonicalIngestionRequestV1` requires `capture_id`, `source_session_id`,
`raw_capture_digest`, and `capture_origin_ns` — it describes music that was
*observed being played*. An authored lesson was not played by anyone.

Routing authored content through it would mean fabricating capture evidence to
satisfy required fields. The revision would be real and its provenance would be
a lie, which is worse than having no revision at all.

Authored lessons therefore use `CanonicalRevisionService.create_document_with_revision()`
with `ScoreSourceKind.MANUAL_CONSTRUCTION`. Same Core authority, honest
provenance.

## The revision is exported, not just computed

A citation nobody can resolve is decoration. Each lesson exports its revision
beside its projections:

```text
web/mvp1/projections/<lesson>/
    canonical_revision.json
    tab.json
    notation.json
```

`tab.json` and `notation.json` both cite `canonical_revision_id`, and
`canonical_revision.json` carries that exact ID. The artifact is a serialization
of `CanonicalScoreRevisionV1` — not a second score model reconstructed for
export — so deserializing it reproduces the same identity and content.

This is deliberately not a general score database. Runtime still uses the
in-memory repository; the durable boundary is the artifact.

### Compatibility note for existing consumers

MVP 2C **adds** a per-lesson directory. It moves nothing.

```text
web/mvp1/projections/<lesson>.json        unchanged  fretboard projection
web/mvp1/projections/<lesson>/            new        score artifacts
```

The flat per-lesson file every DO-008 and DO-012 consumer already reads keeps its
path, its name, its schema, and its `behavior_digest`. A consumer that never asks
for the score sees no difference.

Two consequences worth stating for anyone reading the directory rather than a
known path:

- `projections/` now contains **directories as well as files**. Code that
  enumerates it must filter. Everything in this repository addresses artifacts by
  explicit path, and the fixture guard globs `*.json`, which does not match
  directories — but an external consumer listing the folder would now see entries
  that are not lesson projections.
- The score artifacts are optional to a lesson. If they are absent or disagree
  about their revision, the score views disable themselves and report why; the
  fretboard, transport, media, Zone, and practice surfaces are unaffected.

There is no migration to perform, and no consumer needs to change to keep
working.

## What each projection is allowed to know

```text
Canonical revision
      │
      ├──────────────────────┐
      ▼                      ▼
  Notation            Selected spatial evidence
                             │
                             ▼
                            TAB
```

**Notation reads canonical music only.** Pitch, duration, meter, measures. It
never sees a string or a fret, and a test proves it: changing the selected
realization must leave the notation digest untouched. Notation of a melody is
the same notation whether you play it in first position or twelfth.

**TAB reads canonical music plus the *selected* spatial evidence.** It never
calls MSME, never ranks candidates, and never falls back to candidate zero. If
selection did not happen, TAB says so:

```text
selected realization present   PLAYABLE
explicitly unplayable          UNPLAYABLE
no selected evidence           UNRESOLVED
```

An `UNRESOLVED` row is more useful than a guessed one. A guess would be
indistinguishable from a real fingering decision, and the learner would practise
it.

## What notation is allowed to infer

Very little, on purpose.

**Rests come only from global silence.** A rest is derived for a span where *no*
canonical note is sounding — the complement of the union of all sounding
intervals. The naive version, looking at gaps between consecutive event starts,
invents rests during held notes; the bundled `simultaneous_notes` lesson has
genuine overlap and would produce exactly that error.

Because `voice_id` is null throughout the current corpus, per-voice rests cannot
be allocated without inventing voices. Where a faithful rendering would need
one, notation reports:

```text
VOICE_SPECIFIC_REST_INFERENCE_UNAVAILABLE
```

**Durations are exact or unsupported.** Whole through thirty-second, plus a
single dot, and only when the tick count divides exactly at the current PPQ.
Nothing is rounded. A duration that would need a tuplet or a double dot reports
`UNSUPPORTED_DISPLAY_DURATION`, and the exact `duration_ticks` stays in the
projection as evidence.

Rounding would be the tempting failure here: it produces something that renders,
looks plausible, and is wrong about the music.

**Accidentals are display spelling, not canonical spelling.** V1 uses a
deterministic sharp-preferred table, recorded as
`display_policy = SHARP_PREFERRED_V1`. This is presentation only; when the
canonical model gains enharmonic evidence, that becomes authoritative and this
policy yields to it.

**Ties are never inferred.** Two adjacent notes of the same pitch are two notes.
A tie asserts that they are one sounded event, and nothing in the canonical model
says so. Until it does, a tie is an unsupported feature rather than a guess.

## The rendering boundary

Core produces notation *semantics*: measures, display durations, spellings,
unsupported-feature records. The browser draws them.

`notation-view.js` and `tab-view.js` place glyphs, lines, and hit targets. They
do not compute durations from MIDI, decide measure membership, or spell pitches.
If the browser had to answer a musical question, the answer belonged upstream.

There are no frontend dependencies. The SVG renderer is narrow by design — the
alternative was adding a full engraving library and letting its data model
become the de facto notation contract.

## Timing is borrowed, not rebuilt

TAB and notation are followers of the DO-012 Teaching Timeline. There is no
`TabClock`, no `NotationClock`, no `ScoreTransport`. Active events come from
`TeachingPlayheadStateV1`, and clicking a score event seeks the existing
`Transport`.

Playback rate and looping change how time progresses, never what the score is: a
test asserts the projection digest is identical at 0.50×, 0.75×, 1.00×, and
1.50×, and that repetitions do not clone projection records.

## Read-only, and why that is the whole point

No dragging, inserting, deleting, retiming, or refingering. The score views
display a canonical revision; they cannot produce one.

A future Creative/Smart Entry tranche may add authoring, and it will do so
through canonical revision commands — creating a *new revision* — rather than by
letting a view mutate what it is displaying. Keeping the read-only boundary
sharp now is what makes that possible later without unpicking this.
