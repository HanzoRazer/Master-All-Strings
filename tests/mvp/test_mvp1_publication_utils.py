"""DO-010A publication utilities: lineage and tree classification."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mvp1_lineage_script_passes() -> None:
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
    result = subprocess.run(
        ["python3", "scripts/compare_mvp1_release_tree.py", "--candidate", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PRODUCT_DIFFERENCE" not in result.stderr
    assert "RESULT:" in result.stdout
