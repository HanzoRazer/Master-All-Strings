# DO-010 Educational practice evaluation

Performance remains measurement-only. Education interprets
`PerformanceSessionEvidenceV1` / `PerformanceAlignmentResultV1` into
`PracticeEvaluationResultV1` using explicit `PracticeEvaluationPolicyV1`
defaults:

- early/late finding thresholds: 100 ms
- pitch difference threshold: >= 1 semitone
- isolate: >= 3 actionable findings in a 4-expected-event window
- slow-down: actionable timing/pitch findings >= 30% of expected events
- continue: actionable findings <= 1 and no SIGNIFICANT finding

Every `OBSERVED_NOT_EXPECTED` alignment row emits `UNEXPECTED_NOTE`.

`EducationalInterpretationV1` stays a broader future contract and is not
required for DO-010 MVP completion.
