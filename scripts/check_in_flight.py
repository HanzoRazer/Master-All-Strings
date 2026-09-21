#!/usr/bin/env python3
"""Reconcile the in-flight register against the repository.

A register nobody checks drifts, and a register that disagrees with the
repository is worse than none: it tells the next agent something false about
what is already being worked on. This reads
``docs/development/IN_FLIGHT.md`` and reports where it disagrees with the open
pull requests and the branches on ``origin``.

It reports; it does not edit. Exit status 0 means the register agrees with the
repository, 1 means it does not.
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

COLUMNS = ("Order", "Branch", "Agent", "PR", "Base", "State", "Updated")
STATES = ("in flight", "in review", "green", "blocked")
UNSET = {"—", "-", ""}

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

    rows: list[Row] = []
    for offset, line in enumerate(lines[header_at + 2 :], start=header_at + 3):
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
            problems.append(f"PR {row.pr!r} should look like '#32' or '—' ({where})")
        if not _DATE.match(row.updated):
            problems.append(f"updated {row.updated!r} should be YYYY-MM-DD ({where})")
        if not row.agent or row.agent in UNSET:
            problems.append(f"row has no agent ({where})")
    return problems


def reconcile(
    rows: list[Row],
    open_prs: dict[str, int] | None,
    remote_branches: set[str] | None,
    current_branch: str | None = None,
) -> list[str]:
    """Compare the register with what the repository actually has.

    ``open_prs`` maps head branch to pull-request number; either argument may be
    None when that fact could not be gathered, in which case those checks are
    skipped rather than guessed at.

    ``current_branch`` is exempt from having to exist on ``origin``: the row is
    written in the first commit of a branch, which is before it is pushed, and a
    check that fails in the moment you are told to run it teaches people to stop
    running it.
    """

    problems: list[str] = []
    listed = {row.branch for row in rows}

    if remote_branches is not None:
        for row in rows:
            if row.branch == current_branch:
                continue
            if row.branch not in remote_branches:
                problems.append(
                    f"register lists {row.branch}, which is not on origin "
                    f"(IN_FLIGHT.md:{row.line_number}) -- delete the row if it merged"
                )

    if open_prs is not None:
        for branch, number in sorted(open_prs.items()):
            if branch not in listed:
                problems.append(
                    f"PR #{number} is open on {branch} but has no row in the register"
                )
        open_numbers = set(open_prs.values())
        for row in rows:
            number = row.pr_number
            if number is not None and number not in open_numbers:
                problems.append(
                    f"register names PR #{number}, which is not open "
                    f"(IN_FLIGHT.md:{row.line_number}) -- delete the row if it merged"
                )
    return problems


def _run(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=60
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
        print(f"FAIL  {REGISTER} does not exist")
        return 1

    rows, problems = parse_register(REGISTER.read_text(encoding="utf-8"))
    problems += validate_rows(rows)

    skipped: list[str] = []
    if args.offline:
        skipped.append("offline: git and GitHub were not consulted")
    else:
        prs = open_pull_requests()
        branches = remote_branches()
        if prs is None:
            skipped.append("could not list open pull requests (gh unavailable?)")
        if branches is None:
            skipped.append("could not list branches on origin")
        problems += reconcile(rows, prs, branches, current_branch())

    for note in skipped:
        print(f"note  {note}")
    if problems:
        for problem in problems:
            print(f"FAIL  {problem}")
        print(f"\nin-flight register: {len(problems)} problem(s)")
        return 1

    count = len(rows)
    print(f"in-flight register: OK ({count} branch{'' if count == 1 else 'es'} in flight)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
