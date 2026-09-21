# Agent instructions — Master-All-Strings

Read this before creating a branch or opening a pull request. It is read by
Cursor, Codex, and other coding agents. This repository has no `CLAUDE.md`; the
architecture and decision context lives in `docs/decisions/` (ADR-0001 through
ADR-0006) and in `governance/engine_architecture_v1.json`, the machine-readable
authority for the four-engine boundaries. Both apply too.

## Branch from current `main`. Always.

```bash
git fetch origin
git switch -c <branch-name> origin/main
```

Not from the workspace's current `HEAD`. Not from another branch. Not from a
branch belonging to a pull request that has not merged yet.

This is not style.

> **Drafted 2026-09-09 from this repository's own git history and pull-request
> record. Pending owner review.** Every commit, timestamp and count below was
> re-derived with `git log`, not taken from the pull-request prose. Correct or
> delete anything that misstates the record.

**A stacked merge put reviewed work on the wrong branch, and every status field
said it had succeeded.**

DO-005 (#8) was merged to `main` before review, then undone by reverting the
merge commit (#10). That set the revert-a-merge trap: re-merging
`feat/do-005-engine-governance` afterwards brought in *nothing*, because git
still treats an already-merged branch as merged even once its merge commit is
reverted. The re-land therefore had to be a fresh branch that reverted the
revert — `feat/do-005-reland` (#12).

DO-006 (#11) was then opened against that still-unmerged `feat/do-005-reland`,
not against `main`. The two merged 20 seconds apart:

    03:07:09   #12   feat/do-005-reland -> main            ec1cbf2
                     main receives DO-005 only

    03:07:29   #11   DO-006 -> feat/do-005-reland          3477de4
                     DO-006 lands on the intermediate branch

GitHub retargets a stacked pull request to `main` only *after* its base merges,
and #11 was merged inside that 20-second window. #13 then carried the
already-reviewed DO-006 tranche across by hand — 101 files, +13,787 and -2 lines
(`5aab8d7`, 22 minutes later). The resulting range is recorded as non-bisectable
in `2fa1a4d`.

Both #11 and #12 report `MERGED`. Nothing was red, and no field was wrong. That
is what makes this class hard to see: the work *is* merged, just not where it
was meant to go.

The self-check further down would have caught the base error before #11 was ever
opened — its merge base was `feat/do-005-reland`, never the tip of `main`. It
would **not** have caught the 20-second race, which is a merge-ordering hazard
with no pre-pull-request gate at all. That half is covered only by the rule
above: do not open a pull request against a branch belonging to a pull request
that has not merged yet.

If your branch is not cut from current `main`, "make it match
`main`" and "keep my changes" start pulling in opposite directions,
and no mechanical resolution is correct any more.

## If `main` moves while your branch is open

Merge, do not rebase:

```bash
git fetch origin && git merge origin/main
```

A rebase rewrites shas a reviewer has already read, and on a branch that was
cut from unmerged work it drops that work without saying so.

## Before you start

Read `docs/development/IN_FLIGHT.md`. It is the register of what every agent is
working on right now — you cannot see Cursor's conversation and Cursor cannot
see yours, so that file is the only thing you both read. Then confirm it against
the repository, because it is only as current as the last person who edited it:

```bash
git fetch origin
gh pr list --state open --json number,title,headRefName,files
```

If a register row or an open pull request already covers the surface you are
about to change, say so and stop rather than implementing the same order twice.

Add your own row in the **first commit on your branch**, before you push, and
set its state to `green` when the work is finished and the gates pass. Delete
the row when the pull request merges. `python scripts/check_in_flight.py`
reconciles the register against the open pull requests and the branches on
`origin`. Run it before you push. It is not a CI gate: the workflow is a
deferred-hygiene path frozen by DO-012A, so wiring it in needs an owner ruling.

A register cannot stop two agents colliding. It can only make the collision
visible before the second one starts.

## One dev order per branch

Do not fold an adjacent fix into an open order because it is convenient. If a
governance document names the authorized surfaces for a change, changing
anything else needs an owner ruling first — say so in the PR body rather than
merging it quietly.

## Nothing enforces this. Check it yourself.

There is no bot and no gate for the base rule. This file is the only thing
standing between you and the failure above. Before you open a pull request:

```bash
# The merge base must BE the tip of main, not merely an ancestor.
test "$(git merge-base HEAD origin/main)" = "$(git rev-parse origin/main)" \
  && echo "base is current" || echo "STALE — read this file again"
```

If the merge base turns out to be the head of an open pull request rather than
an old commit on `main`, you are stacked on unmerged work: do not
rebase, see above.

## Verifying locally

CI runs these on **Python 3.11** (`.github/workflows/verify.yml`). Run the same
four, in this order — the workflow keeps them as separate steps so a failure is
attributable to one gate rather than to "the build".

```bash
pip install -e ".[dev]"          # pytest, pytest-cov, ruff, mypy, jsonschema
ruff check src tests
mypy                             # no arguments: see below
pytest --cov --cov-report=term-missing
```

`mypy` and `pytest` take no targets on purpose. `[tool.mypy]` in `pyproject.toml`
sets `files = ["src"]` and `strict = true`; `[tool.coverage.report]` sets
`fail_under = 95`. The coverage floor lives in `pyproject.toml` rather than in
the CI command, so a local `pytest --cov` enforces exactly the policy the
workflow does. Do not pass `--cov-fail-under` on the command line, and do not
move the number to make a branch pass.
