<!-- GENERATED from governance/engine_architecture_v1.json — do not edit by hand. -->
<!-- Regenerate: python -m master_all_strings.governance.engine_boundaries --write-views -->

# Engine Contract Ownership

Every cross-engine contract has exactly one owning engine and one versioning authority. Generated from the constitutional registry.

| Contract | Owning engine | Producer | Consumers | Mutability | Classification | Cites | Versioning authority |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MusicalEvent` | Musical Core | Musical Core | Educational, Creative, Performance | immutable | neither | — | Musical Core |
| `InstrumentProfile` | Musical Core | Musical Core | Educational, Creative, Performance | immutable | neither | — | Musical Core |
| `TuningProfile` | Musical Core | Musical Core | Educational, Creative, Performance | immutable | neither | — | Musical Core |
| `SpatialPositionCollection` | Musical Core | Musical Core | Educational, Creative | immutable | evidence | — | Musical Core |
| `SelectedSpatialPath` | Musical Core | Musical Core | Educational | immutable | evidence | — | Musical Core |
| `SpatialEvidenceV1` | Musical Core | Musical Core | Educational | immutable | evidence | — | Musical Core |
| `ProjectionRequest` | Musical Core | Creative | Musical Core | immutable | neither | — | Musical Core |
| `ProjectionResult` | Musical Core | Musical Core | Creative, Educational, Performance | immutable | neither | — | Musical Core |
| `EducationalInterpretationV1` | Educational | Educational | Creative | immutable | interpretation | SpatialEvidenceV1 | Educational |
| `LearningObject` | Educational | Educational | Creative | versioned | neither | — | Educational |
| `CurriculumRegistry` | Educational | Educational | — | versioned | neither | — | Educational |
| `CoachingRecommendationV1` | Educational | Educational | — | immutable | interpretation | PerformanceObservationV1 | Educational |
| `AssessmentResult` | Educational | Educational | — | immutable | interpretation | — | Educational |
| `ScoreEditProposal` | Creative | Creative | — | immutable | neither | — | Creative |
| `ScoreEditCommandSet` | Musical Core | Creative | Musical Core | immutable | neither | — | Musical Core |
| `PerformanceObservationV1` | Performance | Performance | Educational | immutable | evidence | — | Performance |
| `PracticeSession` | Educational | Educational | — | versioned | interpretation | — | Educational |
