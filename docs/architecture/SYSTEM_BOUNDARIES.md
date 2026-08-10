# System Boundaries

## Musical-event core

Owns canonical musical facts: pitch, timing, duration, velocity, voice identity, and optional cents offset.

## Spatial mapping

Owns playable candidate locations, imaginary or physical reference semantics, deterministic candidate evaluation inputs, and annotation-ready spatial output.

## Instruments

Own string identities, tunings, display order, scale length, physical fret metadata, imaginary semitone markers, courses, and instrument-specific constraints.

## Sequencer

Will own timeline, transport, playback, track handling, and synchronization. It is intentionally a placeholder at this phase.

## Practice

Will own repetitions, tempo progression, looping, ear-training flows, and student guidance. It is intentionally a placeholder at this phase.

## Lesson assignment (Educational Engine)

Owns the portable `LessonAssignmentV1` envelope: assignment/content identity, instructional intent, playback policy requests, spatial guidance, teacher overrides, preserve-only assessment metadata, provenance, and semantically inert routing fields. See [LESSON_ASSIGNMENT_BOUNDARY.md](LESSON_ASSIGNMENT_BOUNDARY.md) and [MVP1_LESSON_PIPELINE.md](MVP1_LESSON_PIPELINE.md).

MVP-1 shall normalize all lesson input through a portable, versioned `LessonAssignment` envelope before canonical musical resolution. Networking is deferred, but the object shall be serializable, reloadable, teacher-override capable, and transport-neutral so later device-to-device communication does not require redesign of the musical, spatial, timing, selection, projection, or rendering pipeline.

## Adapters

Own boundary-specific translation concerns such as file parsing, API validation, or renderer integration. They do not define musical truth.

## Renderers and external integrations

Renderers, UI surfaces, and device integrations consume spatial annotations and canonical musical data. They are outside the core engine boundary.
