"""DO-010A publication utilities: lineage and tree classification."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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
        ["python3", "scripts/verify_mvp1_release_lineage.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MVP 1 lineage: PASS" in result.stdout


def test_compare_tree_classifies_docs_only_against_product() -> None:
    probe = subprocess.run(
        ["git", "cat-file", "-e", "7a9b68455b84b065fcd6b184c0903b292d090ef7^{commit}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
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
    assert "RESULT:" in result.stdout
    # Honest classes: tooling/patches must not be collapsed into docs-only.
    assert "DOCUMENTATION_ONLY_DIFFERENCE:" not in result.stdout
    if "PRODUCT_CORRECTNESS_PATCH:" in result.stdout:
        assert "ALLOWED_PUBLICATION_DIFFERENCE_WITH_CORRECTNESS_PATCHES" in result.stdout
    else:
        assert result.stdout.strip().splitlines()[-2].startswith("RESULT: ALLOWED_PUBLICATION") or (
            "RESULT: DOCS_ONLY_DIFFERENCE" in result.stdout
            or "RESULT: IDENTICAL_PRODUCT_TREE" in result.stdout
        )
