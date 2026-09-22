#!/usr/bin/env python3
"""Reconcile the in-flight register against the repository.

A register nobody checks drifts, and a register that disagrees with the
repository is worse than none: it tells the next agent something false about
what is already being worked on. This reads
``docs/development/IN_FLIGHT.md`` and reports where it disagrees with the open
pull requests and the branches on ``origin``.

It fails only on what can be fixed from where it is run. A malformed register
fails everywhere. A finding about this branch's own row fails on this branch.
A row whose work has finished fails on a working branch, because clearing it
is that branch's first job. Everything else -- another pull request's row that
lives on its own branch, a stale row seen from ``main`` where nothing can be
committed -- is reported as a note: true, useful, and nobody here's to fix.

It reports; it does not edit. Exit status 1 means there is something to fix
here; notes never change it.

Output is ASCII only, like the other verifiers here. The register is written
with em dashes and a check that cannot print its own findings on a legacy
console is not a check.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "docs" / "development" / "IN_FLIGHT.md"

#: The branch nothing is committed to directly. Seen from here, drift in the
#: register is somebody's next branch's job, not a failure. Named, not asked of
#: git: ``origin/HEAD`` is unset in a clone made with ``git remote add``, and
#: AGENTS.md already fixes the name -- every branch is cut from ``main``.
DEFAULT_BRANCH = "main"

#: gh lists 30 pull requests unless told otherwise, and says nothing about the
#: rest. A register checked against the first 30 is unchecked from the 31st, so
#: ask for more than this repository will ever have open -- and if even that
#: many come back, report the list as unavailable rather than check a part of it.
PR_LIMIT = 500

COLUMNS = ("Order", "Branch", "Agent", "PR", "Base", "State", "Updated")
STATES = ("in flight", "in review", "green", "blocked")
UNSET = {"—", "-", ""}

_SEPARATOR = re.compile(r"^\|?[\s:|-]*-[\s:|-]*\|?$")
_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_PR = re.compile(r"^#\d+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class Row:
    """One register entry, as written."""

    order: str
    branch: str
    agent: str
    pr: str
    base: str
    state: str
    updated: str
    line_number: int

    @property
    def pr_number(self) -> int | None:
        return int(self.pr[1:]) if _PR.match(self.pr) else None


@dataclass(frozen=True)
class PullRequest:
    """One open pull request, as GitHub reports it."""

    number: int
    branch: str
    #: The fork's owner when the head branch is not on origin, else None. A
    #: fork's branch can share a name with one here and be nothing to do with it.
    fork: str | None = None

    @property
    def head(self) -> str:
        return f"{self.fork}:{self.branch}" if self.fork else self.branch


def _open(numbers: list[int]) -> str:
    listed = ", ".join(f"#{number}" for number in numbers)
    return f"PR {listed} is open" if len(numbers) == 1 else f"PRs {listed} are open"


def _ascii(text: str) -> str:
    """Fold to ASCII so a finding can always be printed.

    The register is written with em dashes and the paths in failures are
    whatever the filesystem hands over. A checker that raises
    UnicodeEncodeError instead of reporting is not a checker, and this
    repository already has a script failing in CI for exactly that.
    """

    return text.replace("—", "-").encode("ascii", "replace").decode("ascii")


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_register(text: str) -> tuple[list[Row], list[str]]:
    """Read the rows under the `## In flight` heading.

    Returns the rows and any problems with the table itself. Only that one
    table is read: the rest of the file is prose for humans, including other
    tables, and must stay free to change.
    """

    problems: list[str] = []
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "## In flight")
    except StopIteration:
        return [], ["IN_FLIGHT.md has no '## In flight' heading"]

    header_at = None
    for offset, line in enumerate(lines[start + 1 :], start=start + 1):
        if line.lstrip().startswith("## "):
            break
        if line.lstrip().startswith("|"):
            header_at = offset
            break
    if header_at is None:
        return [], ["the '## In flight' section has no table"]

    header = _cells(lines[header_at])
    if tuple(header) != COLUMNS:
        problems.append(
            f"table header is {header}, expected {list(COLUMNS)} "
            f"(IN_FLIGHT.md:{header_at + 1})"
        )
        return [], problems

    # A markdown table needs the `| --- |` line. Without it the first entry
    # would be read as the separator and silently vanish -- an in-flight branch
    # no one can see is the exact failure this file exists to prevent.
    separator = lines[header_at + 1] if header_at + 1 < len(lines) else ""
    first_row = header_at + 2
    if not _SEPARATOR.match(separator.strip()):
        problems.append(
            f"table has no '| --- |' separator under its header "
            f"(IN_FLIGHT.md:{header_at + 2})"
        )
        first_row = header_at + 1

    rows: list[Row] = []
    for offset, line in enumerate(lines[first_row:], start=first_row + 1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        cells = _cells(line)
        if len(cells) != len(COLUMNS):
            problems.append(
                f"row has {len(cells)} columns, expected {len(COLUMNS)} "
                f"(IN_FLIGHT.md:{offset})"
            )
            continue
        order, branch, agent, pr, base, state, updated = cells
        rows.append(Row(order, branch, agent, pr, base, state, updated, offset))
    return rows, problems


def validate_rows(rows: list[Row]) -> list[str]:
    """Check each row on its own terms, before consulting the repository."""

    problems: list[str] = []
    seen: dict[str, int] = {}
    seen_prs: dict[int, int] = {}
    for row in rows:
        where = f"IN_FLIGHT.md:{row.line_number}"
        if not row.branch or row.branch in UNSET:
            problems.append(f"row has no branch ({where})")
            continue
        if row.branch in seen:
            problems.append(
                f"branch {row.branch} is listed twice ({where} and line {seen[row.branch]})"
            )
        seen[row.branch] = row.line_number
        if row.state not in STATES:
            problems.append(f"state {row.state!r} is not one of {list(STATES)} ({where})")
        if row.base not in UNSET and not _SHA.match(row.base):
            problems.append(f"base {row.base!r} is not a sha ({where})")
        if row.pr not in UNSET and not _PR.match(row.pr):
            problems.append(f"PR {row.pr!r} should look like '#32', or '-' if none ({where})")
        if not _DATE.match(row.updated):
            problems.append(f"updated {row.updated!r} should be YYYY-MM-DD ({where})")
        if not row.agent or row.agent in UNSET:
            problems.append(f"row has no agent ({where})")
        if not row.order or row.order in UNSET:
            problems.append(f"row has no order ({where})")
        number = row.pr_number
        if number is not None:
            if number in seen_prs:
                problems.append(
                    f"PR #{number} is listed twice ({where} and line {seen_prs[number]})"
                )
            seen_prs[number] = row.line_number
    return problems


def on_working_branch(current: str | None) -> bool:
    """True on a branch someone can commit a fix to.

    ``main`` takes no direct commits, and a detached head -- CI, or somebody
    inspecting an old commit -- has no branch at all. From either, drift in the
    register is real but belongs to whichever branch comes next.
    """

    return current is not None and current != DEFAULT_BRANCH


def reconcile(
    rows: list[Row],
    open_prs: list[PullRequest] | None,
    remote_branches: set[str] | None,
    current_branch: str | None = None,
) -> tuple[list[str], list[str]]:
    """Compare the register with the repository. Returns (failures, notes).

    The split is the whole design. Each finding fails only when it can be
    fixed from here, and is a note otherwise:

    * a row whose branch has an open pull request is live, never stale; if
      it names no pull request or a different one, it is wrong, and that is a
      finding about whoever owns the branch;
    * a stale row -- its pull request no longer open, or, for a row that never
      named one and only then, its branch gone from origin -- fails on a
      working branch,
      whose first commit is where stale rows get cleared, and is a note
      everywhere else;
    * a finding about this branch's own row or pull request fails on this
      branch;
    * a finding about anyone else's live work is a note. Their row lives on
      their branch until it merges, so its absence from this copy is the
      register working, not failing.

    A branch carries one order into ``main``, so it has at most one open pull
    request; more than one is itself a finding, owned by that branch. A pull
    request from a fork has no branch on origin and so no row -- it is noted,
    never matched to a branch here that happens to share its name.

    Either fact may be None when it could not be gathered, and the checks
    needing it are skipped rather than guessed at.
    """

    failures: list[str] = []
    notes: list[str] = []
    working = on_working_branch(current_branch)
    listed = {row.branch for row in rows}
    prs = sorted(open_prs or [], key=lambda pr: pr.number)
    open_numbers = {pr.number for pr in prs} if open_prs is not None else None
    head_of = {pr.number: pr.head for pr in prs}
    on_branch: dict[str, list[int]] = {}
    for pr in prs:
        if pr.fork is None:
            on_branch.setdefault(pr.branch, []).append(pr.number)

    def report(message: str, fixable_here: bool) -> None:
        (failures if fixable_here else notes).append(message)

    for row in rows:
        where = f"IN_FLIGHT.md:{row.line_number}"
        own = working and row.branch == current_branch
        number = row.pr_number

        # A branch with an open pull request is live, whatever its row says, so
        # the row is wrong rather than finished. Asked first: a branch reused
        # after its first pull request closed still names the closed number,
        # and calling that stale would say "clear it" -- delete a live row --
        # where the fix is to point it at the open one.
        live = on_branch.get(row.branch, [])
        if live:
            if number is None:
                report(
                    f"{_open(live)} on {row.branch} but the register row still has "
                    f"no PR ({where})",
                    own,
                )
            elif number not in live:
                report(
                    f"row for {row.branch} names PR #{number}, but on {row.branch} "
                    f"{_open(live)} ({where})",
                    own,
                )
            continue

        # Stale: the work this row announces has finished. A row that names a
        # pull request is judged by that pull request and nothing else. With
        # no answer from GitHub there is no verdict: a branch gone from origin
        # cannot tell a merged row from a live one, and "clear it" on that
        # guess deletes the register's record of work still in flight -- the
        # failure this file exists to prevent, caused by the check meant to
        # prevent it. The branch decides only for a row that named no pull
        # request. This branch's own row is never stale for being unpushed:
        # the row is written in the first commit, before there is anything to
        # push.
        if number is not None:
            if open_numbers is None:
                continue
            stale = number not in open_numbers
            why = f"names PR #{number}, which is no longer open"
        else:
            stale = (
                remote_branches is not None
                and row.branch not in remote_branches
                and row.branch != current_branch
            )
            why = "names a branch no longer on origin"
        if stale:
            if working:
                report(f"row for {row.branch} {why} ({where}) -- clear it in this branch", True)
            else:
                report(f"row for {row.branch} {why} ({where}) -- the next branch clears it", False)
            continue

        # Not stale, and no pull request open on its own branch: the only way
        # left for the number to be open is on someone else's branch, which
        # makes the row a lie that reads as true.
        head = head_of.get(number) if number is not None else None
        if head is not None:
            report(
                f"register puts PR #{number} on {row.branch}, but it is open on "
                f"{head} ({where})",
                own,
            )

    claimed = {row.pr_number for row in rows if row.pr_number is not None}
    for branch, numbers in sorted(on_branch.items()):
        own_pr = working and branch == current_branch
        if len(numbers) > 1:
            report(
                f"{_open(numbers)} on {branch} -- a branch carries one order into "
                "main, so close all but one",
                own_pr,
            )
        if branch in listed:
            continue
        if own_pr:
            report(f"{_open(numbers)} on this branch but has no row -- add yours", True)
            continue
        # A number a row already claims under another branch is reported
        # against that row. Saying it has no row as well would be false: it
        # has the wrong one.
        unclaimed = [number for number in numbers if number not in claimed]
        if unclaimed:
            report(
                f"{_open(unclaimed)} on {branch} with no row here -- its row "
                "lives on its own branch until it merges",
                False,
            )
    for pr in prs:
        if pr.fork is not None and pr.number not in claimed:
            report(
                f"PR #{pr.number} is open from a fork ({pr.head}) -- the register "
                "lists branches on origin, so it has no row",
                False,
            )
    return failures, notes


def _run(command: list[str]) -> str | None:
    try:
        # Decode as UTF-8, not the locale. On Windows the locale is a codepage,
        # and git and gh speak UTF-8: branch names and anything else they hand
        # back would otherwise arrive as mojibake there while Linux passes.
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def open_pull_requests() -> list[PullRequest] | None:
    """Every open PR, or None when GitHub could not list them all."""

    fields = "number,headRefName,isCrossRepository,headRepositoryOwner"
    out = _run(
        ["gh", "pr", "list", "--state", "open", "--limit", str(PR_LIMIT), "--json", fields]
    )
    if out is None:
        return None
    try:
        prs = [
            PullRequest(
                int(item["number"]),
                item["headRefName"],
                # A deleted fork has no owner left to name.
                ((item.get("headRepositoryOwner") or {}).get("login") or "unknown")
                if item["isCrossRepository"]
                else None,
            )
            for item in json.loads(out)
        ]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError):
        return None
    return prs if len(prs) < PR_LIMIT else None


def current_branch() -> str | None:
    """The checked-out branch, or None on a detached head or outside git."""

    out = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    name = out.strip() if out else ""
    return name if name and name != "HEAD" else None


def remote_branches() -> set[str] | None:
    """Branch names on origin, or None when the remote could not be listed.

    An empty set is an answer -- origin has no branches -- not a failure to get
    one, and is returned as such.
    """

    out = _run(["git", "ls-remote", "--heads", "origin"])
    if out is None:
        return None
    names = set()
    for line in out.splitlines():
        _, _, ref = line.partition("\t")
        if ref.startswith("refs/heads/"):
            names.add(ref[len("refs/heads/") :])
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="check the table's own shape only; do not consult git or GitHub",
    )
    args = parser.parse_args(argv)

    if not REGISTER.exists():
        print(_ascii(f"FAIL  {REGISTER} does not exist"))
        return 1

    rows, problems = parse_register(REGISTER.read_text(encoding="utf-8"))
    problems += validate_rows(rows)

    notes: list[str] = []
    if args.offline:
        notes.append("offline: git and GitHub were not consulted")
    else:
        prs = open_pull_requests()
        branches = remote_branches()
        if prs is None:
            notes.append(
                "could not list every open pull request (gh unavailable, or "
                f"{PR_LIMIT} or more open)"
            )
        if branches is None:
            notes.append("could not list branches on origin")
        failures, found = reconcile(rows, prs, branches, current_branch())
        problems += failures
        notes += found

    for note in notes:
        print(_ascii(f"note  {note}"))
    if problems:
        for problem in problems:
            print(_ascii(f"FAIL  {problem}"))
        print(_ascii(f"\nin-flight register: {len(problems)} problem(s)"))
        return 1

    rows_word = "row" if len(rows) == 1 else "rows"
    notes_word = "note" if len(notes) == 1 else "notes"
    print(_ascii(f"in-flight register: OK ({len(rows)} {rows_word}, {len(notes)} {notes_word})"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
