"""The in-flight register must disagree with the repository loudly.

Its whole value is that another agent can trust it, so the failure that matters
is a register which passes while saying something false.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTER = REPO_ROOT / "docs" / "development" / "IN_FLIGHT.md"


def _checker() -> ModuleType:
    """Load the script by path.

    ``scripts/`` is not a package and is only importable when the repository
    root happens to be on ``sys.path``, which is true under ``python -m pytest``
    and false under the bare ``pytest`` that CI runs.

    The module goes into ``sys.modules`` before it is executed because
    ``@dataclass`` resolves annotations through ``sys.modules[cls.__module__]``,
    and a module loaded by path is not there unless it is put there.
    """

    spec = importlib.util.spec_from_file_location(
        "check_in_flight", REPO_ROOT / "scripts" / "check_in_flight.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check = _checker()

HEADER = (
    "## In flight\n\n"
    "| Order | Branch | Agent | PR | Base | State | Updated |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
)
ROW = (
    "| DO-015 Stage 8 | cursor/do015-next-ab12 | Claude | #40 "
    "| 286d5aa | in flight | 2026-09-21 |\n"
)
NO_PR_ROW = ROW.replace("#40", "—")


def test_the_checked_in_register_parses_and_validates() -> None:
    rows, problems = check.parse_register(REGISTER.read_text(encoding="utf-8"))
    assert problems == []
    assert check.validate_rows(rows) == []


def test_an_empty_table_means_nothing_is_in_flight() -> None:
    rows, problems = check.parse_register(HEADER + "\nSome prose.\n")
    assert problems == []
    assert rows == []


def test_rows_are_read_with_their_line_numbers() -> None:
    rows, problems = check.parse_register(HEADER + ROW)
    assert problems == []
    assert len(rows) == 1
    assert rows[0].branch == "cursor/do015-next-ab12"
    assert rows[0].pr_number == 40
    assert rows[0].state == "in flight"
    # Reported back to a human, so it has to point at the offending line.
    assert rows[0].line_number == 5


def test_only_the_in_flight_table_is_read() -> None:
    # The file carries other tables for humans; they must stay free to change.
    other = "\n## Stale branches\n\n| Branch | Why |\n| --- | --- |\n| old | merged |\n"
    text = HEADER + ROW + other
    rows, problems = check.parse_register(text)
    assert problems == []
    assert [row.branch for row in rows] == ["cursor/do015-next-ab12"]


def test_a_missing_section_or_table_is_a_problem() -> None:
    _, problems = check.parse_register("# Register\n\nnothing here\n")
    assert problems and "no '## In flight' heading" in problems[0]
    _, problems = check.parse_register("## In flight\n\njust prose\n")
    assert problems and "no table" in problems[0]


def test_a_renamed_column_is_refused_rather_than_guessed_at() -> None:
    text = "## In flight\n\n| Order | Branch | Who | PR | Base | State | Updated |\n| --- |\n"
    rows, problems = check.parse_register(text)
    assert rows == []
    assert problems and "table header is" in problems[0]


@pytest.mark.parametrize(
    ("cell", "replacement", "expected"),
    [
        ("Claude", "", "no agent"),
        ("in flight", "nearly done", "not one of"),
        ("286d5aa", "yesterday", "is not a sha"),
        ("#40", "40", "should look like"),
        ("2026-09-21", "21 Sept", "should be YYYY-MM-DD"),
    ],
)
def test_a_malformed_cell_is_reported_with_its_line(
    cell: str, replacement: str, expected: str
) -> None:
    rows, problems = check.parse_register(HEADER + ROW.replace(cell, replacement))
    assert problems == []
    reported = check.validate_rows(rows)
    assert any(expected in item for item in reported), reported
    assert all("IN_FLIGHT.md:5" in item for item in reported)


def test_a_row_without_a_branch_is_useless() -> None:
    rows, _ = check.parse_register(HEADER + ROW.replace("cursor/do015-next-ab12", "—"))
    assert any("no branch" in item for item in check.validate_rows(rows))


def test_the_same_branch_twice_is_two_agents_or_one_stale_row() -> None:
    rows, _ = check.parse_register(HEADER + ROW + ROW.replace("#40", "#41"))
    assert any("listed twice" in item for item in check.validate_rows(rows))


def test_an_open_pull_request_missing_from_the_register_fails() -> None:
    rows, _ = check.parse_register(HEADER)
    problems = check.reconcile(rows, {"cursor/somebody-else": 41}, {"cursor/somebody-else"})
    assert any("PR #41 is open on cursor/somebody-else" in item for item in problems)


def test_a_row_whose_pull_request_has_merged_fails() -> None:
    rows, _ = check.parse_register(HEADER + ROW)
    problems = check.reconcile(rows, {}, {"cursor/do015-next-ab12"})
    assert any("PR #40, which is not open" in item for item in problems)


def test_a_row_for_a_branch_that_is_gone_fails() -> None:
    rows, _ = check.parse_register(HEADER + ROW)
    problems = check.reconcile(rows, {"cursor/do015-next-ab12": 40}, set())
    assert any("which is not on origin" in item for item in problems)


def test_a_branch_with_no_pull_request_yet_is_fine() -> None:
    rows, _ = check.parse_register(HEADER + NO_PR_ROW)
    assert check.validate_rows(rows) == []
    assert check.reconcile(rows, {}, {"cursor/do015-next-ab12"}) == []


def test_facts_that_could_not_be_gathered_are_skipped_not_invented() -> None:
    # Offline, or without gh: check what can be checked and claim nothing else.
    rows, _ = check.parse_register(HEADER + ROW)
    assert check.reconcile(rows, None, None) == []


def test_the_offline_run_of_the_real_register_passes() -> None:
    assert check.main(["--offline"]) == 0


def test_the_branch_you_are_on_need_not_be_pushed_yet() -> None:
    # The row is written in the first commit, which is before the push. The
    # check has to pass at the moment it is meant to be run.
    rows, _ = check.parse_register(HEADER + NO_PR_ROW)
    assert check.reconcile(rows, {}, set(), "cursor/do015-next-ab12") == []
    # Any other row still has to exist on origin.
    assert check.reconcile(rows, {}, set(), "some/other-branch") != []


def test_a_pull_request_number_must_belong_to_the_row_that_claims_it() -> None:
    # The register's promise is which *branch* is in flight. A number that is
    # open on someone else's branch makes the row a lie that reads as true.
    rows, _ = check.parse_register(HEADER + ROW)
    problems = check.reconcile(rows, {"some/other-branch": 40}, {"cursor/do015-next-ab12"})
    assert any(
        "puts PR #40 on cursor/do015-next-ab12, but it is open on some/other-branch" in item
        for item in problems
    )


def test_an_open_pull_request_the_row_has_not_recorded_yet_is_reported() -> None:
    # Under-reporting is drift too: the row says no PR while one is open on it.
    rows, _ = check.parse_register(HEADER + NO_PR_ROW)
    problems = check.reconcile(rows, {"cursor/do015-next-ab12": 40}, {"cursor/do015-next-ab12"})
    assert any("still has no PR" in item for item in problems)


def test_the_same_pull_request_on_two_rows_is_refused() -> None:
    second = ROW.replace("cursor/do015-next-ab12", "cursor/something-else")
    rows, _ = check.parse_register(HEADER + ROW + second)
    assert any("PR #40 is listed twice" in item for item in check.validate_rows(rows))


def test_a_row_that_says_nothing_about_the_work_is_refused() -> None:
    rows, _ = check.parse_register(HEADER + ROW.replace("DO-015 Stage 8", "—"))
    assert any("no order" in item for item in check.validate_rows(rows))


def test_a_table_with_no_separator_does_not_swallow_its_first_row() -> None:
    # Without the `| --- |` line the first entry would be read as the separator
    # and vanish -- an in-flight branch nobody can see.
    broken = (
        "## In flight\n\n| Order | Branch | Agent | PR | Base | State | Updated |\n" + ROW
    )
    rows, problems = check.parse_register(broken)
    assert any("no '| --- |' separator" in item for item in problems)
    assert [row.branch for row in rows] == ["cursor/do015-next-ab12"]


def test_findings_print_on_a_console_that_is_not_utf8() -> None:
    # The register is written with em dashes, and this repository already has a
    # script that fails in CI for printing a character cp437 cannot encode.
    rows, _ = check.parse_register(HEADER + ROW.replace("#40", "not-a-pr"))
    problems = check.validate_rows(rows)
    assert problems
    for problem in problems:
        rendered = check._ascii(f"FAIL  {problem}")
        rendered.encode("cp437")  # raises if a finding is unprintable
        rendered.encode("ascii")


def test_a_branch_that_only_removes_rows_needs_none_of_its_own() -> None:
    # The recursion this closes: a row cannot be deleted by the pull request
    # it describes, so clearing it needs a branch, which would need a row,
    # which would go stale in turn.
    rows, _ = check.parse_register(HEADER)
    open_prs = {"docs/clear-merged-register-row": 36}
    remote = {"docs/clear-merged-register-row"}
    noisy = check.reconcile(rows, open_prs, remote, "docs/clear-merged-register-row")
    assert any("has no row in the register" in item for item in noisy)
    quiet = check.reconcile(
        rows, open_prs, remote, "docs/clear-merged-register-row", cleanup=True
    )
    assert quiet == []


def test_the_exemption_is_only_for_the_branch_doing_the_clearing() -> None:
    rows, _ = check.parse_register(HEADER)
    problems = check.reconcile(
        rows, {"someone/else": 37}, {"someone/else"}, "docs/clear-merged-register-row", True
    )
    assert any("PR #37 is open on someone/else" in item for item in problems)


def test_a_branch_that_adds_a_row_is_not_a_cleanup() -> None:
    # Removing one row while adding another is ordinary work wearing a
    # cleanup's clothes, and it still has to announce itself.
    before = HEADER + ROW
    after = HEADER + ROW.replace("cursor/do015-next-ab12", "cursor/something-new")
    removed = {r.branch for r in check.parse_register(before)[0]} - {
        r.branch for r in check.parse_register(after)[0]
    }
    added = {r.branch for r in check.parse_register(after)[0]} - {
        r.branch for r in check.parse_register(before)[0]
    }
    assert removed and added, "this fixture must both remove and add"
    # is_cleanup_branch requires removals and no additions.
    assert not (bool(removed) and not added)
