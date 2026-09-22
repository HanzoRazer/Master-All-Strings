# In-flight register

One row per branch someone is working on **right now**. Several agents work this
repository — Cursor, Codex, Claude — and none of them can see each other's
conversations. This file is the only place they can all read to find out what is
already being worked on.

It is not a plan and not a history. A branch appears when work starts and the
row is deleted when the pull request merges.

## In flight

| Order | Branch | Agent | PR | Base | State | Updated |
| --- | --- | --- | --- | --- | --- | --- |

Nothing is in flight. `main` is at `102b795` (DO-015 Stage 9, PR #35).

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
request exists: a row that still says `—` while a pull request is open is drift
like any other. Delete the row when the PR merges.

That last step cannot happen inside the pull request it describes: the merge
lands after the final commit, so a row outlives its own branch and the register
on `main` goes stale until someone clears it. Clearing it takes a branch, and a
branch would need a row, which would go stale in turn.

So a branch that only **removes** rows needs no row of its own. The checker
works that out by comparing this file against `origin/main`: rows removed,
none added, and every row that stays identical apart from its position. Change
a retained row's agent or state on the way past and it is ordinary register
work again, which has to announce itself like anything else. Clear a
merged row either in the first commit of the next branch, which is the usual
way, or in a cleanup branch of its own.

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
gh pr list --state open --json number,title,headRefName,files
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
