"""The in-flight register must disagree with the repository loudly -- but only
where somebody can do something about it.

Its whole value is that another agent can trust it, so the failure that matters
is a register which passes while saying something false. The failure that
wastes everyone's time is a check that goes red where nothing can be fixed.
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
THEIRS = "cursor/do015-next-ab12"
ROW = (
    f"| DO-015 Stage 8 | {THEIRS} | Claude | #40 "
    "| 286d5aa | in flight | 2026-09-21 |\n"
)
NO_PR_ROW = ROW.replace("#40", "—")
MINE = "fix/mine"
MY_ROW = ROW.replace(THEIRS, MINE).replace("#40", "#41")
MY_NO_PR_ROW = ROW.replace(THEIRS, MINE).replace("#40", "—")


def rows_of(text: str) -> list:
    rows, problems = check.parse_register(text)
    assert problems == []
    return rows


def run(
    text: str,
    open_prs: dict[str, int] | None,
    remote: set[str] | None,
    current: str | None,
) -> tuple[list[str], list[str]]:
    return check.reconcile(rows_of(text), open_prs, remote, current)


# --- parsing and validation: the file's own shape, wrong everywhere -----------


def test_the_checked_in_register_parses_and_validates() -> None:
    rows, problems = check.parse_register(REGISTER.read_text(encoding="utf-8"))
    assert problems == []
    assert check.validate_rows(rows) == []


def test_an_empty_table_means_nothing_is_in_flight() -> None:
    assert rows_of(HEADER + "\nSome prose.\n") == []


def test_rows_are_read_with_their_line_numbers() -> None:
    rows = rows_of(HEADER + ROW)
    assert len(rows) == 1
    assert rows[0].branch == THEIRS
    assert rows[0].pr_number == 40
    assert rows[0].state == "in flight"
    # Reported back to a human, so it has to point at the offending line.
    assert rows[0].line_number == 5


def test_only_the_in_flight_table_is_read() -> None:
    # The file carries other tables for humans; they must stay free to change.
    other = "\n## Stale branches\n\n| Branch | Why |\n| --- | --- |\n| old | merged |\n"
    assert [row.branch for row in rows_of(HEADER + ROW + other)] == [THEIRS]


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


def test_a_table_with_no_separator_does_not_swallow_its_first_row() -> None:
    # Without the `| --- |` line the first entry would be read as the separator
    # and vanish -- an in-flight branch nobody can see.
    broken = "## In flight\n\n| Order | Branch | Agent | PR | Base | State | Updated |\n" + ROW
    rows, problems = check.parse_register(broken)
    assert any("no '| --- |' separator" in item for item in problems)
    assert [row.branch for row in rows] == [THEIRS]


@pytest.mark.parametrize(
    ("cell", "replacement", "expected"),
    [
        ("Claude", "", "no agent"),
        ("in flight", "nearly done", "not one of"),
        ("286d5aa", "yesterday", "is not a sha"),
        ("#40", "40", "should look like"),
        ("2026-09-21", "21 Sept", "should be YYYY-MM-DD"),
        ("DO-015 Stage 8", "—", "no order"),
    ],
)
def test_a_malformed_cell_is_reported_with_its_line(
    cell: str, replacement: str, expected: str
) -> None:
    reported = check.validate_rows(rows_of(HEADER + ROW.replace(cell, replacement)))
    assert any(expected in item for item in reported), reported
    assert all("IN_FLIGHT.md:5" in item for item in reported)


def test_a_row_without_a_branch_is_useless() -> None:
    rows = rows_of(HEADER + ROW.replace(THEIRS, "—"))
    assert any("no branch" in item for item in check.validate_rows(rows))


def test_the_same_branch_twice_is_two_agents_or_one_stale_row() -> None:
    rows = rows_of(HEADER + ROW + ROW.replace("#40", "#41"))
    assert any("listed twice" in item for item in check.validate_rows(rows))


def test_the_same_pull_request_on_two_rows_is_refused() -> None:
    rows = rows_of(HEADER + ROW + ROW.replace(THEIRS, "cursor/something-else"))
    assert any("PR #40 is listed twice" in item for item in check.validate_rows(rows))


def test_the_offline_run_of_the_real_register_passes() -> None:
    assert check.main(["--offline"]) == 0


# --- where the checker is running ---------------------------------------------


@pytest.mark.parametrize(
    ("current", "working"),
    [(None, False), ("main", False), (MINE, True), ("cursor/anything", True)],
)
def test_only_a_named_branch_other_than_main_can_take_a_fix(
    current: str | None, working: bool
) -> None:
    assert check.on_working_branch(current) is working


# --- stale rows: finished work, cleared by the next branch ---------------------


def test_a_merged_row_fails_on_a_working_branch() -> None:
    # Clearing stale rows is a working branch's first job, so it is told to.
    failures, notes = run(HEADER + ROW, {}, {THEIRS}, MINE)
    assert len(failures) == 1
    assert "PR #40, which is no longer open" in failures[0]
    assert "clear it in this branch" in failures[0]
    assert notes == []


@pytest.mark.parametrize("current", ["main", None])
def test_a_merged_row_is_only_a_note_where_nothing_can_be_committed(
    current: str | None,
) -> None:
    # The recursion this replaces: a pull request cannot delete its own row,
    # so after every merge main carried one, and failing main for it meant a
    # cleanup pull request -- which needed a row of its own. From main, a
    # stale row is simply the next branch's first job.
    failures, notes = run(HEADER + ROW, {}, {THEIRS}, current)
    assert failures == []
    assert len(notes) == 1
    assert "the next branch clears it" in notes[0]


def test_a_merged_row_is_stale_even_while_its_branch_survives() -> None:
    # GitHub keeps merged branches unless told otherwise; the pull request is
    # what says the work finished.
    failures, _ = run(HEADER + ROW, {}, {THEIRS}, MINE)
    assert failures and "no longer open" in failures[0]


def test_a_row_with_no_pull_request_is_stale_once_its_branch_is_gone() -> None:
    failures, _ = run(HEADER + NO_PR_ROW, {}, set(), MINE)
    assert failures and "no longer on origin" in failures[0]
    failures, notes = run(HEADER + NO_PR_ROW, {}, set(), "main")
    assert failures == [] and "no longer on origin" in notes[0]


def test_a_row_with_no_pull_request_is_live_while_its_branch_exists() -> None:
    # Pushed, not yet proposed: that is work in progress, not finished work.
    assert run(HEADER + NO_PR_ROW, {}, {THEIRS}, MINE) == ([], [])


def test_your_own_unpushed_row_is_not_stale() -> None:
    # The row is written in the first commit, before there is anything to
    # push. A check that fails at the moment it is meant to be run teaches
    # people to stop running it.
    assert run(HEADER + MY_NO_PR_ROW, {}, set(), MINE) == ([], [])


def test_your_own_row_goes_stale_if_you_keep_working_after_it_merged() -> None:
    failures, _ = run(HEADER + MY_ROW, {}, {MINE}, MINE)
    assert failures and "PR #41, which is no longer open" in failures[0]


# --- this branch's own row and pull request -------------------------------------


def test_your_own_pull_request_without_a_row_fails() -> None:
    failures, notes = run(HEADER, {MINE: 41}, {MINE}, MINE)
    assert failures == ["PR #41 is open on this branch but has no row -- add yours"]
    assert notes == []


def test_your_own_row_must_record_its_pull_request() -> None:
    failures, notes = run(HEADER + MY_NO_PR_ROW, {MINE: 41}, {MINE}, MINE)
    assert len(failures) == 1 and "still has no PR" in failures[0]
    assert notes == []


def test_your_own_row_may_not_name_a_pull_request_open_elsewhere() -> None:
    failures, _ = run(HEADER + MY_ROW, {"someone/renamed": 41}, {MINE}, MINE)
    assert len(failures) == 1
    assert "puts PR #41 on fix/mine, but it is open on someone/renamed" in failures[0]


# --- other people's live work: true, useful, and not this branch's to fix -------


def test_another_open_pull_request_without_a_row_here_is_a_note() -> None:
    # The concurrency case the old check failed on. Every pull request's row
    # lives on its own branch until it merges, so two open at once each lack
    # the other's row -- and each failed for it.
    failures, notes = run(HEADER + MY_ROW, {MINE: 41, THEIRS: 40}, {MINE, THEIRS}, MINE)
    assert failures == []
    assert len(notes) == 1
    assert f"PR #40 is open on {THEIRS} with no row here" in notes[0]


def test_every_open_pull_request_is_a_note_from_main() -> None:
    # main held no rows for open pull requests, ever, and failed for each.
    failures, notes = run(HEADER, {MINE: 41, THEIRS: 40}, {MINE, THEIRS}, "main")
    assert failures == []
    assert len(notes) == 2


def test_another_rows_missing_pull_request_is_a_note() -> None:
    failures, notes = run(HEADER + NO_PR_ROW, {THEIRS: 40}, {THEIRS}, MINE)
    assert failures == []
    assert len(notes) == 1 and "still has no PR" in notes[0]


def test_another_rows_mismatched_pull_request_is_a_note() -> None:
    failures, notes = run(HEADER + ROW, {"someone/renamed": 40}, {THEIRS}, MINE)
    assert failures == []
    assert len(notes) == 1 and "puts PR #40" in notes[0]


def test_a_number_open_elsewhere_is_a_mismatch_not_a_stale_row() -> None:
    # Reported once, as what it is. Were it also stale, the same row would be
    # told both to be cleared and to be corrected.
    failures, notes = run(HEADER + ROW, {"someone/renamed": 40}, {THEIRS}, "main")
    findings = failures + notes
    assert len(findings) == 1
    assert "no longer open" not in findings[0]


# --- facts that could not be gathered ------------------------------------------


def test_nothing_is_claimed_when_github_and_origin_are_unreachable() -> None:
    assert run(HEADER + ROW, None, None, MINE) == ([], [])


def test_without_pull_requests_the_branch_still_decides_staleness() -> None:
    # No answer about #40, but its branch is known to be gone.
    failures, _ = run(HEADER + ROW, None, set(), MINE)
    assert failures and "no longer on origin" in failures[0]


def test_without_branches_a_closed_pull_request_still_decides_staleness() -> None:
    failures, _ = run(HEADER + ROW, {}, None, MINE)
    assert failures and "no longer open" in failures[0]


# --- the whole command ----------------------------------------------------------


def _world(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    register: str,
    open_prs: dict[str, int] | None,
    remote: set[str] | None,
    current: str | None,
) -> None:
    path = tmp_path / "IN_FLIGHT.md"
    path.write_text(register, encoding="utf-8")
    monkeypatch.setattr(check, "REGISTER", path)
    monkeypatch.setattr(check, "open_pull_requests", lambda: open_prs)
    monkeypatch.setattr(check, "remote_branches", lambda: remote)
    monkeypatch.setattr(check, "current_branch", lambda: current)


def test_main_stays_green_with_a_merged_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _world(monkeypatch, tmp_path, HEADER + ROW, {}, {THEIRS}, "main")
    assert check.main([]) == 0
    printed = capsys.readouterr().out
    assert "note  row for cursor/do015-next-ab12" in printed
    assert "OK (1 row, 1 note)" in printed


def test_a_working_branch_is_told_to_clear_a_merged_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _world(monkeypatch, tmp_path, HEADER + ROW + MY_ROW, {MINE: 41}, {MINE, THEIRS}, MINE)
    assert check.main([]) == 1
    printed = capsys.readouterr().out
    assert "FAIL  row for cursor/do015-next-ab12" in printed
    assert "clear it in this branch" in printed


def test_two_branches_in_flight_at_once_both_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The case that made a working register impossible to share: each branch
    # carries only its own row until it merges.
    open_prs = {MINE: 41, THEIRS: 40}
    remote = {MINE, THEIRS}
    _world(monkeypatch, tmp_path, HEADER + MY_ROW, open_prs, remote, MINE)
    assert check.main([]) == 0
    _world(monkeypatch, tmp_path, HEADER + ROW, open_prs, remote, THEIRS)
    assert check.main([]) == 0


def test_a_malformed_register_fails_even_on_main(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Notes are for drift nobody here can fix. A broken file is broken for
    # everyone, and main is exactly where it must not go quiet.
    _world(monkeypatch, tmp_path, HEADER + ROW.replace("#40", "40"), {}, {THEIRS}, "main")
    assert check.main([]) == 1


def test_unreachable_facts_are_noted_not_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _world(monkeypatch, tmp_path, HEADER + ROW, None, None, MINE)
    assert check.main([]) == 0
    printed = capsys.readouterr().out
    assert "could not list open pull requests" in printed
    assert "could not list branches on origin" in printed


# --- output ----------------------------------------------------------------------


def test_every_line_the_checker_prints_is_ascii(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The module says its output is ASCII only, so no print may bypass it.

    The failure path interpolates a path the filesystem handed over, and the
    register itself is written with em dashes. Either can carry a character a
    legacy console cannot encode, and a checker that crashes instead of
    reporting is not a checker.
    """

    missing = tmp_path / "IN_FLIGHT—missing.md"
    monkeypatch.setattr(check, "REGISTER", missing)
    assert check.main(["--offline"]) == 1
    printed = capsys.readouterr().out
    assert "missing" in printed
    printed.encode("ascii")
    printed.encode("cp437")


def test_findings_and_notes_carrying_an_em_dash_still_print(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _world(monkeypatch, tmp_path, HEADER + NO_PR_ROW, {}, set(), "main")
    assert check.main([]) == 0
    printed = capsys.readouterr().out
    assert "note" in printed
    printed.encode("ascii")
    printed.encode("cp437")


def test_git_output_is_decoded_as_utf8_not_the_locale() -> None:
    """On Windows the locale is a codepage and git speaks UTF-8.

    Decoded with the locale, every em dash in the register came back as three
    characters of mojibake. Linux CI defaults to UTF-8 and never sees it, so
    this only fails where the bug lives -- which is the point of keeping it.
    """

    committed = check._run(["git", "show", "HEAD:docs/development/IN_FLIGHT.md"])
    assert committed is not None
    assert "—" in committed, "the register should contain em dashes to test with"
    assert "â€”" not in committed, "em dashes came back as mojibake"


def test_your_own_pull_request_still_needs_its_own_row_when_another_claims_it() -> None:
    # Someone else's row wrongly naming this branch's number does not give
    # this branch a row. Both problems are reported: this branch lacks its
    # row, and the other row is wrong.
    failures, notes = run(HEADER + ROW.replace("#40", "#41"), {MINE: 41}, {MINE, THEIRS}, MINE)
    assert any("add yours" in item for item in failures)
    assert any("puts PR #41 on" in item for item in notes)
