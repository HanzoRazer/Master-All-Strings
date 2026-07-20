# Musical Spatial Mapping Engine

## Purpose

The Musical Spatial Mapping Engine (MSME) converts canonical musical pitch events into annotation-ready spatial positions for a configured instrument.

## Canonical inputs

- `MusicalEvent`
- immutable `InstrumentProfile`
- future mapping constraints and preferences

## Outputs

- validated spatial-position contracts;
- auditory-reference contracts for fretless exercises;
- pitch labels and equal-temperament geometry values.

## Fretted behavior

The current contracts distinguish sounding pitch, relative semitone position, physical fret number, and physical distance from the nut.

## Fretless behavior

Fretless instruments are first-class. Imaginary semitone references are represented explicitly and are not mislabeled as physical frets.

## Imaginary semitone behavior

The current models support semitone and fractional-semitone targets, normalized positions, and optional millimeter distances when scale length is known.

## Deterministic selection

Deterministic candidate generation and selection are deferred until the Phase 2 stop gate is reviewed.

## Current non-goals

This phase does not implement candidate generation, scoring, selection, rendering, playback, MIDI parsing, transport, or practice pedagogy.
