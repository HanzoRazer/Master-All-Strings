# Synchronized Teaching Timeline (DO-012 / MVP 2B)

**Subsystem:** Presentation synchronization
**Status:** Implemented — MVP 2B
**Authority:** Derived presentation state. Owns no musical content.

## Why this document exists

MVP 2A left the browser with one real transport (`web/mvp1/transport.js`) and a
set of surfaces that each decided independently whether to care about it. The
fretboard read transport position every animation frame. Lesson Media ignored
the transport entirely and drove an HTML `<video>` element on its own. Zone
styling was a static toggle with no temporal dimension.

Adding TAB and standard notation (DO-013) to that arrangement would have meant a
third and fourth surface each inventing its own relationship to musical time.
DO-012 exists to make that relationship a named, reusable seam *before* more
consumers arrive.

## The rule

```text
There is exactly one musical transport.
Everything a learner sees is a follower of it.
```

`Transport` is the sole authority for position, playing state, playback rate,
seek, loop bounds, and repetition count. The Teaching Timeline **observes**
that authority and distributes derived state. It never advances time itself, it
holds no `setInterval`, and it has no notion of "current position" that is not
read from `Transport`.

## Authority map

```text
Python / Musical Core timing
      │  ticks_to_seconds()
      │
      ├── tick↔seconds anchor table  ──────────┐
      │   (static export, per lesson)          │
      │                                        │
Existing Transport (browser)                   │
      │  subscribe() / snapshot()              │
      ▼                                        │
Teaching Timeline Coordinator  ◄───────────────┘
      │
      ├── TeachingTimelineStateV1
      ├── TeachingPlayheadStateV1
      ├── Fretboard active state
      ├── Zone active state
      └── Media follower
              │
              ├── MediaTimelineBindingV1  (lesson media sidecar / API)
              ├── drift measurement
              └── SynchronizationHealthV1

Educational ISOLATE_PASSAGE
      │
      ▼
presentation adapter  (focus ticks → seconds via anchors)
      │
      ▼
existing Transport.setLoop()
```

## Where musical time comes from

The browser does **not** convert ticks to seconds. That conversion is Musical
Core's (`core.score.musical_timeline.ticks_to_seconds`), and duplicating it in
JavaScript would create a second implementation of canonical timing that could
drift from the first.

Instead the static export carries a **timeline anchor table** authored in
Python:

```json
"timeline_anchors": [
  {"tick": 0,    "seconds": 0.0},
  {"tick": 960,  "seconds": 0.5},
  {"tick": 4320, "seconds": 4.5}
]
```

Anchors are emitted at every tempo-change boundary plus the lesson start and
end. Between two anchors the tempo is constant by construction, so the mapping
is exactly linear and the browser may interpolate. The interpolation is
deterministic and monotonic; it is arithmetic *within* a Core-authored mapping,
not an independent derivation of it.

This is what lets `TeachingTimelineStateV1` and `TeachingPlayheadStateV1` carry
a real `position_tick` without a JavaScript tick converter.

## Media synchronization

Media is a follower, and only when explicitly told to be.

| Mode | Behavior |
|---|---|
| `DETACHED` | Exactly MVP 2A. Media plays, pauses, seeks, and rates on its own. The shared transport is not touched. |
| `SYNCHRONIZED` | Media position, play state, and rate are derived from the shared transport through a binding. |

Synchronization requires a `MediaTimelineBindingV1`. There is no inference from
titles, durations, or filenames — media that has no binding cannot be
synchronized, and says so.

The V1 mapping is affine and 1:1:

```text
media_time = media_anchor_seconds + (lesson_time - lesson_anchor_seconds)
```

No warping, no stretch markers, no elastic time. A binding may declare
`lesson_end_seconds` / `media_end_seconds`; outside that range the follower
reports `OUT_OF_BINDING_RANGE` rather than extrapolating.

## Drift is evidence, not a secret

Following an HTML media element means measuring how far it actually is from
where it should be. `SynchronizationHealthV1` carries that measurement:

```text
|drift| <= 40 ms          → SYNCED,     correction NONE
40 ms < |drift| <= 150 ms → DRIFTING,   correction RESAMPLE
|drift| > 150 ms          → CORRECTING, correction HARD_SEEK
```

Thresholds are declared constants in `presentation/synchronization.py`, not
magic numbers buried in browser code.

Hard seeks happen on explicit shared seek, loop wrap, media load/resume, and
threshold breach — never continuously. Continuously assigning `currentTime`
makes video stutter and is the single most common way this kind of
synchronization goes wrong.

## Media cannot hold the lesson hostage

If media stalls, fails to load, or runs past the end of its binding:

```text
media  → DEGRADED / UNAVAILABLE / OUT_OF_BINDING_RANGE
music  → continues
```

The musical transport is authoritative. The bundled golden lesson deliberately
exercises this: a 3.0 s demonstration clip is bound to a 4.5 s lesson, so the
final 1.5 s plays with the media follower explicitly out of range while the
fretboard, Zone, playhead, and audio continue undisturbed.

## What this layer must never do

* own or create canonical score content
* create canonical event IDs — `active_event_ids` are IDs that already exist in
  the projection
* mint canonical revisions (`canonical_revision_id` is deliberately **absent**
  from DO-012; durable score projections need real revision provenance and that
  wiring belongs to DO-013)
* modify Musical Core, MSME, Zone semantics, Performance evidence, or
  Educational findings
* replace `Transport`
* become a single opaque teaching-player widget

## Educational isolate

The Educational Engine chooses `ISOLATE_PASSAGE` and reports
`focus_start_tick` / `focus_end_tick`. Those ticks are already authoritative.

Before DO-012 nothing consumed them as a loop — the browser displayed a focus
range and printed a status line. DO-012 adds the missing presentation adapter:
focus ticks resolve to seconds through the anchor table and are applied with the
existing `Transport.setLoop()`.

No Educational policy changed. The engine's findings, actions, and messages are
byte-identical; only the presentation consequence is now real.
