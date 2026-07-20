# Master All Strings

Master All Strings is the modern product home for reconstructing, modernizing, and expanding the musical sequencing and String Master concepts developed in the original Master Producer.

> Master All Strings is not software for drawing instruments or estimating CNC jobs. It is a musical-performance and learning platform that translates musical information into playable, instrument-specific guidance.

> Music is canonical. Instrument representation is an adapter.

## Current scope

This repository currently implements Phase 0 through Phase 2 of the initial foundation plan:

- repository structure and architecture documents;
- immutable core contracts for musical events, instruments, and spatial positions;
- validation helpers;
- pitch-formatting utilities;
- equal-temperament geometry utilities.

The first bounded subsystem is the **Musical Spatial Mapping Engine (MSME)**. Candidate generation, scoring, and deterministic selection are intentionally deferred until the Phase 2 stop gate is reviewed.

## What this repository is not

This repository is not:

- a luthier CAD/CAM application;
- a CNC estimating or manufacturing-planning tool;
- a generic fretboard calculator;
- a continuation of the frozen Visual C++ 6 / MFC archive;
- a place to copy unrelated code from neighboring repositories.

## Repository layout

```text
Master-All-Strings/
├── pyproject.toml
├── src/master_all_strings/
├── resources/instruments/
├── tests/
└── docs/
```

See `/home/runner/work/Master-All-Strings/Master-All-Strings/docs/architecture/PRODUCT_CHARTER.md` for the product charter and `/home/runner/work/Master-All-Strings/Master-All-Strings/docs/architecture/MUSICAL_SPATIAL_MAPPING_ENGINE.md` for subsystem details.
