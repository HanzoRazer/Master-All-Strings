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
#: register is somebody's next branch's job, not a failure.
DEFAULT_BRANCH = "main"

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
        rows.append(Row(*cells, line_number=offset))
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
    open_prs: dict[str, int] | None,
    remote_branches: set[str] | None,
    current_branch: str | None = None,
) -> tuple[list[str], list[str]]:
    """Compare the register with the repository. Returns (failures, notes).

    The split is the whole design. Each finding fails only when it can be
    fixed from here, and is a note otherwise:

    * a stale row -- its pull request no longer open, or, for a row that never
      named one, its branch gone from origin -- fails on a working branch,
      whose first commit is where stale rows get cleared, and is a note
      everywhere else;
    * a finding about this branch's own row or pull request fails on this
      branch;
    * a finding about anyone else's live work is a note. Their row lives on
      their branch until it merges, so its absence from this copy is the
      register working, not failing.

    ``open_prs`` maps head branch to pull-request number; either fact may be
    None when it could not be gathered, and the checks needing it are skipped
    rather than guessed at.
    """

    failures: list[str] = []
    notes: list[str] = []
    working = on_working_branch(current_branch)
    listed = {row.branch for row in rows}
    open_numbers = set(open_prs.values()) if open_prs is not None else None
    head_of = {number: branch for branch, number in (open_prs or {}).items()}

    def report(message: str, fixable_here: bool) -> None:
        (failures if fixable_here else notes).append(message)

    for row in rows:
        where = f"IN_FLIGHT.md:{row.line_number}"
        own = working and row.branch == current_branch
        number = row.pr_number

        # Stale: the work this row announces has finished. A known pull
        # request is the better evidence -- GitHub keeps merged branches -- so
        # the branch only decides when there is no number, or no answer about
        # it. This branch's own row is never stale for being unpushed: the row
        # is written in the first commit, before there is anything to push.
        if number is not None and open_numbers is not None:
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

        if open_prs is None:
            continue
        if number is not None:
            head = head_of.get(number)
            if head is not None and head != row.branch:
                # A number that is open on someone else's branch makes the row
                # a lie that reads as true.
                report(
                    f"register puts PR #{number} on {row.branch}, but it is open on "
                    f"{head} ({where})",
                    own,
                )
        elif row.branch in open_prs:
            report(
                f"PR #{open_prs[row.branch]} is open on {row.branch} but the "
                f"register row still has no PR ({where})",
                own,
            )

    if open_prs is not None:
        claimed = {row.pr_number for row in rows if row.pr_number is not None}
        for branch, number in sorted(open_prs.items()):
            if branch in listed:
                continue
            own_pr = working and branch == current_branch
            if number in claimed and not own_pr:
                # A row already claims this number under another branch, and
                # that mismatch is reported against the row. Saying the pull
                # request has no row as well would be false: it has the wrong one.
                continue
            if own_pr:
                report(f"PR #{number} is open on this branch but has no row -- add yours", True)
            else:
                report(
                    f"PR #{number} is open on {branch} with no row here -- its row "
                    "lives on its own branch until it merges",
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


def open_pull_requests() -> dict[str, int] | None:
    """Open PRs by head branch, or None when GitHub could not be reached."""

    out = _run(["gh", "pr", "list", "--state", "open", "--json", "number,headRefName"])
    if out is None:
        return None
    try:
        return {item["headRefName"]: int(item["number"]) for item in json.loads(out)}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def current_branch() -> str | None:
    """The checked-out branch, or None on a detached head or outside git."""

    out = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    name = out.strip() if out else ""
    return name if name and name != "HEAD" else None


def remote_branches() -> set[str] | None:
    """Branch names on origin, or None when the remote could not be listed."""

    out = _run(["git", "ls-remote", "--heads", "origin"])
    if out is None:
        return None
    names = set()
    for line in out.splitlines():
        _, _, ref = line.partition("\t")
        if ref.startswith("refs/heads/"):
            names.add(ref[len("refs/heads/") :])
    return names or None


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
            notes.append("could not list open pull requests (gh unavailable?)")
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
