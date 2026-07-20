"""Regression guard: public package surfaces import cleanly in any order.

Each import runs in a FRESH interpreter (subprocess) so import order is not masked
by ``sys.modules`` caching from other tests. Importing
``master_all_strings.instruments`` before ``core.spatial_mapping`` previously raised
a circular ``ImportError``; this test locks the fix in place.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_SRC = str(Path(__file__).resolve().parents[1] / "src")

_PUBLIC_SURFACES = [
    "master_all_strings.instruments",
    "master_all_strings.core.spatial_mapping",
    "master_all_strings.core.musical_events",
    "master_all_strings.core.foundation",
]


@pytest.mark.parametrize("module", _PUBLIC_SURFACES)
def test_public_surface_imports_in_isolation(module: str) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = _SRC + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
