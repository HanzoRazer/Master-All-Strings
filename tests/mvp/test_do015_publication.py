"""DO-015 publication verifier: what it refuses to publish.

A verifier that only ever sees a correct tree proves nothing -- it would pass
just as happily if it classified nothing at all. These feed it the failures it
exists to catch, one per class, and the real record to show the classes are not
so broad that nothing can satisfy them.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "verify_do015_publication.py"
EVIDENCE = REPO_ROOT / "docs" / "mvp2" / "DO015_PUBLICATION_EVIDENCE.json"
CERTIFICATION = REPO_ROOT / "docs" / "mvp2" / "DO015_INTEGRATION_EVIDENCE.json"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_do015_publication", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def verifier() -> ModuleType:
    return _load()


@pytest.fixture
def evidence() -> dict[str, Any]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def certification() -> dict[str, Any]:
    return json.loads(CERTIFICATION.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def always(_candidate: str, _descendant: str) -> bool:
    return True


# --- the real record: the classes are satisfiable ------------------------------


def test_the_checked_in_publication_record_is_complete(
    verifier: ModuleType, evidence: dict[str, Any], certification: dict[str, Any]
) -> None:
    assert verifier.missing_fields(evidence) == ()
    assert verifier.verify_publication_status(evidence) == ()
    assert verifier.verify_lineage(evidence, certification, always) == ()


def test_the_publication_record_names_the_certified_product(
    evidence: dict[str, Any], certification: dict[str, Any]
) -> None:
    assert (
        evidence["lineage"]["certified_product_sha"]
        == certification["lineage"]["certified_product_sha"]
    )


def test_the_baseline_is_present_and_empty_until_the_merge_creates_it(
    evidence: dict[str, Any],
) -> None:
    # Present, so nobody can claim it was forgotten; null, because the commit
    # that becomes the baseline cannot be named from inside the branch.
    assert evidence["lineage"]["do015_publication_baseline_sha"] is None


# --- one test per failure class ------------------------------------------------


def test_a_wrong_certified_product_sha_is_refused(
    verifier: ModuleType, evidence: dict[str, Any], certification: dict[str, Any]
) -> None:
    evidence["lineage"]["certified_product_sha"] = "0" * 40
    problems = verifier.verify_lineage(evidence, certification, always)
    assert problems and "but Stage 9 certified" in problems[0]


def test_a_stage9_merge_that_is_not_an_ancestor_is_refused(
    verifier: ModuleType, evidence: dict[str, Any], certification: dict[str, Any]
) -> None:
    problems = verifier.verify_lineage(evidence, certification, lambda candidate, _: False)
    # Asserted on the message's own shape: "... is not an ancestor of the Stage 9
    # merge" also contains both words, and a looser assertion passed when the
    # ancestry check was removed entirely.
    merge = evidence["lineage"]["stage9_merge_sha"][:7]
    certified = evidence["lineage"]["certified_product_sha"][:7]
    assert f"Stage 9 merge {merge} is not an ancestor of HEAD" in problems
    assert f"certified product {certified} is not an ancestor of HEAD" in problems


def test_a_certified_product_outside_its_own_certification_is_refused(
    verifier: ModuleType, evidence: dict[str, Any], certification: dict[str, Any]
) -> None:
    merge = evidence["lineage"]["stage9_merge_sha"]
    problems = verifier.verify_lineage(
        evidence, certification, lambda _candidate, descendant: descendant != merge
    )
    certified = evidence["lineage"]["certified_product_sha"][:7]
    assert f"certified product {certified} is not an ancestor of the Stage 9 merge" in " ".join(
        problems
    )


def test_a_base_that_is_an_ancestor_but_not_the_branch_point_is_refused(
    verifier: ModuleType, evidence: dict[str, Any]
) -> None:
    # The failure ancestry alone cannot catch: every commit back to the
    # certification is an ancestor of this branch, so a base naming one of
    # them passes every ancestry check while misstating what was published
    # from where. Only the branch point itself settles it.
    merge = evidence["lineage"]["stage9_merge_sha"]
    base = evidence["lineage"]["stage10_base_sha"]
    problems, notes = verifier.verify_branch_point(merge, base, "f" * 40)
    assert problems and f"stage10_base_sha is {merge[:7]}" in problems[0]
    assert f"cut from {base[:7]}" in problems[0]
    assert notes == ()


def test_the_recorded_base_matching_the_branch_point_passes(
    verifier: ModuleType, evidence: dict[str, Any]
) -> None:
    base = evidence["lineage"]["stage10_base_sha"]
    assert verifier.verify_branch_point(base, base, "f" * 40) == ((), ())


@pytest.mark.parametrize(
    ("point", "head", "expected"),
    [
        (None, "f" * 40, "branch point unknown"),
        ("f" * 40, None, "branch point unknown"),
        ("f" * 40, "f" * 40, "branch point is HEAD"),
    ],
)
def test_an_undeterminable_branch_point_is_a_note_not_a_verdict(
    verifier: ModuleType, point: str | None, head: str | None, expected: str
) -> None:
    # Once this branch merges, origin/main contains it and there is no branch
    # point left to compare. Inventing a verdict there is how a check starts
    # lying; the run says it could not enforce the field instead.
    problems, notes = verifier.verify_branch_point("0" * 40, point, head)
    assert problems == ()
    assert notes and expected in notes[0]


def test_a_base_outside_this_history_is_refused(
    verifier: ModuleType, evidence: dict[str, Any], certification: dict[str, Any]
) -> None:
    base = evidence["lineage"]["stage10_base_sha"]
    problems = verifier.verify_lineage(
        evidence, certification, lambda candidate, _: candidate != base
    )
    assert f"Stage 10 base {base[:7]} is not an ancestor of HEAD" in problems


def test_a_base_that_predates_the_certification_is_refused(
    verifier: ModuleType, evidence: dict[str, Any], certification: dict[str, Any]
) -> None:
    merge = evidence["lineage"]["stage9_merge_sha"]
    base = evidence["lineage"]["stage10_base_sha"]
    problems = verifier.verify_lineage(
        evidence,
        certification,
        lambda candidate, descendant: not (candidate == merge and descendant == base),
    )
    assert any(f"does not contain the Stage 9 merge {merge[:7]}" in item for item in problems)


@pytest.mark.parametrize(
    "path",
    [
        "src/master_all_strings/education/guided_session.py",
        "web/mvp1/app.js",
        "web/mvp1/index.html",
        "resources/education/lessons/half_steps_one_string.json",
        "governance/engine_architecture_v1.json",
    ],
)
def test_a_changed_runtime_path_is_refused(verifier: ModuleType, path: str) -> None:
    assert verifier.protected_product_changes([path]) == (path,)


@pytest.mark.parametrize(
    "path",
    [
        "web/mvp1/tests/guided_session.test.js",
        "docs/mvp2/DO015_PUBLICATION_REPORT.md",
        "scripts/check_in_flight.py",
        "tests/mvp/test_do015_publication.py",
        "AGENTS.md",
    ],
)
def test_repository_hygiene_after_certification_is_allowed(
    verifier: ModuleType, path: str
) -> None:
    # Requiring an empty diff would make publication unusable after any
    # maintenance -- and five hygiene pull requests already stand between the
    # certified product and this base.
    assert verifier.protected_product_changes([path]) == ()


@pytest.mark.parametrize("section", ["lineage", "product_surface", "tags", "known_limitations"])
def test_a_missing_evidence_section_is_refused(
    verifier: ModuleType, evidence: dict[str, Any], section: str
) -> None:
    del evidence[section]
    assert section in verifier.missing_fields(evidence)


@pytest.mark.parametrize(
    "field",
    [
        "certified_product_sha",
        "stage9_merge_sha",
        "stage10_base_sha",
        "do015_publication_baseline_sha",
    ],
)
def test_a_missing_lineage_field_is_refused(
    verifier: ModuleType, evidence: dict[str, Any], field: str
) -> None:
    del evidence["lineage"][field]
    assert field in verifier.missing_fields(evidence)


def test_a_missing_publication_record_is_refused(verifier: ModuleType, tmp_path: Path) -> None:
    payload, problems = verifier.load_publication_evidence(tmp_path / "nothing.json")
    assert payload is None and "does not exist" in problems[0]
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    payload, problems = verifier.load_publication_evidence(broken)
    assert payload is None and "could not be read" in problems[0]


def test_a_premature_published_status_is_refused(
    verifier: ModuleType, evidence: dict[str, Any]
) -> None:
    evidence["status"] = verifier.PUBLISHED_STATUS
    problems = verifier.verify_publication_status(evidence)
    assert problems and "before the merge that would make it true" in problems[0]


@pytest.mark.parametrize("status", ["PUBLISHED", "RELEASED", "", "ready"])
def test_any_other_status_is_refused(
    verifier: ModuleType, evidence: dict[str, Any], status: str
) -> None:
    evidence["status"] = status
    assert verifier.verify_publication_status(evidence) != ()


def test_a_moved_mvp1_tag_is_refused(verifier: ModuleType, evidence: dict[str, Any]) -> None:
    recorded = evidence["tags"]["mvp1"]["sha"]
    problems, verdict = verifier.verify_tag_state(["mvp-1"], ["mvp-1"], recorded, "1" * 40)
    assert problems and "but the record says" in problems[0]
    assert verdict == "PASS"


@pytest.mark.parametrize("tag", ["mvp-2", "mvp-2e", "v2.0.0"])
def test_an_unauthorized_mvp2_tag_stops_the_stage(
    verifier: ModuleType, evidence: dict[str, Any], tag: str
) -> None:
    problems, _ = verifier.verify_tag_state(["mvp-1", tag], [])
    assert problems and "stop and report" in problems[0]
    # Local or remote, either is enough to stop.
    problems, _ = verifier.verify_tag_state(["mvp-1"], [tag])
    assert problems


def test_unreachable_remote_tags_are_neither_pass_nor_fail(
    verifier: ModuleType, evidence: dict[str, Any]
) -> None:
    problems, verdict = verifier.verify_tag_state(["mvp-1"], None)
    assert problems == ()
    assert verdict == "NOT_AVAILABLE"


def test_a_failing_stage9_verifier_fails_publication(verifier: ModuleType) -> None:
    # Delegated, not reimplemented: if Stage 9's own tools stop passing, the
    # publication candidate is not a publication candidate.
    assert verifier.verify_certification_is_still_valid(lambda command: 0) == ()
    problems = verifier.verify_certification_is_still_valid(lambda command: 1)
    assert len(problems) == 2
    assert any("verifier" in item for item in problems)
    assert any("generator" in item for item in problems)


def test_a_failing_generator_alone_fails_publication(verifier: ModuleType) -> None:
    def only_the_generator_fails(command: list[str]) -> int:
        return 1 if "--check" in command else 0

    problems = verifier.verify_certification_is_still_valid(only_the_generator_fails)
    assert len(problems) == 1 and "generator" in problems[0]


# --- the command ---------------------------------------------------------------


def test_the_offline_command_checks_the_record_it_can_see(
    verifier: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert verifier.main(["--offline"]) == 0
    printed = capsys.readouterr().out
    assert "OK   required publication fields" in printed
    assert "OK   publication status" in printed
    assert "offline" in printed


def test_the_command_fails_on_a_record_that_claims_publication(
    verifier: ModuleType,
    evidence: dict[str, Any],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    premature = copy.deepcopy(evidence)
    premature["status"] = verifier.PUBLISHED_STATUS
    path = tmp_path / "DO015_PUBLICATION_EVIDENCE.json"
    path.write_text(json.dumps(premature), encoding="utf-8")
    assert verifier.main(["--offline", "--evidence", str(path)]) == 1
    assert "FAIL publication status" in capsys.readouterr().out


def test_every_line_the_command_prints_is_ascii(
    verifier: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    verifier.main(["--offline"])
    printed = capsys.readouterr().out
    assert printed.encode("ascii", "strict")
