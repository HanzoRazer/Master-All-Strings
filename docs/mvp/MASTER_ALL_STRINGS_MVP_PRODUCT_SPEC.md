# Master All Strings — MVP 1 Product Spec

Commercial milestone: **Master All Strings MVP 1**

This document describes what MVP 1 is and what a learner can do with it.
Engineering history names (MVP-1F, MVP-2A, DO-008/009/010) remain valid as
historical identifiers; they do not rename this commercial milestone.

## Product capability

MVP 1 is an offline, localhost guitar practice product that closes the loop:

```text
Lesson → See / Hear → Practice → Perform → Evaluate → Feedback → Next Action → Continue
```

A learner can:

1. Launch a bundled demo lesson on a standard six-string guitar projection.
2. See selected fingering on the fretboard (including Zone Harmony colors when enabled).
3. Hear the lesson through the offline Reference Synth.
4. Practice with Play / Pause / Seek, supported rates (0.50×–1.50×), and looping.
5. Optionally use one-string teaching views; unplayable events remain explicit.
6. Perform an attempt with fake or physical Web MIDI input.
7. Receive Educational findings and a deterministic next action after the attempt.
8. Apply the recommended next action and continue practicing.

`CONTINUE` means no immediate repetition is required under the MVP evaluation policy.
It never claims mastery.

## Ownership boundary

```text
PerformanceSessionEvidenceV1   (measurement)
        ↓
education/                     (interpretation)
        ↓
PracticeEvaluationResultV1
```

Performance contracts remain measurement-only. Educational Practice*V1 contracts
interpret evidence. The broader `EducationalInterpretationV1` contract remains deferred.

## What MVP 1 is not

- Commercial MVP 2 (advanced sequencer, synchronized notation/TAB expansion, video, avatar)
- SaaS / cloud accounts
- Smart Guitar hardware integration
- Physical MIDI or audio certification (both remain unverified until hardware testing)
- AI coaching beyond deterministic Practice*V1 next actions

## Launch

```bash
pip install -e ".[dev]"
PYTHONPATH=src python3 scripts/run_mvp1.py --lesson ascending_scale --open
```

Developer golden Educational demo (not a learner control):

```text
http://127.0.0.1:<port>/index.html?fakeMidi=1&devGolden=1
```

## Related documents

- Product flow history: `docs/mvp/MVP1_USER_FLOW.md`
- Release-gate result: `docs/mvp/MASTER_ALL_STRINGS_MVP_RELEASE_REPORT.md`
- Frozen SHAs: `docs/mvp/MVP1_RELEASE_BASELINE.md`
- Publication history: `docs/mvp/MVP1_PUBLICATION_REPORT.md`
- Known limitations: `docs/mvp/DO010_KNOWN_LIMITATIONS.md`
