# Four-Engine Handoff Decomposition

This document maps every capability group in the preserved
[educational-platform and smart-notation handoff](../handoff/HANDOFF-2026-07-21-EDUCATIONAL-PLATFORM-SMART-NOTATION.md)
onto the four engines ratified in [ADR-0006](../decisions/ADR-0006-FOUR-ENGINE-ARCHITECTURE.md).

Its purpose is traceability: the handoff was written before the taxonomy and groups
several engines together under "education." Nothing in it is discarded by the
reassignment. This plan records where each group *goes*, so future implementation
handoffs can be split by engine without losing or double-claiming a capability. The
authoritative ownership is the machine-readable registry
(`governance/engine_architecture_v1.json`); this document is the reconciliation
narrative that connects the handoff's sections to that registry.

## Rule

No capability is superseded merely by engine reassignment. A group that spans a seam
is split across two engines at the seam boundary defined in the
[system model](../architecture/FOUR_ENGINE_SYSTEM_MODEL.md), not assigned wholesale
to one.

## Mapping

| Handoff group (§3.2) | Engine(s) | Registry anchor | Notes |
| --- | --- | --- | --- |
| Curriculum and library model | Educational | `curriculum`, `learning-paths`, `reference-material`, `user-library-import` | Official-vs-user separation and provenance are Educational concerns. |
| Learning Object model | Educational | `learning-objects` (contract `LearningObject`) | The primary educational aggregate. |
| MSME educational analysis | **Seam 2** — Musical Core + Educational | `spatial-evidence` (`SpatialEvidenceV1`) → `educational-interpretation` (`EducationalInterpretationV1`) | Split at the evidence/interpretation seam. Core states spatial facts; Education interprets. The handoff's single "analysis" idea becomes two contracts. |
| Tuning architecture | Musical Core + Educational | `instrument-profiles` (Core: `TuningProfile`) + `educational-interpretation` (Education: tuning-specific instructional meaning) | The tuning *fact* is Core; what a tuning *means for a learner* is Educational. |
| AI coaching | Educational | `coaching` (contract `CoachingRecommendationV1`) | Coaching interprets evidence — including Performance evidence via **Seam 4**. |
| AI Smart Score Entry | Creative | `smart-score-entry`, `semantic-edit-proposals` (`ScoreEditProposal`) | Intent-driven authoring. |
| Score control and engraving | **Seam 1** — Creative + Musical Core | Creative: `score-authoring-ux`, `direct-precision-editing`; Core: `notation-projection`/`tab-projection`/`midi-projection` (`ProjectionRequest`/`ProjectionResult`, `ScoreEditCommandSet`) | Split at the authoring/projection seam. Creative changes the music; Core projects it. The executable command contract is Core-owned (Core owns the canonical-music mutation vocabulary); Creative produces commands in it. |
| Smart Guitar integration | Performance | `smart-guitar-adapters`, `live-capture` (`PerformanceObservationV1`), `performance-sessions`, `telemetry`, `teacher-student-sync` | Emits observation evidence consumed by Educational coaching (Seam 4). Embeds no curriculum policy. |

## ADR-number reconciliation

The handoff plans `ADR-0005`–`ADR-0008` for notation, learning objects, score-edit
commands, and tuning. Those numbers are superseded (see the handoff's preservation
banner):

- `ADR-0005` is **reserved for DO-004** (deterministic selection), not Learning Objects.
- `ADR-0006` is the **four-engine architecture**, which absorbs the handoff's
  "notation as projection" concept as its Seam 1.
- The handoff's `ADR-0007`/`ADR-0008` topics (semantic score-edit commands,
  tuning-aware education) remain valid *concepts*; when they are ratified they take
  the next free ADR numbers at that time, owned by the engine this table assigns.

## What this plan does not do

It does not implement anything, move any package, or rewrite the handoff. Each engine's
implementation is a separate future Dev Order that will cite this plan and the registry.
