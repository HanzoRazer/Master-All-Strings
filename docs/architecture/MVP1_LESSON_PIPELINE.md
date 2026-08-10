# MVP-1 Lesson Pipeline

## Authoritative flow (today)

```text
MIDI file bytes
   ↓
MidiLessonImporter
   ↓
LessonAssignmentV1
   ↓
validate_assignment
   ↓
LessonAssignmentResolver
   ↓
canonical MusicalEvent (+ playback / spatial requests)
   ↓
MSME candidate generation
   ↓
validated teacher override OR MVP enumeration-order auto-select
   ↓
SelectedSpatialEvent
   ↓
temporal / scrolling-fretboard semantic projection
   ↓
zero-authority renderer consumer
```

MIDI is an import format only. It is not the lesson-domain aggregate root.

## Governing statement

MVP-1 shall normalize all lesson input through a portable, versioned
`LessonAssignment` envelope before canonical musical resolution. Networking is
deferred, but the object shall be serializable, reloadable, teacher-override
capable, and transport-neutral so later device-to-device communication does not
require redesign of the musical, spatial, timing, selection, projection, or
rendering pipeline.

## Future transport diagram

Transport terminates before canonical resolution:

```text
Teacher device / classroom server / cloud (future)
   ↓  transmit LessonAssignmentV1 JSON only
Student device / another guitar (future)
   ↓
deserialize LessonAssignmentV1
   ↓
validate / resolve   ← transport ends here
   ↓
canonical MusicalEvent → MSME → selector → projection → renderer
```

The networking layer may own delivery, addressing, authentication, retry, and
discovery. It must not alter lesson semantics, MSME candidates, selection,
timing, or rendering.

## Equivalence gate

For equivalent musical content:

```text
legacy conceptual path: MIDI → MusicalEvent
MVP-1E path:            MIDI → LessonAssignmentV1 → MusicalEvent
```

must produce identical MSME candidates and identical automatic fingering for the
same instrument profile and policy. Routing metadata must never participate in
that comparison.
