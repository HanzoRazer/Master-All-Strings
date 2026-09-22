"""The DO-015 certification verifier has to fail on bad evidence.

A verifier that only passes is decoration. Each case here breaks one property
the certification depends on and proves the verifier notices: a missing
section, a forged lineage, an artifact that is not there, a fixture whose bytes
moved, and -- the one nothing else checks -- a production file that changed
after the commit being certified.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "resources" / "education" / "examples" / "guided_sessions"


def _verifier() -> ModuleType:
    """Load by path; ``scripts/`` is not a package, and the module is put into
    ``sys.modules`` first so its annotations resolve."""

    spec = importlib.util.spec_from_file_location(
        "verify_do015_certification", REPO_ROOT / "scripts" / "verify_do015_certification.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify = _verifier()


def _fixture_digests() -> dict[str, str]:
    return {
        path.name: verify.content_digest(path)
        for path in sorted(FIXTURE_DIR.glob("*.json"))
    }


def valid_evidence() -> dict[str, Any]:
    """The smallest record that should pass every check."""

    evidence: dict[str, Any] = {
        "lineage": {
            "repository": "HanzoRazer/Master-All-Strings",
            "stage7_merge_sha": verify.STAGE7_MERGE_SHA,
            "stage8_product_sha": "a29afb5e6972c5dfbf2266dee7a0ec47597c1d98",
            "stage8_merge_sha": "3fcf618b655c3f51b020d11a0bb3f96571da08d7",
            "stage9_base_sha": "3fcf618b655c3f51b020d11a0bb3f96571da08d7",
            "certified_product_sha": "3fcf618b655c3f51b020d11a0bb3f96571da08d7",
        },
        "artifacts": ["docs/mvp2/DO015_CERTIFICATION_REPORT.md"],
        "fixtures": {
            "drift_check": "PASS",
            "digest_method": "sha256 of the file with CRLF normalised to LF",
            "digests": _fixture_digests(),
        },
        "browser_reproducible": {"status": "PASS"},
        "browser_visual": {"status": "NOT_AVAILABLE", "reason": "no connected browser"},
        "stage8_adversarial": {"suites": ["web/mvp1/tests/guided_authority_adversarial.test.js"]},
    }
    for section in verify.REQUIRED_SECTIONS:
        evidence.setdefault(section, {"recorded": True})
    return evidence


def staged_root(tmp_path: Path) -> Path:
    """A root holding exactly what a frozen certification would hold.

    Hermetic on purpose: these cases must not depend on whether the real
    report and evidence have been written yet, since the verifier lands before
    the evidence it verifies.
    """

    fixtures = tmp_path / "resources" / "education" / "examples" / "guided_sessions"
    fixtures.mkdir(parents=True)
    for path in FIXTURE_DIR.glob("*.json"):
        (fixtures / path.name).write_bytes(path.read_bytes())
    report = tmp_path / "docs" / "mvp2" / "DO015_CERTIFICATION_REPORT.md"
    report.parent.mkdir(parents=True)
    report.write_text("# certification report\n", encoding="utf-8")
    return tmp_path


def problems_for(
    evidence: dict[str, Any],
    root: Path,
    changed: list[str] | None = None,
) -> list[str]:
    """Every problem the pure checks find, ignoring the git-backed ones."""

    found: list[str] = []
    found += verify.check_required_sections(evidence)
    found += verify.check_lineage(evidence)
    found += verify.check_artifacts(evidence, root)
    found += verify.check_fixture_digests(evidence, root)
    found += verify.check_witnesses(evidence)
    if changed is not None:
        found += verify.check_production_diff(changed)
    return found


def test_a_complete_record_passes(tmp_path: Path) -> None:
    assert problems_for(valid_evidence(), staged_root(tmp_path), changed=[]) == []


@pytest.mark.parametrize("section", sorted(verify.REQUIRED_SECTIONS))
def test_a_missing_section_fails(section: str, tmp_path: Path) -> None:
    root = staged_root(tmp_path)
    evidence = valid_evidence()
    del evidence[section]
    assert any(section in problem for problem in problems_for(evidence, root))


def test_an_empty_section_is_not_a_record(tmp_path: Path) -> None:
    root = staged_root(tmp_path)
    evidence = valid_evidence()
    evidence["known_limitations"] = {}
    assert any("empty" in problem for problem in problems_for(evidence, root))


@pytest.mark.parametrize("key", sorted(set(verify.REQUIRED_LINEAGE) - {"repository"}))
def test_a_lineage_sha_must_be_a_sha(key: str, tmp_path: Path) -> None:
    root = staged_root(tmp_path)
    evidence = valid_evidence()
    evidence["lineage"][key] = "HEAD~1"
    assert any("not a full 40-character sha" in problem for problem in problems_for(evidence, root))


def test_a_forged_predecessor_fails(tmp_path: Path) -> None:
    root = staged_root(tmp_path)
    evidence = valid_evidence()
    evidence["lineage"]["stage7_merge_sha"] = "0" * 40
    assert any("stage7_merge_sha must be" in problem for problem in problems_for(evidence, root))


def test_certifying_past_the_base_needs_saying_why(tmp_path: Path) -> None:
    root = staged_root(tmp_path)
    evidence = valid_evidence()
    evidence["lineage"]["certified_product_sha"] = "b" * 40
    found = problems_for(evidence, root)
    assert any("certified_beyond_base_reason" in problem for problem in found)
    evidence["lineage"]["certified_beyond_base_reason"] = "covers an unrelated docs merge"
    found = problems_for(evidence, root)
    assert not any("certified_beyond_base_reason" in problem for problem in found)


def test_a_missing_artifact_fails(tmp_path: Path) -> None:
    root = staged_root(tmp_path)
    evidence = valid_evidence()
    evidence["artifacts"] = ["docs/mvp2/do015_artifacts/not_captured.png"]
    assert any("artifact is missing" in problem for problem in problems_for(evidence, root))


def test_evidence_must_list_its_artifacts(tmp_path: Path) -> None:
    root = staged_root(tmp_path)
    evidence = valid_evidence()
    evidence["artifacts"] = []
    assert any("must list its artifacts" in problem for problem in problems_for(evidence, root))


def test_a_fixture_whose_bytes_moved_fails(tmp_path: Path) -> None:
    root = staged_root(tmp_path)
    evidence = valid_evidence()
    name = next(iter(evidence["fixtures"]["digests"]))
    evidence["fixtures"]["digests"][name] = "0" * 64
    assert any("changed since certification" in problem for problem in problems_for(evidence, root))


def test_an_unrecorded_fixture_fails(tmp_path: Path) -> None:
    root = staged_root(tmp_path)
    evidence = valid_evidence()
    name = next(iter(evidence["fixtures"]["digests"]))
    del evidence["fixtures"]["digests"][name]
    found = problems_for(evidence, root)
    assert any("not recorded in the evidence" in problem for problem in found)


@pytest.mark.parametrize(
    "path",
    [
        "src/master_all_strings/education/guided_session.py",
        "web/mvp1/app.js",
        "resources/education/examples/guided_sessions/repeat_accepted.json",
        "governance/engine_architecture_v1.json",
        ".github/workflows/verify.yml",
        "pyproject.toml",
        "scripts/build_guided_session_fixtures.py",
    ],
)
def test_a_product_file_changed_after_the_certified_sha_fails(path: str) -> None:
    # The property nothing else can check: certification that carried a product
    # change would be certifying a commit that never existed as a product.
    assert verify.check_production_diff([path]) != []


@pytest.mark.parametrize(
    "path",
    [
        "docs/mvp2/DO015_INTEGRATION_EVIDENCE.json",
        "docs/mvp2/do015_artifacts/browser_smoke_summary.json",
        "docs/development/IN_FLIGHT.md",
        "tests/mvp/test_do015_certification.py",
        "web/mvp1/tests/guided_authority_adversarial.test.js",
        "scripts/verify_do015_certification.py",
        "scripts/build_do015_certification_evidence.py",
    ],
)
def test_an_evidence_only_diff_passes(path: str) -> None:
    assert verify.check_production_diff([path]) == []


def test_the_reproducible_witness_is_mandatory(tmp_path: Path) -> None:
    root = staged_root(tmp_path)
    evidence = valid_evidence()
    evidence["browser_reproducible"] = {"status": "NOT_AVAILABLE", "reason": "no harness"}
    assert any("mandatory witness" in problem for problem in problems_for(evidence, root))


def test_the_visual_witness_may_be_absent_but_must_say_why(tmp_path: Path) -> None:
    root = staged_root(tmp_path)
    evidence = valid_evidence()
    evidence["browser_visual"] = {"status": "NOT_AVAILABLE"}
    assert any("without a reason" in problem for problem in problems_for(evidence, root))
    evidence["browser_visual"] = {"status": "PASS"}
    assert not any("browser_visual" in problem for problem in problems_for(evidence, root))


def test_an_invented_witness_status_fails(tmp_path: Path) -> None:
    root = staged_root(tmp_path)
    evidence = valid_evidence()
    evidence["browser_visual"] = {"status": "PROBABLY_FINE"}
    found = problems_for(evidence, root)
    assert any("must be PASS or NOT_AVAILABLE" in problem for problem in found)


def test_stage8_must_be_referenced_not_assumed(tmp_path: Path) -> None:
    root = staged_root(tmp_path)
    evidence = valid_evidence()
    evidence["stage8_adversarial"] = {"result": "PASS"}
    found = problems_for(evidence, root)
    assert any("must reference the Stage 8 suites" in problem for problem in found)


def test_missing_evidence_file_is_reported_not_raised(tmp_path: Path) -> None:
    loaded, problems = verify.load_evidence(tmp_path / "nothing.json")
    assert loaded is None
    assert any("missing" in problem for problem in problems)


def test_unparseable_evidence_is_reported_not_raised(tmp_path: Path) -> None:
    broken = tmp_path / "evidence.json"
    broken.write_text("{ not json", encoding="utf-8")
    loaded, problems = verify.load_evidence(broken)
    assert loaded is None
    assert any("not valid JSON" in problem for problem in problems)


def test_findings_print_on_a_console_that_is_not_utf8() -> None:
    rendered = verify._ascii("FAIL  fixture — changed → badly")
    rendered.encode("cp437")
    rendered.encode("ascii")


def test_the_checked_in_evidence_passes_every_check_ci_can_make() -> None:
    """The real record, read the way a reviewer would read it -- minus one.

    The CI-record check is left to the CLI. A run id for a commit does not
    exist until that commit has run, so asserting it here would make every
    content commit red until a later commit sealed it, and sealing changes the
    content again. The seal is verified by
    ``python scripts/verify_do015_certification.py``, which the report tells a
    reviewer to run and which checks all eight.
    """

    if not verify.EVIDENCE.exists():
        pytest.skip("certification evidence has not been frozen yet")
    evidence, problems = verify.load_evidence(verify.EVIDENCE)
    assert evidence is not None and problems == []
    head = verify._git(["rev-parse", "HEAD"])
    certified = str(evidence["lineage"]["certified_product_sha"])
    changed = verify.changed_paths(certified, head) if head else None
    found = [
        (label, items)
        for label, items in verify.run_checks(
            evidence, verify.REPO_ROOT, changed, head, include_ci=False
        )
        if items
    ]
    assert found == []


def test_the_ci_record_is_present_and_well_formed() -> None:
    """Shape, not the seal. See above for why the seal is the CLI's job."""

    if not verify.EVIDENCE.exists():
        pytest.skip("certification evidence has not been frozen yet")
    evidence, _ = verify.load_evidence(verify.EVIDENCE)
    assert evidence is not None
    ci = evidence["linux_ci"]
    assert verify._SHA.match(str(ci["certified_content_sha"]))
    assert str(ci["semantics"]).strip()
    assert ci["conclusion"] == "success"
    # No placeholder. Leaving the seal at zero would let an unsealed record
    # sit in the repository looking finished, which is the loophole the split
    # between this suite and the CLI could otherwise open.
    assert isinstance(ci["run_id"], int) and ci["run_id"] > 0


def _ci_record(**overrides: object) -> dict[str, Any]:
    record = {
        "workflow": ".github/workflows/verify.yml",
        "certified_content_sha": "c" * 40,
        "run_id": 123456,
        "conclusion": "success",
        "semantics": "the green run for the last commit that changed content",
    }
    record.update(overrides)
    return {"linux_ci": record}


def test_a_complete_ci_record_passes() -> None:
    assert verify.check_ci_record(_ci_record(), []) == []


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("certified_content_sha", "HEAD", "not a full sha"),
        ("run_id", 0, "id of a real run"),
        ("run_id", "35678827161", "id of a real run"),
        ("conclusion", "failure", "must be success"),
        ("semantics", "", "must say what the named run covers"),
    ],
)
def test_a_broken_ci_record_is_refused(field: str, value: object, expected: str) -> None:
    problems = verify.check_ci_record(_ci_record(**{field: value}), [])
    assert any(expected in problem for problem in problems), problems


def test_product_work_after_the_named_run_is_refused() -> None:
    # The claim the record makes is that everything after the named run is the
    # paperwork of recording it. A test or a script is not paperwork.
    for path in [
        "src/master_all_strings/education/guided_session.py",
        "tests/mvp2/test_do015_certification_scenarios.py",
        "scripts/verify_do015_certification.py",
        "web/mvp1/app.js",
    ]:
        problems = verify.check_ci_record(_ci_record(), [path])
        assert any("not evidence or register metadata" in item for item in problems), path


def test_evidence_metadata_after_the_named_run_is_fine() -> None:
    allowed = [
        "docs/mvp2/DO015_INTEGRATION_EVIDENCE.json",
        "docs/mvp2/DO015_CERTIFICATION_REPORT.md",
        "docs/mvp2/DO015_TRANCHE_PLAN.md",
        "docs/development/IN_FLIGHT.md",
    ]
    assert verify.check_ci_record(_ci_record(), allowed) == []


def test_an_ungatherable_diff_is_skipped_not_invented() -> None:
    assert verify.check_ci_record(_ci_record(), None) == []


def _real_run(**overrides: object) -> dict[str, Any]:
    run = {
        "databaseId": 123456,
        "headSha": "c" * 40,
        "conclusion": "success",
        "status": "completed",
        "workflowName": "verify",
    }
    run.update(overrides)
    return run


def test_a_run_that_matches_the_seal_passes() -> None:
    assert verify.check_ci_run_is_real(_ci_record(), _real_run()) == []


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("databaseId", 999, "and got 999"),
        ("status", "in_progress", "has not finished"),
        ("conclusion", "failure", "not success"),
        ("conclusion", None, "not success"),
        ("headSha", "d" * 40, "but the record seals"),
        ("workflowName", "codeql", "not verify"),
    ],
)
def test_a_run_that_does_not_match_the_seal_is_refused(
    field: str, value: object, expected: str
) -> None:
    # The seal is only evidence if it can be wrong. A record can claim any run
    # id and any conclusion; this is what makes the claim checkable.
    problems = verify.check_ci_run_is_real(_ci_record(), _real_run(**{field: value}))
    assert any(expected in problem for problem in problems), problems


def test_a_run_for_another_commit_is_the_loophole_this_closes() -> None:
    # Sealing a green run from some earlier commit would otherwise let a red
    # head wear a green badge.
    problems = verify.check_ci_run_is_real(
        _ci_record(certified_content_sha="a" * 40), _real_run(headSha="b" * 40)
    )
    assert any("but the record seals" in problem for problem in problems)


def test_github_being_unreachable_is_skipped_not_assumed() -> None:
    problems = verify.check_ci_run_is_real(_ci_record(), None)
    assert problems == ["SKIPPED: GitHub could not be asked about the run"]
