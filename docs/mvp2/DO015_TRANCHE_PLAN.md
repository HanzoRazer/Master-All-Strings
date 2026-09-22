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
full pytest                   2786 passed, 3 skipped
coverage                      95.61%
generator --check             PASS
ruff check src tests          PASS
mypy (strict, src)            PASS (161 source files)
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

## Stage 7 attempt progression and session history

PR #31 merged Stage 6. Stage 7 branches from `main`, not from the Stage 6
feature branch.

```text
stage6_merge_sha        = d7b71a9a65494655426c4f3d1ea38297fbc42baf
stage7_base_sha         = d7b71a9a65494655426c4f3d1ea38297fbc42baf
Stage 7 branch          = cursor/do015-guided-attempt-history-cc01
```

`git merge-base HEAD origin/main` equalled `origin/main` at branch creation:
Stage 7 was cut from the tip, which is the Stage 6 merge commit itself.

### The append seam already existed

Stage 7 did not build one. `GuidedSessionController.syncFromEvaluation()`
(`web/mvp1/guided_disposition.js`) has owned create-vs-append since Stage 4, and
`app.js` has called it from the normal post-performance path since then:

```text
Arm / Start / Perform            (unchanged)
      ↓
educationApi.evaluate(...)       (unchanged, called once)
      ↓
syncFromEvaluation({evaluation, guidance})
      ├── no session        → POST /api/education/guided-sessions
      └── AWAITING_ATTEMPT  → POST /api/education/guided-sessions/{id}/attempts
      ↓
server-returned GuidedPracticeSessionV1 replaces the local one
```

Attempt ids stay caller-owned and opaque: `crypto.randomUUID()` via the
controller's `newId`, never the array index or `attempts.length`. No second
orchestrator, evaluator pass, rate policy, passage policy, or tick converter
was added.

### What Stage 7 changed

```text
append failure        prior server-returned session is preserved and the
                      attempt is reported as unrecorded; only a failed first
                      creation clears anything (GuidedProgressionError carries
                      phase + sessionPreserved)

lesson switch         LocalGuidedSessionApi.transition() →
                      POST /api/education/guided-sessions/{id}/transition
                      old session → TRANSITIONED by the Stage 2 service
                      failure keeps the old session; it is never discarded
                      new lesson gets no session until its first evaluated
                      attempt

lesson pin            controller.session is the record;
                      controller.activeSession is what may drive controls,
                      and is null when the record belongs to another lesson --
                      assignment, content AND canonical revision, the same
                      three pins the append path enforces
                      an unresolved revision (null) does not match a session
                      that carries one: the context completes only when
                      loadScoreViews resolves scoreView.revisionId, which is
                      the value an evaluation pins a session to

identity pin          evidence whose assignment_id / content_id /
                      canonical_revision_id disagrees with the session is
                      refused, never re-pinned

history               web/mvp1/guided-session-history.js renders
                      session.attempts[] into #guidedSessionHistory, mounted
                      by results.js
```

`current_attempt_index` -- not `attempts.at(-1)` -- identifies the current
attempt; lifecycle state decides whether it is actionable, so a `CLOSED` or
`TRANSITIONED` session is read-only throughout. Prior attempts render
read-only and are byte-identical before and after later appends.

The history renderer imports only the read-only session predicates from
`guided_disposition.js`. It reaches no Transport seam, no evaluator, no
guidance builder, and not `PracticeSessionHistory`, which remains the
Educational Engine's evaluator input and is a different thing from this
history. A source guard in `tests/guided_session_history.test.js` holds that.

Browser diagnostics gained `guidedSessionStatus`, `guidedAttemptCount`,
`currentAttemptId`, `currentAttemptIndex`, `guidedAttemptIds`,
`transitionedSessionId`, `transitionedSessionStatus`, `lastProgressionPhase`,
`lastAppendStatus`, and `lastAppendError`. They are observational.

### Whole-page coverage of the lesson-switch failure

`tests/guided_lesson_switch_browser.test.js` boots `app.js` itself against
`tests/browser_harness.js` -- minted DOM elements, the repository's own lesson
artifacts off disk, and a routed `fetch` -- and drives the page through its own
controls with the deterministic `?fakeMidi=1` input: Arm, Start, perform, Stop,
Accept, then the lesson picker.

It covers the path no module-level test can see, where the preserved session and
what the page shows can disagree:

```text
attempt on lesson A  → session AWAITING_ACTION, Accept → ACCEPTED/PENDING
lesson switch to B   → transition POST fails
                       session preserved, byte-identical, still pinned to A
                       activeSession null; Accept/Decline/Apply inert
                       history empty for B and carries the failure notice
                       zero /attempts requests
attempt on B         → refused at the pin; no append, no create, A untouched
return to A          → the preserved session is the learner's again, and the
                       history shows its attempt because the controls act on it
switch to B (ok)     → A → TRANSITIONED; B's first attempt creates its own
```

Two fixes came out of writing it. The lesson picker overwrites the status line
with `Loaded <lesson>` as soon as `loadSession` returns, so the transition
failure is rendered into the results panel and not left to that line alone. And
`applySessionArtifacts` renders history from `activeSession` rather than from
nothing, so a lesson whose session is still open -- a reload, or a return after
a failed transition -- does not show an empty history while its Apply control
is live.

### Revision pinning

Review of `0a9e5ab` found `activeSession` pinned on assignment and content
only, while the append path pinned all three. The same lesson re-cut at a new
canonical revision therefore left the old session actionable: the append would
be refused later, correctly, but the controls should never have been live.

Both now pin the same three fields. `setLessonContext` carries
`canonicalRevisionId`, and `activeSession` compares it strictly -- including
null, so an unresolved revision does not match a session that has one. The
browser only learns the loaded revision when `loadScoreViews` resolves
`scoreView.revisionId` (the value the evaluate request carries, hence the
session's own pin), so `applySessionArtifacts` pins the lesson with no revision
and `loadSession` completes the pin afterwards and renders again. The window in
between fails closed.

`GuidedSessionController.recordDisposition` and `recordExecution` now read
`activeSession` too, so the pin holds whichever entry point is used rather than
only through `app.js`'s handlers.

### Verification (local, Python 3.11, matching CI)

```text
Node tests                    483 passed  (400 at stage7_base + 83 new)
  web/mvp1/tests/*.test.js
full pytest                   2784 passed, 3 skipped, 2 failed
coverage                      95.61%  (floor 95%)
generator --check             PASS
ruff check src tests          PASS
mypy (strict, src)            PASS (161 source files)
```

The two failures are pre-existing and environmental, not Stage 7's: both fail
identically on `d7b71a9` in a worktree with no Stage 7 code. They are
`tests/mvp/test_mvp1_publication_utils.py::test_mvp1_lineage_script_passes`
(the lineage script prints `→` and the shelled-out `python3` on this
Windows host encodes cp1252) and
`tests/integrations/test_do008_end_to_end.py::test_checked_in_bundle_correlates_all_authoritative_semantic_events`
(a checked-in bundle artifact's sha256 over a CRLF working copy). Linux CI runs
both.

```text
protected surfaces vs stage7_base_sha    no diff
  src/master_all_strings/education/guided_session.py
  src/master_all_strings/education/guided_session_service.py
  src/master_all_strings/education/session_history.py
  src/master_all_strings/education/guidance.py
  src/master_all_strings/mvp/guided_session_api.py
  resources/education/examples/guided_sessions/**
  governance/engine_architecture_v1.json
  web/mvp1/transport.js
  web/mvp1/teaching-timeline.js
  web/mvp1/practice_actions.js
  web/mvp1/guided-action-executor.js
```

## Stage 8 adversarial authority

Stage 8 branches from current `main`, which already contains the Stage 7 merge.
It adds adversarial verification only. No product file changed. No defect was
found, so there is no corrective SHA. Stage 9 has not started. Merge, tag, and
release are not authorized.

```text
stage7_product_sha = 4eaf71b66d9e8f19c46e002636186b44701855b0
stage7_merge_sha   = 286d5aa439831ea44ff6e198a8518a45f076b513
stage8_base_sha    = f4322bf741e52448a7cd36da370dffb9c9efa02d
Stage 8 branch      = cursor/do015-adversarial-authority-s8a1
```

`286d5aa` is an ancestor of `stage8_base_sha`. The in-flight register's stale
PR #33 row was removed in the first commit on this branch.

### Coverage crosswalk

`EXISTING` names the Stage 4–7 test that already locks the cell. `NEW` names
the Stage 8 test. Nothing in this matrix is `DEFECT`.

| Cell | Result |
| --- | --- |
| A1 revision mismatch | EXISTING — `web/mvp1/tests/guided_progression.test.js:598` :: a session from another revision of the same lesson is not actionable |
| A2 unresolved revision | EXISTING — `web/mvp1/tests/guided_progression.test.js:657` :: an unresolved revision leaves a recorded session inert until it agrees |
| A3 revision restored | EXISTING — `web/mvp1/tests/guided_progression.test.js:632` :: the preserved session becomes actionable again at its own revision |
| A4 assignment mismatch | NEW — `web/mvp1/tests/guided_authority_adversarial.test.js:118` :: assignment mismatch alone leaves the session inert |
| A5 content mismatch | NEW — `web/mvp1/tests/guided_authority_adversarial.test.js:129` :: content mismatch alone leaves the session inert |
| A6 all three mismatch | NEW — `web/mvp1/tests/guided_authority_adversarial.test.js:139` :: all three pins disagreeing still cannot append or act |
| B1–B2 accept/decline before pin | NEW — `web/mvp1/tests/guided_authority_adversarial.test.js:169` :: a direct disposition handler cannot bypass an inactive session |
| B3 double accept | EXISTING — `tests/mvp/test_guided_session_api_do015.py:170` :: test_double_disposition_is_409_and_does_not_mutate |
| B4 accept then decline | EXISTING — `web/mvp1/tests/guided_disposition.test.js:185` :: a resolved disposition cannot be recorded again |
| B5 decline then accept | EXISTING — `tests/education/test_guided_session_service_do015.py:543` :: test_second_disposition_is_rejected |
| B6 historical attempt actuation | NEW — `tests/education/test_guided_session_adversarial_do015.py:144` :: test_disposition_does_not_rewrite_the_historical_attempt |
| C1 apply before accept | EXISTING — `web/mvp1/tests/guided_apply.test.js:140` :: Apply is a no-op before acceptance: no runtime and no execution POST |
| C2 apply after decline | EXISTING — `web/mvp1/tests/guided_apply.test.js:165` :: declined actions cannot apply |
| C3 double apply | EXISTING — `web/mvp1/tests/guided_apply.test.js:220` :: a second Apply after final execution does not run runtime or POST; NEW — `web/mvp1/tests/guided_authority_adversarial.test.js:241` :: overlapping Apply calls actuate runtime once |
| C4 wrong executed action | EXISTING — `tests/education/test_guided_session_service_do015.py:739` :: test_executed_action_cannot_hide_a_different_action_type; NEW — `tests/mvp/test_guided_session_api_do015.py:803` :: test_wrong_executed_action_is_409_and_does_not_mutate |
| C5 unsupported misuse | EXISTING — `tests/education/test_guided_session_service_do015.py:582` :: test_continue_unsupported_is_rejected |
| C6 legitimate unsupported | EXISTING — `web/mvp1/tests/guided_action_executor.test.js:252` :: VIEW_ONE_STRING is UNSUPPORTED and does not mutate runtime; EXISTING — `web/mvp1/tests/guided_action_executor.test.js:269` :: ENABLE_ZONE_VIEW is UNSUPPORTED and does not mutate runtime |
| D1 evidence before runtime | EXISTING — `web/mvp1/tests/guided_apply.test.js:186` :: runtime mutation precedes SUCCEEDED evidence POST; the executor posts only after `execute` returns |
| D2 runtime failure | EXISTING — `web/mvp1/tests/guided_apply.test.js:201` :: runtime failure posts FAILED and never SUCCEEDED |
| D3 runtime success, evidence failure | EXISTING — `web/mvp1/tests/guided_apply.test.js:231` :: runtime success with evidence write failure is reported honestly |
| D4 no automatic retry | EXISTING — `web/mvp1/tests/guided_apply.test.js:231` :: runtime success with evidence write failure is reported honestly; the second Apply does not call the runtime seam again |
| E1 append while AWAITING_ACTION | EXISTING — `web/mvp1/tests/guided_progression.test.js:202` :: AWAITING_ACTION does not append: the recommendation is still unanswered |
| E2 append after CLOSED | EXISTING — `tests/education/test_guided_session_service_do015.py:480` :: test_append_rejects_awaiting_action_closed_and_transitioned |
| E3 append after TRANSITIONED | EXISTING — `tests/education/test_guided_session_service_do015.py:480` :: test_append_rejects_awaiting_action_closed_and_transitioned |
| E4 duplicate attempt id | EXISTING — `tests/mvp/test_guided_session_api_do015.py:369` :: test_duplicate_attempt_and_performance_ids_are_409 |
| E5 duplicate performance id | EXISTING — `tests/mvp/test_guided_session_api_do015.py:369` :: test_duplicate_attempt_and_performance_ids_are_409 |
| E6–E8 wrong assignment, content, revision | EXISTING — `tests/education/test_guided_session_service_do015.py:497` :: test_append_rejects_wrong_assignment_content_and_revision; NEW — `tests/mvp/test_guided_session_api_do015.py:846` :: test_append_rejects_all_three_pins_together_without_mutation |
| E9 evaluation/guidance mismatch | NEW — `tests/education/test_guided_session_adversarial_do015.py:43` :: test_append_rejects_evidence_chain_disagreements_without_mutation; `tests/mvp/test_guided_session_api_do015.py:821` :: test_append_rejects_mismatched_guidance_evidence_without_mutation |
| E10 evaluation digest mismatch | NEW — `tests/education/test_guided_session_adversarial_do015.py:43` :: test_append_rejects_evidence_chain_disagreements_without_mutation |
| F1 failed transition, new lesson | EXISTING — `web/mvp1/tests/guided_lesson_switch_browser.test.js:249` :: a lesson switch whose transition fails keeps the session and stands the page down |
| F2 direct Accept despite disabled control | NEW — `web/mvp1/tests/guided_authority_adversarial.test.js:169` :: a direct disposition handler cannot bypass an inactive session |
| F3 direct Apply despite hidden control | NEW — `web/mvp1/tests/guided_authority_adversarial.test.js:204` :: a failed transition's preserved session ignores direct learner calls |
| F4 new lesson performance, stale session | EXISTING — `web/mvp1/tests/guided_lesson_switch_browser.test.js:296` :: the new lesson's attempt is refused rather than recorded on the old session |
| F5 return to matching lesson | EXISTING — `web/mvp1/tests/guided_lesson_switch_browser.test.js:312` :: returning to the lesson it belongs to hands the preserved session back |
| G1–G4 DOM / fake current marker | NEW — `web/mvp1/tests/guided_authority_adversarial.test.js:296` :: a tampered history DOM cannot redirect the controls onto a finished attempt. The forged markup is answered by driving the disposition and Apply handlers, not by re-reading the session object |
| G5 malformed historical entry | NEW — `web/mvp1/tests/guided_authority_adversarial.test.js:381` :: a malformed historical attempt renders without becoming actionable; NEW — `web/mvp1/tests/guided_authority_adversarial.test.js:418` :: no public history export can make a malformed historical row actionable |
| G6 history interaction surface | NEW — `web/mvp1/tests/guided_authority_adversarial.test.js:468` :: the history module exports nothing that could act on a session. The five presentation exports are locked, so an interaction API cannot arrive unreviewed |
| H1 malformed payload | EXISTING — `tests/mvp/test_guided_session_api_do015.py:511` :: test_malformed_disposition_is_400; `tests/mvp/test_guided_session_api_do015.py:524` :: test_malformed_and_incomplete_requests_are_400 |
| H2 unknown session | EXISTING — `tests/mvp/test_guided_session_api_do015.py:130` :: test_unknown_session_is_404 |
| H3 illegal transition | EXISTING — `tests/mvp/test_guided_session_api_do015.py:188` :: test_execution_before_acceptance_is_409 |
| H4 session A, evidence of session B | NEW — `tests/mvp/test_guided_session_api_do015.py:868` :: test_path_session_wins_over_a_forged_body_session_id |
| H5 replay disposition | EXISTING — `tests/mvp/test_guided_session_api_do015.py:170` :: test_double_disposition_is_409_and_does_not_mutate |
| H6 replay execution | NEW — `tests/mvp/test_guided_session_api_do015.py:789` :: test_replayed_execution_is_409_and_does_not_mutate |
| H7 replay append | EXISTING — `tests/mvp/test_guided_session_api_do015.py:369` :: test_duplicate_attempt_and_performance_ids_are_409 |
| H8 conflict leaves the stored session unchanged | EXISTING — `tests/mvp/test_guided_session_api_do015.py:170` :: test_double_disposition_is_409_and_does_not_mutate; NEW — `tests/mvp/test_guided_session_api_do015.py:789` :: test_replayed_execution_is_409_and_does_not_mutate. Both assert `to_dict` equality after the 409 |
| I1 tampered historical digest | EXISTING — `tests/education/test_guided_session_contract_do015.py:512` :: test_digest_changes_when_attempt_content_changes |
| I2 provenance exclusion | EXISTING — `tests/education/test_guided_session_contract_do015.py:475` :: test_digest_ignores_provenance |
| I3 semantic action changes digest | EXISTING — `tests/education/test_guided_session_contract_do015.py:512` :: test_digest_changes_when_attempt_content_changes |
| I4 fixture integrity | EXISTING — `tests/education/test_guided_session_fixtures_do015.py:88` :: test_fixtures_have_no_drift; EXISTING — `tests/education/test_guided_session_fixtures_do015.py:93` :: test_regeneration_is_byte_identical. The `--check` gate runs the same comparison |
| J authority imports | EXISTING — `web/mvp1/tests/guided_session_history.test.js:305` :: the history renderer reaches no runtime, evaluator, or evaluator input; NEW — `web/mvp1/tests/guided_authority_adversarial.test.js:403` :: stage 6 and stage 7 presentation modules do not take each other's authority |
| aborted session | NEW — `tests/education/test_guided_session_adversarial_do015.py:163` :: test_aborted_session_rejects_append_and_disposition |
| client-tampered recommendation | NEW — `web/mvp1/tests/guided_authority_adversarial.test.js:186` :: the server session replaces a locally tampered recommendation |
| cross-revision page | EXISTING — `web/mvp1/tests/guided_lesson_switch_browser.test.js:362` :: the same lesson at another canonical revision is not the session's lesson |

No whole-page adversarial file was added. The Stage 7 lesson-switch browser
suite already boots `app.js` for stale lesson and stale revision. The new
cells are controller, renderer, service, or HTTP tests.

A replay that returns 409 with the stored session unchanged is the fail-closed
result. Stage 8 does not require a second 200.
### Verification (local, Python 3.11.9)

```text
Node tests                    493 passed  (483 at the Stage 7 record + 10 new)
  web/mvp1/tests/*.test.js
full pytest                   2820 passed, 3 skipped, 2 failed
coverage                      95.61%  (floor 95%)
generator --check             PASS
ruff check src tests          PASS
mypy (strict, src)            PASS (161 source files)
GitHub Actions verify.yml     PASS  run 35647304458 on 837db3c
defects found                 none
product corrections           none
```

The two failures were re-run on a clean worktree of `f4322bf`, with no Stage 8
files present. Both failed the same way they fail on this branch:

```text
test_mvp1_lineage_script_passes
  the lineage script prints → and the shelled-out python3 encodes cp1252
test_checked_in_bundle_correlates_all_authoritative_semantic_events
  zone semantic artifact sha256 mismatch on the Windows CRLF checkout
```

Linux CI remains the authoritative witness for those two. Everything Stage 8
added is locally green.

```text
protected surfaces vs stage8_base_sha    no diff
  src/master_all_strings/education/guided_session.py
  src/master_all_strings/education/guided_session_service.py
  src/master_all_strings/education/session_history.py
  src/master_all_strings/education/guidance.py
  src/master_all_strings/mvp/guided_session_api.py
  resources/education/examples/guided_sessions/**
  governance/engine_architecture_v1.json
  web/mvp1/transport.js
  web/mvp1/teaching-timeline.js
  web/mvp1/practice_actions.js
  web/mvp1/guided-action-executor.js
```

## Stage 9 full MAS certification

Stage 9 certifies the completed DO-015 stack as one system and freezes the
evidence. It adds no product capability, and the verifier enforces that: no
file outside `docs/**`, `tests/**` and `scripts/verify_do015_certification.py`
may differ between the certified product and the evidence freeze.

```text
stage8_product_sha    = a29afb5e6972c5dfbf2266dee7a0ec47597c1d98
stage8_merge_sha      = 3fcf618b655c3f51b020d11a0bb3f96571da08d7
stage9_base_sha       = 3fcf618b655c3f51b020d11a0bb3f96571da08d7
certified_product_sha = 3fcf618b655c3f51b020d11a0bb3f96571da08d7
Stage 9 branch        = cursor/do015-full-certification-cc02
```

`3fcf618` is the PR #34 merge commit and the tip of `main` at branch creation,
so the certified product baseline and the Stage 9 base are the same commit.
The Stage 8 product head is `a29afb5`, not the `f671a73` an earlier draft of
the order carried: two review-fix commits landed on the Stage 8 branch before
it merged.

Certification results are recorded in `DO015_INTEGRATION_EVIDENCE.json` and
read back by `scripts/verify_do015_certification.py`. The human synthesis is
`DO015_CERTIFICATION_REPORT.md`.

```text
targeted DO-015 pytest     501 passed
full pytest                2978 passed, 3 skipped, 2 failed (Windows-only)
coverage                   95.63%  (floor 95%)
Node                       505 passed, 0 failed (Windows; linux_ci_coverage NOT_PRESENT)
ruff check src tests       PASS
mypy (strict)              PASS, 161 source files
fixture --check            PASS
check_in_flight.py         PASS
certification verifier     OK (9 of 9)
```

The certified session: SLOW_DOWN accepted and applied to rate 0.75, then
ISOLATE_PASSAGE accepted and applied to a loop, then CONTINUE accepted and
applied to CLOSED -- three attempts, one canonical revision, three distinct
performance identities, prior attempts immutable once no longer current, and a
session digest that recomputes to what the service returned.

Two witnesses with different claims. The reproducible one boots the real
`app.js` through the in-repo harness and certifies orchestration and the UI
event path; it does not certify rendering. The authoritative one drives the
same legs through the real Stage 4 API and certifies lifecycle truth and the
digest. The visual witness is `NOT_AVAILABLE`: no connected browser existed in
the certification environment, so DOM rendering is not certified by this
tranche and no screenshots exist.

`CONTINUE` is unreachable from a bundled lesson by fake MIDI, so closure used a
controlled lifecycle certification scenario: synthetic performance evidence,
real evaluator, real recommendation, regenerated and compared on every test
run.

Stage 10 has not started. Merge, tag, release and publication are not
authorized by this tranche.

## Session status (minimal)

`ACTIVE`, `AWAITING_ACTION`, `AWAITING_ATTEMPT`, `CLOSED`, `TRANSITIONED`,
`ABORTED`.

## Non-goals

Engine-registry rows, `PracticeSessionHistory` changes, mastery claims,
authorizing `VIEW_ONE_STRING` / `ENABLE_ZONE_VIEW`, Transport math, secondary
actions becoming executable, merge/tag, CNC work.
