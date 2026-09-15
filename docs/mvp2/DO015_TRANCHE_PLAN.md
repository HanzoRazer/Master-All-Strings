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
2. Session service: create / append / disposition / execution / transition
3. Fixtures for accept, decline, isolate, repeat, continue, failure, switch
4. Additive education/practice API
5. Accept/Decline UI (replace Apply)
6. Wire accept → existing rate/loop seams; `REPEAT` → next attempt;
   `CONTINUE` success → close
7. Attempt history + DO-014 guidance association per attempt
8. Adversarial authority tests
9. Full MAS certification

Stage 1 is contract/schema only. Stage 2 is the lifecycle service in
`guided_session_service.py`. Stage 3 is the deterministic fixture matrix.
API and browser work remain later.

## Stage 2 gate closure

Patch-forward from the Stage 2 implementation baseline. Do not reset to
Stage 1 and reimplement.

```text
5392ec7   Stage 0/1 contract baseline
ba69b66   Stage 2 implementation
b3b8462   Stage 2 implementation/hardening
follow-up Stage 2 gate-closure remediation (this document)
```

Final Stage 2 public service names (kept; not renamed to illustrative spellings):

```text
create_from_first_evaluated_attempt
append_evaluated_attempt
record_action_disposition
record_action_execution
transition_session
```

`close_session` and `begin_next_attempt` are not public. Inspection found no
independent required caller. Ordinary successful closure is caused only by:

```text
CONTINUE + ACCEPTED + SUCCEEDED → CLOSED
```

Decline and recorded execution already transition an open session to
`AWAITING_ATTEMPT`; `append_evaluated_attempt` performs the next lifecycle
transition. Callers must supply opaque `session_id` and `attempt_id`. The
service validates non-empty/uniqueness and does not mint identities.

`UNSUPPORTED` is reserved for Educational actions whose execution capability
lies outside this tranche:

```text
VIEW_ONE_STRING + ACCEPTED → UNSUPPORTED allowed
ENABLE_ZONE_VIEW + ACCEPTED → UNSUPPORTED allowed
CONTINUE + ACCEPTED → SUCCEEDED | FAILED; UNSUPPORTED invalid
SLOW_DOWN / ISOLATE_PASSAGE / REPEAT → UNSUPPORTED invalid
```

Cross-object evidence checks remain the two independently supplied
relationships (`performance_session_id`, `evaluation_digest`). After
construction, `attempt.guidance_digest` equals `guidance.guidance_digest`.
There is no caller-supplied `guidance_digest`.

Gate results for the Stage 2 gate-closure follow-up were 89 targeted tests.
Pre-merge boundary hardening additionally locks:

```text
omitted executed_action     records recommended_action
supplied executed_action    same action_type only
UNSUPPORTED                 must not record executed_action
session digest exclusions   session_digest, provenance
```

```text
targeted Stage 1+2 tests     93 passed
  test_guided_session_contract_do015.py
  test_guided_session_service_do015.py
ruff check src tests         PASS
mypy (strict, src)           PASS (160 source files)
protected surfaces vs main   unchanged
  PracticeSessionHistory
  governance/engine_architecture_v1.json
  API / src/master_all_strings/mvp
  web/mvp1
```

Stage 3 fixtures are authorized on this branch. Later stages remain unauthorized.

## Stage 3 fixture matrix

Generator: `scripts/build_guided_session_fixtures.py`
`--check` regenerates in memory and compares committed bytes.

Directory: `resources/education/examples/guided_sessions/`

```text
slow_down_accepted.json
slow_down_declined.json
isolate_passage_accepted.json
repeat_accepted.json
continue_accepted_closed.json
continue_declined.json
execution_failed.json
view_one_string_unsupported.json
lesson_transition.json
three_attempt_progression.json
```

All ten are produced by public Stage 2 operations from fixed opaque IDs.
No `uuid4()`, no wall-clock time, no hand-authored impossible states.
Revision mismatch, duplicate identities, `VIEW_ONE_STRING + SUCCEEDED`,
`CONTINUE + UNSUPPORTED`, and failed CONTINUE are service-rejection /
semantic tests, not golden success artifacts.

```text
Stage 2 checkpoint SHA      a4e23ad4031cbd7693aa459ba4e7f04d680f942f
fixture files               10
fixture tests               50 passed
targeted Stage 1–3 tests    143 passed
  test_guided_session_contract_do015.py
  test_guided_session_service_do015.py
  test_guided_session_fixtures_do015.py
generator --check           PASS
ruff check src tests        PASS
mypy (strict, src)          PASS (160 source files)
protected surfaces vs main  unchanged
  PracticeSessionHistory
  governance/engine_architecture_v1.json
  API / src/master_all_strings/mvp
  web/mvp1
  Transport
```

Stage 4 API integration is authorized on a new branch from merged `main`.

## Stage 4 additive API

PR #28 merged. Stage 4 does not continue the Stage 3 feature branch.

```text
stage2_checkpoint_sha   = a4e23ad4031cbd7693aa459ba4e7f04d680f942f
stage3_product_sha      = 0c19b37f0936a0cbb99285b5b3ca40bbe6b07a2d
stage3_merge_sha        = 8046e854e2d75922a33898ffba4ff3568556f6a6
stage4_base_sha         = 8046e854e2d75922a33898ffba4ff3568556f6a6
Stage 4 branch          = cursor/do015-guided-session-api-ce6b
```

`git merge-base --is-ancestor 8046e854e2d75922a33898ffba4ff3568556f6a6 HEAD` holds.
Stage 4 branched from that merge commit (`origin/main` at entry), not from
`cursor/do015-guided-practice-session-ce6b`.

Storage is an in-memory repository (`get` / `put` only). No SQLite, filesystem,
or Redis. The store does not implement transitions.

Route inventory (additive under the existing `/api/education/*` namespace):

```text
POST /api/education/guided-sessions
GET  /api/education/guided-sessions/{session_id}
POST /api/education/guided-sessions/{session_id}/disposition
POST /api/education/guided-sessions/{session_id}/execution
POST /api/education/guided-sessions/{session_id}/attempts
POST /api/education/guided-sessions/{session_id}/transition
```

`close` / `begin-next` are not API operations. Every mutating route delegates to
the Stage 2 public service. HTTP mapping is `400` malformed, `404` unknown
session, `409` illegal lifecycle / identity conflict. Known rejections are not
`500`. Failed requests do not replace the stored session.

```text
API tests                     35 passed
  test_guided_session_api_do015.py
targeted Stage 1–4 tests      178 passed
  test_guided_session_contract_do015.py
  test_guided_session_service_do015.py
  test_guided_session_fixtures_do015.py
  test_guided_session_api_do015.py
generator --check             PASS
ruff check src tests          PASS
mypy (strict, src)            PASS (161 source files)
protected surfaces vs main    unchanged except additive API registration
  PracticeSessionHistory
  governance/engine_architecture_v1.json
  web/mvp1
  Transport
  Stage 3 fixture bytes
  Stage 2 service
```

Stage 5 Accept/Decline UI is authorized on a new branch from merged Stage 4 `main`.

## Stage 5 Accept/Decline UI

PR #29 merged Stage 4. Stage 5 does not continue the Stage 4 feature branch.

```text
stage4_product_sha      = f2da2e123fc9a6bc30884d7e7964039752daa290
stage4_merge_sha        = f686b18904bd4dd3022a7c8641b0980114f1f705
stage5_base_sha         = f686b18904bd4dd3022a7c8641b0980114f1f705
Stage 5 branch          = cursor/do015-guided-accept-decline-ce6b
```

`git merge-base --is-ancestor f686b18904bd4dd3022a7c8641b0980114f1f705 HEAD` holds.

Learner controls this stage:

```text
ACCEPT  → POST /api/education/guided-sessions/{id}/disposition {disposition: ACCEPTED}
DECLINE → POST /api/education/guided-sessions/{id}/disposition {disposition: DECLINED}
```

After ACCEPT the UI shows `Accepted — ready to apply` and locks Accept/Decline.
`#btnApplyPrimary` remains in the DOM as `Apply recommendation` but is hidden and
disabled. It is not an Accept path and is not an execution control.

Hard invariant:

```text
Accept/Decline
  → disposition API only
  → no practiceActions.apply()
  → no Transport.setRate / setLoop
  → no recording start
  → no lesson advance
```

The first evaluated attempt creates the guided session through the Stage 4
create route. After DECLINE the next evaluation appends. Opaque `session_id`
and `attempt_id` are caller-supplied.

```text
Node tests                    365 passed
  web/mvp1/tests/*.test.js
targeted Stage 1–4 tests      178 passed
generator --check             PASS
ruff check src tests          PASS
mypy (strict, src)            PASS (161 source files)
protected surfaces vs main    unchanged except Stage 5 browser UI
  PracticeSessionHistory
  governance/engine_architecture_v1.json
  Transport implementation
  Teaching Timeline implementation
  Stage 3 fixture bytes
  Stage 2 service
  Stage 4 API semantics
```

Stage 6 Apply-recommendation execution is not authorized on this branch.

## Stage 6 accepted-guidance execution

PR #30 merged Stage 5. Stage 6 does not continue the Stage 5 feature branch.

```text
stage5_product_sha      = 6f11b3518296702043564b7b10c65c26e9498f78
stage5_merge_sha        = 91b5ba27ffc4a553b8b95f2da203c36418f86436
stage6_base_sha         = 91b5ba27ffc4a553b8b95f2da203c36418f86436
Stage 6 branch          = cursor/do015-guided-action-execution-df74
```

`git merge-base --is-ancestor 91b5ba27ffc4a553b8b95f2da203c36418f86436 HEAD` holds.
Stage 6 branched from that merge commit (`origin/main` at entry).

Learner sequence this stage:

```text
recommendation
     ↓
Accept  → disposition API only (Stage 5 unchanged)
     ↓
ACCEPTED / PENDING
     ↓
Apply recommendation
     ↓
guided-action-executor  → existing runtime seam
     ↓
SUCCEEDED | FAILED | UNSUPPORTED
     ↓
POST /api/education/guided-sessions/{id}/execution
     ↓
server-returned GuidedPracticeSessionV1
```

`#btnApplyPrimary` is enabled only for `ACCEPTED` + `PENDING`. Accept still makes
zero Transport calls. Apply cannot run before acceptance, after decline, or
after a finalized execution status.

Runtime mapping (no new policy, no new tick converter, no new Transport):

```text
SLOW_DOWN        → PracticeActionController.applySlowDown → Transport.setRate(target_rate)
ISOLATE_PASSAGE  → PracticeActionController.applyIsolatePassage
                   resolveFocusRangeSeconds → secondsAtTick(start) / secondsAtTick(end)
                   → Transport.setLoop
REPEAT           → no rate/loop/recording mutation; readiness for Arm/Start
CONTINUE         → no Transport mutation; CLOSED comes from Stage 2 via Stage 4
VIEW_ONE_STRING  → no runtime mutation; execution_status UNSUPPORTED, executed_action null
ENABLE_ZONE_VIEW → no runtime mutation; execution_status UNSUPPORTED, executed_action null
```

Partial success (runtime changed, evidence POST failed) keeps the local session
at the pre-execution server state, surfaces `Evidence recording failed`, and
does not automatically retry the runtime action.

```text
Node tests                    400 passed
  web/mvp1/tests/*.test.js
targeted Stage 1–4 tests      178 passed
generator --check             PASS required
ruff check src tests          PASS required
mypy (strict, src)            PASS required
protected surfaces vs main    unchanged except Stage 6 browser execution wiring
  PracticeSessionHistory
  governance/engine_architecture_v1.json
  Transport implementation
  Teaching Timeline implementation
  Stage 3 fixture bytes
  Stage 2 service
  Stage 4 API semantics
```

Stage 7 attempt-history UI is not authorized on this branch.

## Session status (minimal)

`ACTIVE`, `AWAITING_ACTION`, `AWAITING_ATTEMPT`, `CLOSED`, `TRANSITIONED`,
`ABORTED`.

## Non-goals

Engine-registry rows, `PracticeSessionHistory` changes, mastery claims,
authorizing `VIEW_ONE_STRING` / `ENABLE_ZONE_VIEW`, Transport math, secondary
actions becoming executable, merge/tag, CNC work.
