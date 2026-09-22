"""The DO-015 certification verifier has to fail on bad evidence.

A verifier that only passes is decoration. Each case here breaks one property
the certification depends on and proves the verifier notices: a missing
section, a forged lineage, an artifact that is not there, a fixture whose bytes
moved, and -- the one nothing else checks -- a production file that changed
after the commit being certified.
"""

from __future__ import annotations

import hashlib
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
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
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
        "fixtures": {"drift_check": "PASS", "digests": _fixture_digests()},
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


def test_the_checked_in_evidence_passes_the_verifier(tmp_path: Path) -> None:
    # The real record, read the way a reviewer would read it.
    if not verify.EVIDENCE.exists():
        pytest.skip("certification evidence has not been frozen yet")
    assert verify.main([]) == 0
