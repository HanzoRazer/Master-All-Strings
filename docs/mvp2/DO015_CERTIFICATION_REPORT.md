# DO-015 certification report

**Certified, not published.** No MVP 2 tag exists, no release has been made, and
nothing here authorizes one. This record says the capability works and can be
verified; whether to publish it is a separate decision by someone else.

The machine-readable record is
[`DO015_INTEGRATION_EVIDENCE.json`](DO015_INTEGRATION_EVIDENCE.json), and
`python scripts/verify_do015_certification.py` reads it back against the
repository. This document is the synthesis; where the two disagree, the JSON is
what was measured.

## What was certified, and against what

```text
stage7_merge_sha      286d5aa439831ea44ff6e198a8518a45f076b513
stage8_product_sha    a29afb5e6972c5dfbf2266dee7a0ec47597c1d98
stage8_merge_sha      3fcf618b655c3f51b020d11a0bb3f96571da08d7   (PR #34)
stage9_base_sha       3fcf618b655c3f51b020d11a0bb3f96571da08d7
certified_product_sha 3fcf618b655c3f51b020d11a0bb3f96571da08d7
```

The Stage 8 product head is `a29afb5`, not the `f671a73` an earlier draft of the
Stage 9 order carried: two review-fix commits landed on that branch before it
merged. Certifying a SHA that was never the product would make every number
below unverifiable, so the actual head is recorded.

`certified_product_sha` equals `stage9_base_sha` because Stage 9 changes no
product file. That is not a claim, it is a check: the verifier enumerates the
diff from the certified commit and fails on anything outside `docs/`, `tests/`,
`web/mvp1/tests/` and `scripts/verify_do015_certification.py`.

## The capability

One guided-practice session, driven through the page's own controls, from the
first evaluated attempt to closure:

| Attempt | Recommendation | Learner | Execution | Runtime effect | Session after |
| --- | --- | --- | --- | --- | --- |
| 0 | `SLOW_DOWN` | Accepted | SUCCEEDED | rate → 0.75, no loop | `AWAITING_ATTEMPT` |
| 1 | `ISOLATE_PASSAGE` | Accepted | SUCCEEDED | loop set, rate unchanged | `AWAITING_ATTEMPT` |
| 2 | `CONTINUE` | Accepted | SUCCEEDED | no runtime mutation | `CLOSED` |

History rendered one, then two, then three attempts. Accept never touched
Transport. Apply executed the accepted action and nothing else. Each attempt
appended through the API rather than being pushed locally, and once an attempt
stopped being current it never changed again.

## Two witnesses, two different claims

Certification uses both, and they are not interchangeable.

**Reproducible — `node web/mvp1/tests/do015_certification_capture.mjs`.** Boots
the real `app.js` and drives it through Arm, Start, perform, Stop, Accept and
Apply. It proves application orchestration, the real UI event path and a
deterministic guided flow, and anyone can re-run it. It does **not** prove
rendering: it mints DOM objects rather than laying anything out. Ten tests in
`web/mvp1/tests/do015_certification.test.js` assert the same run, so the
artifact in `do015_artifacts/` cannot drift from what the suite proves.

**Authoritative lifecycle — `tests/mvp2/test_do015_certification_scenarios.py`.**
The browser witness mirrors the Stage 2 lifecycle in JavaScript, which is enough
for orchestration and not enough for the session digest — only the contract
computes that, and a mirror quoting its own placeholder would be quoting itself.
So the same three legs are driven through the real Stage 4 API over the Stage 2
service. The session closed with three attempts and a digest that recomputes to
what the service returned.

**Visual — not available.** No connected Chrome extension existed in this
environment, so there are no screenshots and **DOM rendering is not certified by
this tranche**. That is a real gap, recorded as one rather than papered over.

## Where the recommendations came from

No bundled lesson reaches `CONTINUE` by fake MIDI: the emitter plays notes the
demos do not contain, so a fake performance always produces findings, and
`CONTINUE` is what the policy returns when nothing is actionable.

The closure path therefore needed a **controlled lifecycle certification
scenario**, and this is the honest shape of one. The performance evidence is
synthetic — every expected note played, shifted by a fixed pattern — and
everything downstream is real. Each recommendation is the product evaluator's
answer to that evidence:

```text
alternating lateness  -> SLOW_DOWN        (4 findings)
sustained lateness    -> ISOLATE_PASSAGE  (9 findings)
clean                 -> CONTINUE         (0 findings)
```

None was hand-authored, and none is presented as a natural fake-MIDI outcome.
`tests/mvp2/test_do015_certification_scenarios.py` regenerates the artifact on
every run, so a policy change fails there rather than leaving a frozen record
describing behaviour the product no longer has.

## Authority boundaries, under adversarial conditions

Stage 8's matrix was re-run, not reimplemented: 12 Node and 70 Python
adversarial tests, all green. The crosswalk in
[`DO015_TRANCHE_PLAN.md`](DO015_TRANCHE_PLAN.md) maps each authority cell to a
test at `path:line`, and a verifier reads those citations back.

Two boundaries were additionally witnessed end to end through the page:

- **A re-cut canonical revision.** Same assignment, same content, new revision:
  the recorded session is preserved, `activeSession` is null, Accept, Decline
  and Apply are all inert, and the history region renders nothing.
- **A lesson switch.** The open session became `TRANSITIONED` through the
  service, and the next lesson started with no session at all.

## Results

```text
targeted DO-015 pytest     471 passed, 1 skipped
full pytest                2948 passed, 4 skipped, 2 failed *
coverage                   95.63%  (floor 95%)
Node                       505 passed, 0 failed      (Windows; no Linux CI)
ruff check src tests       PASS
mypy (strict)              PASS, 161 source files
fixture --check            PASS
check_in_flight.py         PASS
certification verifier     PASS
```

\* The two failures are Windows-only environment artifacts that reproduce on the
certified base with none of this tranche's code: a sha256 over a checked-in
bundle in a CRLF working copy, and a lineage script printing `→` through a
cp1252 console. Linux CI runs both and is authoritative. Stage 9 does not
authorize repairing them.

## Known limitations

- **DOM rendering is not certified.** No visual witness was available.
- **Node has no Linux CI coverage.** `verify.yml` has four Python steps and no
  Node step. Recorded, not repaired: the workflow is a deferred-hygiene path
  frozen by DO-012A, and unfreezing it needs an owner ruling.
- `VIEW_ONE_STRING` and `ENABLE_ZONE_VIEW` have no natural browser witness,
  because no bundled lesson produces them. They stay covered by unit tests and
  Stage 8.
- The reproducible witness mirrors the lifecycle in JavaScript; lifecycle truth
  and the session digest are certified separately, through the real API.

## Deferred

Carried forward, none of them a correctness defect:

- the Stage 8 crosswalk verifier checks citation shape, not semantic meaning;
- line-number citations are fragile — symbol-based `path::name` references would
  be better;
- the adversarial tests import private helpers from another test module;
- `check_in_flight.py` is not a CI gate, for the frozen-workflow reason above.

## The review question

> Can another engineer independently verify, from the frozen evidence and
> repository state, that DO-015 works end to end, preserves its authority
> boundaries under adversarial conditions, and is technically ready for a
> separate publication decision?

Yes, with the rendering gap named above. Every number here is reproducible from
this checkout: run the suites, run the capture, run the verifier.

Merge, tag, release and publication remain separate decisions and none of them
has been made.
