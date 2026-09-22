#!/usr/bin/env python3
"""Reconcile the in-flight register against the repository.

A register nobody checks drifts, and a register that disagrees with the
repository is worse than none: it tells the next agent something false about
what is already being worked on. This reads
``docs/development/IN_FLIGHT.md`` and reports where it disagrees with the open
pull requests and the branches on ``origin``.

It reports; it does not edit. Exit status 0 means the register agrees with the
repository, 1 means it does not.

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
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "docs" / "development" / "IN_FLIGHT.md"

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


def reconcile(
    rows: list[Row],
    open_prs: dict[str, int] | None,
    remote_branches: set[str] | None,
    current_branch: str | None = None,
    cleanup: bool = False,
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
                if cleanup and branch == current_branch:
                    # A branch that only removes rows is not work to collide
                    # with, and requiring it to add one would just leave the
                    # next person another row to clear.
                    continue
                problems.append(
                    f"PR #{number} is open on {branch} but has no row in the register"
                )
        # A number on its own proves nothing: the register's promise is which
        # *branch* is in flight, so the number has to belong to that branch.
        head_of = {number: branch for branch, number in open_prs.items()}
        for row in rows:
            where = f"IN_FLIGHT.md:{row.line_number}"
            number = row.pr_number
            if number is None:
                if row.branch in open_prs:
                    problems.append(
                        f"PR #{open_prs[row.branch]} is open on {row.branch} but the "
                        f"register row still has no PR ({where})"
                    )
                continue
            head = head_of.get(number)
            if head is None:
                problems.append(
                    f"register names PR #{number}, which is not open "
                    f"({where}) -- delete the row if it merged"
                )
            elif head != row.branch:
                problems.append(
                    f"register puts PR #{number} on {row.branch}, but it is open on "
                    f"{head} ({where})"
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


def _normalise(text: str) -> str:
    """Line endings only. A CRLF checkout is not a register change."""

    return text.replace("\r\n", "\n")


def register_at(ref: str) -> str | None:
    """The register as some other ref has it, or None if it cannot be read."""

    return _run(["git", "show", f"{ref}:docs/development/IN_FLIGHT.md"])


def _removed_rows_are_stale(
    before: list[Row],
    removed: set[str],
    open_prs: dict[str, int] | None,
    remote_branches: set[str] | None,
) -> bool:
    """True when every row this branch deleted had already finished.

    Fails closed. If the open pull requests could not be listed there is no way
    to know whether a row was live, and guessing would hand out the exemption
    on exactly the occasion it should be refused.
    """

    if open_prs is None:
        return False
    open_numbers = set(open_prs.values())
    for row in before:
        if row.branch not in removed:
            continue
        if row.branch in open_prs:
            return False
        number = row.pr_number
        if number is not None:
            if number in open_numbers:
                return False
            continue
        # No pull request was ever named, so the branch itself is the evidence.
        if remote_branches is None or row.branch in remote_branches:
            return False
    return True


def is_cleanup_branch(
    current: str | None,
    open_prs: dict[str, int] | None = None,
    remote_branches: set[str] | None = None,
) -> bool:
    """True when this branch only removes rows from the register.

    A row cannot be deleted by the pull request it describes: the merge lands
    after the last commit, so the row outlives its own branch and the register
    on main goes stale. Someone then has to clear it, and that someone needs a
    branch, which needs a row, which goes stale in turn.

    The way out is to notice what a cleanup branch is. If a branch removes
    rows and touches nothing else, it is not work anyone else could collide
    with, and demanding it announce itself is what makes the recursion.

    "Touches nothing else" has to mean the whole file. Comparing branch names
    would let a branch change a retained row's state on the way past;
    comparing parsed rows would still let it rewrite the prose, the heading,
    the column names or the separator, or leave malformed content the parser
    skips. All of those are register changes, and a register change is the one
    thing this file exists to announce.

    So the test is exact: take the register as `origin/main` has it, delete
    precisely the rows this branch dropped, and require the result to be
    byte-for-byte what the branch has. Anything else -- a word of prose, a
    column, a stray line -- and this is ordinary work that announces itself
    like everything else.

    And the rows removed must already be stale. The exemption exists for
    clearing rows whose work has landed; used on a live row it would let one
    branch delete another's announcement and skip making its own, which is
    worse than the problem it solves. A row is stale when its pull request is
    no longer open, or -- for a row that never named one -- when its branch is
    gone from `origin`. Not being able to tell is not the same as stale.
    """

    if current is None:
        return False
    theirs = register_at("origin/main")
    if theirs is None:
        return False
    ours = REGISTER.read_text(encoding="utf-8") if REGISTER.exists() else ""
    before, before_problems = parse_register(theirs)
    after, after_problems = parse_register(ours)
    if before_problems or after_problems:
        # A register nobody can parse is not a register anybody can be
        # exempted for tidying.
        return False

    # Position is the one field a deletion is allowed to move.
    was = {row.branch: replace(row, line_number=0) for row in before}
    now = {row.branch: replace(row, line_number=0) for row in after}
    removed = set(was) - set(now)
    if not removed or set(now) - set(was):
        return False
    if not _removed_rows_are_stale(before, removed, open_prs, remote_branches):
        return False

    dropped_lines = {row.line_number for row in before if row.branch in removed}
    lines = _normalise(theirs).split("\n")
    expected = "\n".join(
        line for number, line in enumerate(lines, start=1) if number not in dropped_lines
    )
    return expected == _normalise(ours)


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
        current = current_branch()
        cleanup = is_cleanup_branch(current, prs, branches)
        problems += reconcile(rows, prs, branches, current, cleanup)

    for note in skipped:
        print(_ascii(f"note  {note}"))
    if problems:
        for problem in problems:
            print(_ascii(f"FAIL  {problem}"))
        print(_ascii(f"\nin-flight register: {len(problems)} problem(s)"))
        return 1

    count = len(rows)
    print(
        _ascii(f"in-flight register: OK ({count} branch{'' if count == 1 else 'es'} in flight)")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
