# DO-015 Tranche Plan — MVP 2E Guided Practice Session Orchestration

**Dev Order:** DO-015
**Milestone:** MVP 2 (tranche E)
**Branch:** `cursor/do015-guided-practice-session-ce6b`
**PR target:** `main`
**Delivery:** implementation + feature PR. Merge/tag not authorized.

This is an engineering record, not a publication report.

## Lineage

```text
do015_base_sha        = db9f3e0b0b43842a09b67c54d1ca0249c4f2829d
do014_baseline_sha    = c012db885852509dc030b2b6c3c699eff8eec210
DO-014 schema         = TeachingGuidanceProjectionV1 / 1.0.0
DO-014 policy         = teaching-guidance-v1
DO-014 evidence-freeze report = NONE — not a blocker
```

`origin/main` was re-verified as `db9f3e0…` immediately before branch creation.
DO-014 landed on `main` as PR #24 (`c012db8`). No `docs/mvp2/DO014_*` freeze
report exists; that absence is an explicit non-blocker, not a missing gate.

## Objective

Own guided-practice session progression, accepted-action execution state,
attempt sequencing, immutable attempt references, and observable history.

Education still decides **what**. The learner decides **whether**. Practice
orchestration manages **when / next**. Recommendation must not auto-execute
Transport. Recommendation, disposition, and execution are separate facts.

## Design rulings (locked)

1. No guided session at lesson load. The first completed/evaluated attempt
   creates the session.
2. Accepted `SLOW_DOWN`, `ISOLATE_PASSAGE`, and `REPEAT` keep the session open.
3. Accepted-and-successfully-executed `CONTINUE` closes the session.
   `ACCEPTED` alone does not imply successful execution and does not close.
4. A lesson switch transitions an open session. It does not create the next
   session until the new lesson produces its first evaluated attempt.
5. Identity reuses the existing MAS chain. No aliases.

   ```text
   assignment_id + content_id
           ↓
   canonical_revision_id
           ↓
   performance_session_id
           ↓
   evaluation_digest
           ↓
   guidance_digest
           ↓
   opaque session_id + attempt_id
   ```

   Production IDs are opaque. Tests use fixed deterministic IDs. IDs are never
   derived from pitches, lesson hashes, revision digest, evaluation content, or
   timestamps alone.
6. The critical evidence distinction is `recommended_action` →
   `action_disposition` → `execution_status`.
7. Execution vocabulary is `NOT_REQUESTED`, `PENDING`, `SUCCEEDED`, `FAILED`,
   and `UNSUPPORTED`. `UNSUPPORTED` is the truthful state for Educational
   actions outside DO-015 scope (`VIEW_ONE_STRING`, `ENABLE_ZONE_VIEW`) and
   does not authorize those capabilities.
8. Only the primary DO-014 `next_action` is actionable. Secondary actions stay
   advisory.
9. `PracticeSessionHistory` stays untouched. It is Educational Engine evaluator
   history, not the guided session.
10. DO-015 lives under `src/master_all_strings/education/` as a sibling of
    `guidance.py`.
11. No engine-registry expansion. `GuidedPracticeSessionV1` is not added to
    `governance/engine_architecture_v1.json`, matching DO-014's unregistered
    `TeachingGuidanceProjectionV1` (`96b58a8`).
12. `CONTINUE` is not mastery. Preserve DO-010 wording.
13. Timestamps, when present, are provenance only and are excluded from the
    session digest.

## Authority this tranche does not take

Educational next-action choice, timing/pitch scoring, passage recomputation,
Transport rate/loop math, canonical score, TAB, notation, mastery, and learner
models remain outside this contract.

## Stages

0. Baseline engineering record (this document)
1. `GuidedPracticeSessionV1` contract, schema, serialization, digest
2. Session service: create / append / disposition / execution / close / transition
3. Fixtures for accept, decline, isolate, repeat, continue, failure, switch
4. Additive education/practice API
5. Accept/Decline UI (replace Apply)
6. Wire accept → existing rate/loop seams; `REPEAT` → next attempt;
   `CONTINUE` success → close
7. Attempt history + DO-014 guidance association per attempt
8. Adversarial authority tests
9. Full MAS certification

Stage 1 is contract/schema only. It does not implement the lifecycle service,
API, or browser.

## Session status (minimal)

`ACTIVE`, `AWAITING_ACTION`, `AWAITING_ATTEMPT`, `CLOSED`, `TRANSITIONED`,
`ABORTED`.

## Non-goals

Engine-registry rows, `PracticeSessionHistory` changes, mastery claims,
authorizing `VIEW_ONE_STRING` / `ENABLE_ZONE_VIEW`, Transport math, secondary
actions becoming executable, merge/tag, CNC work.
