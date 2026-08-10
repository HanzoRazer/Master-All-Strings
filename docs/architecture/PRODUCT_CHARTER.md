# Product Charter

## What Master All Strings is

Master All Strings is the future-facing musical software product derived from the concepts and workflow evidence of the original Master Producer and related String Master technology. Its mission is to translate canonical musical information into playable, instrument-specific guidance for sequencing, practice, and instrument learning.

## Product architecture

Master All Strings is composed of four cooperating engines, each a constitutional ownership boundary ([ADR-0006](../decisions/ADR-0006-FOUR-ENGINE-ARCHITECTURE.md), [system model](FOUR_ENGINE_SYSTEM_MODEL.md)):

- **Musical Core** — canonical music, spatial mapping, selection, deterministic projection;
- **Educational Engine** — curriculum, learning objects, interpretation, coaching, assessment;
- **Creative Engine** — score authoring, composition, AI-assisted entry;
- **Performance Engine** — live capture, playback, device integration.

This describes the intended architecture, not current implementation status. Musical Core has shipped code through candidate generation; the Educational Engine now also ships the portable `LessonAssignmentV1` lesson-entry boundary (MVP-1E). Creative and Performance remain governance boundaries with planned capabilities. Canonical music remains authoritative regardless of engine, and Smart Guitar remains a consumer and integration surface (within the Performance Engine), never the architectural source of truth.

MVP-1 shall normalize all lesson input through a portable, versioned `LessonAssignment` envelope before canonical musical resolution. Networking is deferred, but the object shall be serializable, reloadable, teacher-override capable, and transport-neutral so later device-to-device communication does not require redesign of the musical, spatial, timing, selection, projection, or rendering pipeline.

## What Master All Strings is not

Master All Strings is not a luthier CAD/CAM tool, CNC estimating application, manufacturing-planning repository, generic fretboard calculator, or a continuation of the frozen Visual C++ 6 / MFC archive.

## Why this repository exists

This repository owns the clean, modern implementation of the product. Repository ownership is determined by product purpose, not by whichever neighboring repository happens to contain a convenient language stack, test suite, or dependency graph.

## Relationship to Master Producer

The legacy Master Producer repository is a historical source of behavioral evidence, design lineage, workflow evidence, and constraints. New production code belongs here, not in the legacy archive.

## Relationship to Smart Guitar

Smart Guitar is treated as a future integration or consumer of the platform rather than the architectural source of truth. The musical model remains canonical regardless of rendering device or controller.

## Why this is not part of other repositories

This is not part of luthiers-toolbox or CNC Production Shop because those repositories are owned by different product purposes. Instrument geometry, manufacturing, governance, or CAD concerns may integrate later, but they do not define this repository’s architecture.
