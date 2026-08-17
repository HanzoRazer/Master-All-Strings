# Lesson Media — Presentation Support Subsystem

**Dev Order:** DO-011 / MVP 2A

## Role

Lesson Media is an **application/presentation subsystem**. It may explain
canonical musical concepts through text, image, or video teaching aids. It
**cannot** define, mutate, or supersede:

* LessonAssignment musical content;
* Musical Core events / digests;
* MSME candidates;
* Zone Harmony semantics;
* Performance capture / alignment;
* Educational Practice*V1 evaluation.

## Authority diagram

```text
LessonAssignment / Educational intent
              │
              ├──────────────┐
              ▼              ▼
      Musical pipeline    Lesson Media (sidecar)
              │              │
              ▼              ▼
      Fretboard/Zone      Explanation
              │              │
              └──────┬───────┘
                     ▼
                Student UX
```

## Contract seam

`LessonAssignmentV1` remains frozen at `1.0.0`. Media associations live in a
**sidecar catalog** keyed by lesson/content identity (`demo_id` / `content_id` /
`assignment_id` as appropriate). A future lesson-contract revision may absorb
media intentionally; DO-011 does not.

## Transport separation

Musical transport remains authoritative for MIDI playback, practice loop,
fretboard position, expected events, and the reference audio scheduler.

Media owns its own play/pause/seek/rate/segment-loop state. Synchronization in
MVP 2A is **coordinated UX**, not a shared clock.

## Failure policy

Missing or unavailable media must never prevent the musical lesson from loading.
Catalog/build validation may hard-fail unresolved required references; the
browser soft-fails with an explicit diagnostic.

## Governance

No new engine row is added to `governance/engine_architecture_v1.json` in DO-011.
If media later becomes cross-engine authority, register it then.
