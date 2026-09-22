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


@pytest.fixture(autouse=True)
def only_the_register_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test to a branch that touched nothing but the register.

    Without this the cleanup tests would ask real git what changed, and on any
    branch that changed more than the register the new scope guard would make
    them return False for a reason they were never written to test -- passing
    vacuously. The scope tests below override it on purpose.
    """

    monkeypatch.setattr(check, "changed_files", lambda: {check.REGISTER_PATH})


def _is_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    before: str,
    after: str,
    open_prs: dict[str, int] | None = None,
    remote_branches: set[str] | None = None,
) -> bool:
    """Run the real predicate against fixture registers, never live git state.

    The default world is one where the removed row has finished: no open pull
    requests, and its branch gone from origin.
    """

    register = tmp_path / "IN_FLIGHT.md"
    register.write_text(after, encoding="utf-8")
    monkeypatch.setattr(check, "REGISTER", register)
    monkeypatch.setattr(
        check, "register_at", lambda ref: before if ref == "origin/main" else None
    )
    return check.is_cleanup_branch(
        "docs/clear-merged-register-row",
        {} if open_prs is None else open_prs,
        set() if remote_branches is None else remote_branches,
    )


def test_removing_rows_without_other_edits_is_a_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert _is_cleanup(monkeypatch, tmp_path, HEADER + ROW, HEADER)


def test_removing_a_row_and_adding_a_row_is_not_a_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = HEADER + ROW
    after = HEADER + ROW.replace("cursor/do015-next-ab12", "cursor/something-new")
    assert not _is_cleanup(monkeypatch, tmp_path, before, after)


def test_removing_a_row_and_editing_a_retained_row_is_not_a_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The bypass a branch-name comparison misses: clear a stale row and change
    # someone else's state on the way past, and the exemption would have let
    # the whole thing through unannounced.
    retained = ROW.replace("cursor/do015-next-ab12", "cursor/retained-row")
    before = HEADER + ROW + retained
    after = HEADER + retained.replace("in flight", "blocked")
    assert not _is_cleanup(monkeypatch, tmp_path, before, after)


def test_a_retained_row_may_move_down_the_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Position is the one thing a deletion is allowed to change.
    retained = ROW.replace("cursor/do015-next-ab12", "cursor/retained-row")
    before = HEADER + ROW + retained
    after = HEADER + retained
    assert _is_cleanup(monkeypatch, tmp_path, before, after)


def test_editing_rows_without_removing_one_is_not_a_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = HEADER + ROW
    after = HEADER + ROW.replace("in flight", "green")
    assert not _is_cleanup(monkeypatch, tmp_path, before, after)


def test_cleanup_needs_a_branch_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    register = tmp_path / "IN_FLIGHT.md"
    register.write_text(HEADER, encoding="utf-8")
    monkeypatch.setattr(check, "REGISTER", register)
    monkeypatch.setattr(check, "register_at", lambda _ref: HEADER + ROW)
    assert not check.is_cleanup_branch(None)


def test_cleanup_cannot_be_decided_without_origin_main(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Unreadable is not the same as unchanged: refuse rather than assume.
    register = tmp_path / "IN_FLIGHT.md"
    register.write_text(HEADER, encoding="utf-8")
    monkeypatch.setattr(check, "REGISTER", register)
    monkeypatch.setattr(check, "register_at", lambda _ref: None)
    assert not check.is_cleanup_branch("docs/clear-merged-register-row")


def test_the_register_can_be_read_from_another_ref() -> None:
    # is_cleanup_branch is worthless if this silently returns None: the branch
    # then looks like ordinary work and the recursion comes back. It did,
    # because the helper takes a whole command and "git" was missing from it.
    assert check.register_at("HEAD") is not None
    assert "## In flight" in check.register_at("HEAD")
    assert check.register_at("refs/heads/no-such-branch-here") is None


def test_cleanup_cannot_reword_the_register(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Prose is policy here. Rewriting it while deleting a row is a register
    # change, and a register change is the thing this file announces.
    before = "Rows are cleared when they merge.\n\n" + HEADER + ROW
    after = "Rows are cleared whenever, honestly.\n\n" + HEADER
    assert not _is_cleanup(monkeypatch, tmp_path, before, after)


def test_cleanup_cannot_rename_a_column(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = HEADER + ROW
    after = HEADER.replace("| Agent |", "| Who |")
    assert not _is_cleanup(monkeypatch, tmp_path, before, after)


def test_cleanup_cannot_drop_the_separator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = HEADER + ROW
    after = HEADER.replace("| --- | --- | --- | --- | --- | --- | --- |\n", "")
    assert not _is_cleanup(monkeypatch, tmp_path, before, after)


def test_cleanup_cannot_leave_content_the_parser_skips(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A malformed row is a parse problem, and a register nobody can parse is
    # not a register anybody can be exempted for tidying.
    before = HEADER + ROW
    after = HEADER + "| too | few | columns |\n"
    assert not _is_cleanup(monkeypatch, tmp_path, before, after)


def test_cleanup_cannot_start_from_a_register_that_will_not_parse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = HEADER.replace("| Agent |", "| Who |") + ROW
    after = HEADER.replace("| Agent |", "| Who |")
    assert not _is_cleanup(monkeypatch, tmp_path, before, after)


def test_cleanup_cannot_append_anything_after_the_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    before = HEADER + ROW
    after = HEADER + "\nA note nobody asked for.\n"
    assert not _is_cleanup(monkeypatch, tmp_path, before, after)


def test_a_line_ending_difference_is_not_a_register_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A CRLF checkout must not cost a branch its exemption. Only the side that
    # bypasses the file can carry CRLF in a test: reading a file normalises it
    # anyway, which is why the comparison normalises what git hands back too.
    before = (HEADER + ROW).replace("\n", "\r\n")
    after = HEADER
    assert _is_cleanup(monkeypatch, tmp_path, before, after)


def test_normalising_touches_line_endings_and_nothing_else() -> None:
    assert check._normalise("a\r\nb\n") == "a\nb\n"
    assert check._normalise("| a | b |\n") == "| a | b |\n"


def test_cleanup_is_refused_on_a_register_that_was_already_broken(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The case the document comparison alone cannot see.

    Here the branch really does remove exactly one row and change nothing
    else, so deriving the expected document says yes. But the register it is
    tidying carries a row nobody can parse, and both sides carry it equally,
    so the difference is invisible. Handing out an exemption on a file that
    does not parse is how a broken register stays broken and unannounced.
    """

    malformed = "| too | few | columns |\n"
    before = HEADER + ROW + malformed
    after = HEADER + malformed
    assert not _is_cleanup(monkeypatch, tmp_path, before, after)


def test_a_cleanup_may_not_remove_a_row_whose_work_is_live(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The exemption is for rows that have finished, not for any row at all.

    Used on live work it would let one branch delete another's announcement
    and skip making its own, which is worse than the problem it solves.
    """

    assert not _is_cleanup(
        monkeypatch,
        tmp_path,
        HEADER + ROW,
        HEADER,
        open_prs={"cursor/do015-next-ab12": 40},
        remote_branches={"cursor/do015-next-ab12"},
    )


def test_a_row_is_live_if_its_number_is_open_under_another_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The row claims PR #40 and #40 is open, even if the branch name has
    # drifted. Still live, still not this branch's to clear.
    assert not _is_cleanup(
        monkeypatch,
        tmp_path,
        HEADER + ROW,
        HEADER,
        open_prs={"someone/renamed": 40},
        remote_branches=set(),
    )


def test_a_row_with_no_pull_request_is_live_while_its_branch_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Nothing was ever announced to GitHub, so the branch is the only evidence
    # of whether the work is going on.
    assert not _is_cleanup(
        monkeypatch,
        tmp_path,
        HEADER + NO_PR_ROW,
        HEADER,
        open_prs={},
        remote_branches={"cursor/do015-next-ab12"},
    )


def test_a_row_with_no_pull_request_and_no_branch_is_stale(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert _is_cleanup(
        monkeypatch, tmp_path, HEADER + NO_PR_ROW, HEADER, open_prs={}, remote_branches=set()
    )


def test_a_merged_row_is_stale_even_if_its_branch_survives(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # GitHub keeps merged branches unless told otherwise; the pull request is
    # what says the work finished.
    assert _is_cleanup(
        monkeypatch,
        tmp_path,
        HEADER + ROW,
        HEADER,
        open_prs={},
        remote_branches={"cursor/do015-next-ab12"},
    )


def test_staleness_cannot_be_assumed_when_github_is_unreachable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Not being able to tell is not the same as stale, and this predicate
    # hands out an exemption.
    register = tmp_path / "IN_FLIGHT.md"
    register.write_text(HEADER, encoding="utf-8")
    monkeypatch.setattr(check, "REGISTER", register)
    monkeypatch.setattr(check, "register_at", lambda _ref: HEADER + ROW)
    assert not check.is_cleanup_branch("docs/clear-merged-register-row", None, set())


def test_a_row_with_no_pull_request_needs_the_branch_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    register = tmp_path / "IN_FLIGHT.md"
    register.write_text(HEADER, encoding="utf-8")
    monkeypatch.setattr(check, "REGISTER", register)
    monkeypatch.setattr(check, "register_at", lambda _ref: HEADER + NO_PR_ROW)
    assert not check.is_cleanup_branch("docs/clear-merged-register-row", {}, None)


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


def test_findings_carrying_an_em_dash_still_print(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    register = tmp_path / "IN_FLIGHT.md"
    register.write_text(HEADER + ROW.replace("2026-09-21", "—"), encoding="utf-8")
    monkeypatch.setattr(check, "REGISTER", register)
    assert check.main(["--offline"]) == 1
    printed = capsys.readouterr().out
    printed.encode("ascii")
    printed.encode("cp437")


def test_a_cleanup_may_not_change_anything_but_the_register(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Deleting a stale row is not cover for editing code. A branch that does
    # both has work to announce like any other.
    monkeypatch.setattr(
        check, "changed_files", lambda: {check.REGISTER_PATH, "src/master_all_strings/x.py"}
    )
    assert not _is_cleanup(monkeypatch, tmp_path, HEADER + ROW, HEADER)


def test_a_cleanup_must_actually_change_the_register(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(check, "changed_files", lambda: {"docs/other.md"})
    assert not _is_cleanup(monkeypatch, tmp_path, HEADER + ROW, HEADER)


def test_an_unknown_diff_refuses_the_exemption(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(check, "changed_files", lambda: None)
    assert not _is_cleanup(monkeypatch, tmp_path, HEADER + ROW, HEADER)


def test_git_output_is_decoded_as_utf8_not_the_locale() -> None:
    """The regression that made the exemption dead on Windows.

    `subprocess.run(text=True)` decodes with the locale, which on Windows is a
    codepage. The register is full of em dashes, and each came back as three
    characters of mojibake, so the cleanup comparison could never match there.
    Linux CI defaults to UTF-8 and never saw it; the other tests here mock
    register_at and could not have.
    """

    committed = check.register_at("HEAD")
    assert committed is not None
    assert "—" in committed, "the register should contain em dashes to test with"
    assert "â€”" not in committed, "em dashes came back as mojibake"
