"""DO-010A / DO-010A-R publication utilities: lineage and tree classification."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_compare_module():
    path = ROOT / "scripts" / "compare_mvp1_release_tree.py"
    spec = importlib.util.spec_from_file_location("compare_mvp1_release_tree", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_classify_governance_source_is_architecture_difference() -> None:
    classify = _load_compare_module().classify
    assert classify("governance/engine_architecture_v1.json") == "ARCHITECTURE_DIFFERENCE"
    assert classify("governance/other_registry.json") == "ARCHITECTURE_DIFFERENCE"


def test_classify_generated_architecture_views_are_generated_only() -> None:
    classify = _load_compare_module().classify
    assert (
        classify("docs/architecture/ENGINE_CONTRACT_OWNERSHIP.md")
        == "GENERATED_GOVERNANCE_ONLY_DIFFERENCE"
    )
    assert (
        classify("docs/architecture/ENGINE_OWNERSHIP_REGISTRY.md")
        == "GENERATED_GOVERNANCE_ONLY_DIFFERENCE"
    )


def test_classify_correctness_patch_allowlist_is_narrow() -> None:
    classify = _load_compare_module().classify
    assert (
        classify("src/master_all_strings/mvp/performance_api.py") == "PRODUCT_CORRECTNESS_PATCH"
    )
    assert classify("src/master_all_strings/mvp/education_api.py") == "PRODUCT_DIFFERENCE"


def test_mvp1_lineage_script_passes() -> None:
    probe = subprocess.run(
        ["git", "cat-file", "-e", "7a9b68455b84b065fcd6b184c0903b292d090ef7^{commit}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        import pytest

        pytest.skip("full git history required for MVP 1 lineage verification")
    result = subprocess.run(
        ["python3", "scripts/verify_mvp1_release_lineage.py", "--release-sha", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MVP 1 lineage: PASS" in result.stdout


def test_no_squash_topology_script_passes() -> None:
    probe = subprocess.run(
        ["git", "cat-file", "-e", "a198c7b30370d077e7213b4ebeab170c769aaaff^{commit}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        import pytest

        pytest.skip("full git history required for squash topology verification")
    result = subprocess.run(
        ["python3", "scripts/verify_no_squash_release_topology.py", "--release-sha", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no-squash release topology: PASS" in result.stdout


def test_compare_tree_classifies_allowed_publication_against_original_product() -> None:
    probe = subprocess.run(
        ["git", "cat-file", "-e", "7a9b68455b84b065fcd6b184c0903b292d090ef7^{commit}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if probe.returncode != 0:
        import pytest

        pytest.skip("full git history required for MVP 1 tree comparison")
    result = subprocess.run(
        ["python3", "scripts/compare_mvp1_release_tree.py", "--candidate", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT: PRODUCT_DIFFERENCE" not in result.stderr
    assert "RESULT: ARCHITECTURE_DIFFERENCE" not in result.stderr
    assert "RESULT:" in result.stdout
    assert "DOCUMENTATION_ONLY_DIFFERENCE:" not in result.stdout
    if "PRODUCT_CORRECTNESS_PATCH:" in result.stdout:
        assert "ALLOWED_PUBLICATION_DIFFERENCE_WITH_CORRECTNESS_PATCHES" in result.stdout
