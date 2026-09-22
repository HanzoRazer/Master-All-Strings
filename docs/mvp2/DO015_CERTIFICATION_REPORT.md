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
for orchestration and not enough for anything the service decides — only the
contract computes the digest, and a mirror quoting its own placeholder would be
quoting itself. So the same legs are driven through the real Stage 4 API over
the Stage 2 service. The session closed with three attempts and a digest that
recomputes to what the service returned, and a fourth session was transitioned
through the same route.

The division of labour is the point, and the claims are kept apart:

```text
JS mirror witness       page orchestration, UI event sequencing
Python service witness  lifecycle truth, transition truth, digest truth
```

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
- **A lesson switch.** Two witnesses, deliberately separated. Through the page:
  the open session is stood down and the next lesson starts with no session at
  all. Through the real Stage 4 API: an open session becomes `TRANSITIONED`,
  its attempts unchanged, its digest recomputing — and its own assignment and
  content pins **unchanged**, because a transition marks a record terminal
  rather than moving it to the new lesson.

## Results

```text
targeted DO-015 pytest     491 passed
full pytest                2968 passed, 3 skipped, 2 failed *
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

## Three defects the certification found in itself

None was in the product. All three are recorded because a certification that
hides its own misfires is not worth much.

**The immutability witness measured the wrong thing.** The first browser
witness reported attempt 0 as mutated. It froze the attempt before that
attempt's own Accept and Apply, so a legitimate lifecycle read as tampering.
Immutability is a claim about an attempt that is no longer current.

**A boundary check can only see committed work, and I kept forgetting.** Three
times a check passed with a change in the working tree and failed the moment
it was committed: the fixture digests, a product script swept in by
`git add -A scripts` after a stray `ruff --fix`, and the CI seal. The rule is
simple and worth stating for the next person: **run the boundary checks after
committing, not before.** The swept-in product change -- one unused import
removed from `scripts/build_projection_fixtures.py` -- was reverted. It was
almost certainly harmless, which is exactly why a rule rather than a judgement
is what keeps it out.

**The CI seal contradicted its own rule.** The record says everything after
the named run is metadata, but the seal lived in the generator, so recording a
run was a code change that the rule forbade. The seal is a data artifact now,
and sealing touches `docs/mvp2` and nothing else.

## One defect found in the digests

The first CI run failed on `Stage 3 fixture bytes match the record`. The
verifier had been digesting the fixture files as they sit in the working copy,
which on Windows means CRLF and on Linux means LF -- so the record was a
property of the checkout rather than of the content, and it could not pass on
both platforms at once. This repository already has a test failing for that
exact reason, which is what made it recognisable.

Fixed by normalising CRLF to LF before hashing, and the evidence records the
method alongside the digests so nobody has to guess later. The defect was in
the certification tooling, not the product; no product file changed.

## How to read this, and in what order

Four things carry the certification, and they are not equal:

| | Source of truth | Why it ranks here |
| --- | --- | --- |
| 1 | the suites and the capture script | executable; the only things that can be wrong in a way that matters |
| 2 | the artifacts under `do015_artifacts/` | written by the product, regenerated and compared by those suites |
| 3 | `DO015_INTEGRATION_EVIDENCE.json` | assembled by a committed generator, checked by the verifier |
| 4 | this report | prose, and the weakest of the four |

Where any two disagree, the earlier one wins. The report is written for a
reader; the JSON is written for a checker; the artifacts are written by the
product; the suites *are* the product.

### The verifier is a maintenance contract

`verify_do015_certification.py` is deliberately strict, and strictness has a
cost: it hard-codes the required sections, the frozen predecessor SHAs, and the
allowlist of paths that may move after the certified commit. When the
repository changes shape, that script has to be updated with it.

That is the intended bargain, not an oversight. A check that quietly tolerates
a renamed section is not evidence of anything. Treat it as a contract with two
obligations: if a certification surface moves, update `ALLOWED_PREFIXES`; if
the record grows or loses a section, update `REQUIRED_SECTIONS` and say why in
the tranche plan. Its own tests are negative cases, so breaking it usually
fails loudly rather than silently.

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
this checkout:

```text
python scripts/build_do015_certification_evidence.py --check
python scripts/verify_do015_certification.py
pytest tests/mvp2/test_do015_certification_scenarios.py
node web/mvp1/tests/do015_certification_capture.mjs
```

The first of those is what makes the claim true of this record and not only of
the numbers in it. The evidence JSON is built by a committed generator, so a
reviewer can rebuild it rather than take its assembly on trust; `--check` fails
if the committed record is not what the generator produces.

Merge, tag, release and publication remain separate decisions and none of them
has been made.
