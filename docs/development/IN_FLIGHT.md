# In-flight register

One row per branch someone is working on **right now**. Several agents work this
repository — Cursor, Codex, Claude — and none of them can see each other's
conversations. This file is the only place they can all read to find out what is
already being worked on.

It is not a plan and not a history. A row appears when work starts, and once its
pull request merges the next branch clears it.

## In flight

| Order | Branch | Agent | PR | Base | State | Updated |
| --- | --- | --- | --- | --- | --- | --- |
| DO-015 Stage 10 | cursor/do015-publication-closeout-cc03 | Claude | — | fd2c490 | in flight | 2026-09-22 |

An empty table means nothing is in flight.

### How to use it

Add your row in the **first commit on the branch**, before you push:

```markdown
| DO-015 Stage 8 | cursor/do015-attempt-review-ab12 | Claude | — | 286d5aa | in flight | 2026-09-21 |
```

- **Order** — the Dev Order and stage, or a short phrase for repository work.
- **Branch** — exactly as it exists on `origin`.
- **Agent** — Cursor, Codex, Claude. Whoever is driving.
- **PR** — `#32` once opened, `—` until then.
- **Base** — the `origin/main` sha the branch was cut from. AGENTS.md explains
  why this one matters more than it looks.
- **State** — one of:

  | State | Means |
  | --- | --- |
  | `in flight` | Being worked on. The head may change under you. |
  | `in review` | Pushed, review or CI outstanding. |
  | `green` | Gates pass, work finished, waiting to be merged. |
  | `blocked` | Stopped, needs an owner ruling. Say why in the Order column. |

- **Updated** — the date you last touched the row, `YYYY-MM-DD`.

Update `State` when it changes — particularly to `green`, which is what says
the branch is finished and safe to merge. Fill in `PR` as soon as the pull
request exists.

### When a row is finished

A row cannot be deleted by the pull request it describes: the merge lands after
the last commit, so every row outlives its branch. That is expected, not drift.

**Any branch in flight clears a finished row** — any row whose pull request has
closed or merged, or which never named one and whose branch is gone from
`origin`.

- Rows already finished when you start: clear them in your **first commit**,
  with your own row.
- Rows that finish while you work: clear them in the **next commit you make
  anyway**. The check will name them.

Whoever is in flight when a row finishes clears it. That is why the check fails
on every working branch and not on some designated one: no branch is nominated,
none waits for another, and none opens a pull request just to clear a row. Two
branches clearing the same row delete the same line, which merges cleanly.

If nothing is in flight, the row waits. It is a note on `main`, and the next
branch to start clears it.

### What fails, and what is only a note

The checker fails only on what can be fixed from where it is run:

| Finding | On your branch | On `main` or a detached head |
| --- | --- | --- |
| The register is malformed | fails | fails |
| A finished row | fails — clear it | note |
| Your own pull request has no row, or your row is wrong | fails | — |
| Your branch has more than one open pull request | fails | — |
| Another open pull request has no row here | note | note |
| Another row is wrong, or another branch has two pull requests | note | note |
| A pull request from a fork | note | note |

A finished row fails on a working branch because clearing it is that branch's
job; from `main` it is true, and nobody's to fix there. Another open pull
request having no row in *your* copy is the register working, not failing: each
branch carries only its own row until it merges.

A branch carries one order into `main`, so it has one open pull request, and
one row names it. A fork's pull request has no branch on `origin` and so no
row; it is noted, never matched to a branch here that shares its name.

Nothing in this section names a branch, a pull request or a commit, on purpose.
Prose that did would go stale every time something merged.

Run `python scripts/check_in_flight.py` before pushing. It reconciles this file
against the open pull requests and the branches on `origin` and reports where
they disagree. It is not a CI gate yet — the workflow is a deferred-hygiene path
frozen by DO-012A — so for now the register stays honest because agents check
it, not because the build does.

## Before you start

Read this file, then confirm it against the repository — the register can only
be as current as the last person who edited it:

```bash
git fetch origin
gh pr list --state open --limit 500 --json number,title,headRefName,files
```

If someone else's row already covers the surface you were about to change, say
so and stop, per AGENTS.md. Two agents implementing the same order is the
expensive failure this file exists to prevent.

## Stale branches on `origin`

These are **not** in flight. They survive because their pull requests were
squash-merged (the branch tip never became an ancestor of `main`) or because
they never had one at all. `git branch -r --no-merged origin/main` lists all
four, which makes them look live when they are not.

| Branch | Last commit | Why it is still there |
| --- | --- | --- |
| `cursor/mvp1f-interactive-fretboard-90b8` | 2026-08-11 | PR #17 merged; branch left behind |
| `recovery/mvp1-squash-merge` | 2026-08-16 | Recovery branch; no PR |
| `cursor/mvp2b-teaching-timeline-90b8` | 2026-08-23 | PR #20 merged; branch left behind |
| `agent/curriculum-smart-notation-roadmap` | 2026-07-22 | No PR; never proposed |

They can be deleted whenever the owner is content that nothing unmerged is on
them. Until then this table is what stops the next agent reading them as work in
progress.
