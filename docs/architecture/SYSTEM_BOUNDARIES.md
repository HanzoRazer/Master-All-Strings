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

## Adapters

Own boundary-specific translation concerns such as file parsing, API validation, or renderer integration. They do not define musical truth.

## Renderers and external integrations

Renderers, UI surfaces, and device integrations consume spatial annotations and canonical musical data. They are outside the core engine boundary.
