# DO-015 Publication Report — Mainline Publication Candidate

## Status

```text
DO-015
CERTIFIED
READY FOR PUBLICATION
NOT YET PUBLISHED
```

Publication is the owner's merge of this pull request. Nothing in this branch
claims it has happened, and no later commit flips this status: the next Dev
Order records the merge commit as the publication baseline. A status that has
to be corrected after the fact is a status nobody can trust.

## Lineage

| Field | Value |
| --- | --- |
| Certified product | `3fcf618b655c3f51b020d11a0bb3f96571da08d7` |
| Stage 9 head | `eba01a1b232ac31ef5433a80e7f5572c439111c0` |
| Stage 9 merge (PR #35) | `102b7959ac6a99c924baada89ce3b04d779c209d` |
| Stage 10 base | `fd2c490e58ac1a46cb184ac04fe8b910b659080d` |
| Stage 10 branch | `cursor/do015-publication-closeout-cc03` |
| Publication baseline | `null` — the Stage 10 merge commit |
| `mvp-1` | `ac38819b23ed9d85b651755e7612f42d7d528ddc` |

## Certified product identity

`3fcf618` is what DO-015 *is*. It is the Stage 8 merge, and Stage 9 certified
it without changing a product file. Every commit after it in this lineage is
evidence, tooling or documentation.

## Stage 9 certification identity

Certification is a separate identity from the product: Stage 9, PR #35, merged
as `102b795`, recorded in `DO015_INTEGRATION_EVIDENCE.json` and
`DO015_CERTIFICATION_REPORT.md`. **Stage 10 changes neither file.** They are a
freeze, and a freeze that gets edited to describe later events is not one.

This stage does not re-derive certification. `verify_do015_publication.py` runs
Stage 9's own verifier and its evidence generator `--check`, and reports what
they say.

## Publication candidate identity

The candidate is this branch. It is deliberately *not* recorded as a sha in
`DO015_PUBLICATION_EVIDENCE.json`: a commit cannot contain its own identity,
and trying makes every commit demand one more. The verifier measures the
product surface from the certified product to `HEAD` at run time, so the record
never needs to name the commit it lives in.

### The base is checked, not just recorded

`stage10_base_sha` is compared against the branch point — `git merge-base HEAD
origin/main` — rather than checked for presence or ancestry. Every commit back
to the certification is an ancestor of this branch, so an ancestry test alone
would accept a base that misstates where publication was prepared from. Once
this branch merges there is no branch point left to compare, and the run says
the field was not enforced rather than inventing a verdict.

## What is being published

The certified DO-015 capability, unchanged, integrated into `main`:

- guided practice session orchestration as certified at `3fcf618`;
- its certification evidence chain, still verifiable by its own tools;
- an explicit statement that the mainline now carries both.

## What is not being claimed

```text
MVP 2 RELEASED      — no
MVP 2 TAGGED        — no
v2.0.0              — no
PRODUCT RELEASED    — no
MVP 2 COMPLETE      — no
```

`mvp-1` remains the only tag in the repository. No tag or release is created by
this stage, and an unexpected MVP 2 tag stops it rather than being removed.

## Post-certification changes

Five pull requests merged between the certified product and this base. None
touches the product:

| PR | Merge | What it changed |
| --- | --- | --- |
| #36 | `775e3f1` | In-flight register tooling |
| #37 | `8c93fc8` | In-flight register prose |
| #38 | `fcd837b` | Register row cleared |
| #39 | `d6c870a` | Register row cleared |
| #40 | `fd2c490` | The register check fails only on what it can fix |

The protected surface — `src/master_all_strings/**`, `web/mvp1/**` outside its
tests, `resources/**`, `governance/**` — shows **zero** changed files across
that range. The verifier re-measures it on every run; this table is a summary,
not the evidence.

## Verification results

| Gate | Result |
| --- | --- |
| Publication verifier | OK (9 of 9) |
| Stage 9 certification verifier | OK (9 of 9) |
| Stage 9 evidence generator `--check` | OK |
| Protected product surface | 0 changed files since `3fcf618` |
| Publication verifier tests | 47 passed |
| DO-015 targeted tests (Python) | 311 passed |
| Node suite | 505 passed, 0 failed |
| Reproducible browser witness | PASS |
| Full pytest | 3069 passed, 3 skipped, 2 failed |
| Coverage | 95.63% (floor 95%) |
| Ruff | PASS |
| Strict mypy | PASS |
| Guided-session fixtures `--check` | OK |
| In-flight register | OK |
| Tags | `mvp-1` unchanged; no MVP 2 tag, local or on `origin` |

The reproducible witness was re-run and compared against the Stage 9 artifact:
identical apart from freshly generated session and attempt UUIDs, with the
final status, every evaluation digest and the canonical revision unchanged. The
artifact was then restored, so **Stage 9's evidence is byte-for-byte untouched
by this stage**.

The two pytest failures are the two documented Windows-only platform artifacts,
unchanged by this stage and green on Linux CI, which is authoritative. The PR's
own CI run is the Linux result.

## Known limitations

Carried forward from Stage 9 exactly as certified, and **not** repaired to make
this report read better:

- DOM rendering is not certified: no connected browser, no visual witness, no
  screenshots;
- Node has no Linux CI coverage; the Node suite is certified on Windows only;
- the reproducible browser witness mirrors the Stage 2 lifecycle in JavaScript;
  lifecycle truth and the session digest are certified through the real Stage 4
  API;
- `VIEW_ONE_STRING` and `ENABLE_ZONE_VIEW` have no natural browser witness;
- Stage 8 citation and test-maintenance debt remains deferred;
- neither the publication verifier nor the certification verifier is a CI gate:
  `verify.yml` is a deferred-hygiene path frozen by DO-012A. Their unit tests
  run under the normal pytest gate.

## Next baseline rule

```text
do015_publication_baseline_sha = <the merge commit of this pull request>
```

The next MVP 2 Dev Order records that sha and cites `3fcf618` as the DO-015
product identity. Product identity, certification identity and publication
baseline stay three separate fields; collapsing them is how a documentation
commit ends up being cited as the product.

## Final reviewer question

> Is the certified DO-015 capability still unchanged, fully traceable, and
> ready to be declared a published mainline MVP 2 baseline, without rewriting
> its certification evidence or implying that MVP 2 itself has been released?

**YES.** The certified product is an ancestor of this branch, the protected
product surface has not changed a byte since it, Stage 9's evidence is
untouched and still passes its own verifier, and nothing here claims a release.
