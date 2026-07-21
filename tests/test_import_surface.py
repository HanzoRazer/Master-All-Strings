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


def _run_import(statement: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = _SRC + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-c", statement],
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.parametrize("module", _PUBLIC_SURFACES)
def test_public_surface_imports_in_isolation(module: str) -> None:
    result = _run_import(f"import {module}")
    assert result.returncode == 0, result.stderr


# A cycle only manifests under one ordering, so importing each surface alone can pass
# while the pairing that originally failed still breaks. These lock both directions.
_ORDERED_PAIRS = [
    (first, second)
    for first in _PUBLIC_SURFACES
    for second in _PUBLIC_SURFACES
    if first != second
]


@pytest.mark.parametrize(("first", "second"), _ORDERED_PAIRS)
def test_public_surfaces_import_in_either_order(first: str, second: str) -> None:
    result = _run_import(f"import {first}; import {second}")
    assert result.returncode == 0, result.stderr


# The legacy module paths are re-export shims after the foundation extraction; these
# symbol-level imports are what downstream callers actually wrote before the change.
_LEGACY_SYMBOL_IMPORTS = [
    "from master_all_strings.core.spatial_mapping.errors import SpatialMappingError",
    "from master_all_strings.core.spatial_mapping.validation import require_midi_note",
    "from master_all_strings.core.spatial_mapping.validation import require_non_empty",
    "from master_all_strings.core.spatial_mapping.enums import FingerboardMode",
    "from master_all_strings.core.spatial_mapping.models import JSONScalar",
    "from master_all_strings.core.spatial_mapping import SpatialMappingError",
]


@pytest.mark.parametrize("statement", _LEGACY_SYMBOL_IMPORTS)
def test_legacy_symbol_import_paths_still_resolve(statement: str) -> None:
    result = _run_import(statement)
    assert result.returncode == 0, result.stderr


def test_error_identity_is_shared_across_all_import_paths() -> None:
    """A shim that rebound the class would silently break ``except`` handlers."""
    result = _run_import(
        "from master_all_strings.core.foundation import SpatialMappingError as A;"
        "from master_all_strings.core.spatial_mapping.errors import SpatialMappingError as B;"
        "from master_all_strings.core.spatial_mapping import SpatialMappingError as C;"
        "assert A is B is C;"
        "assert issubclass(A, ValueError)"
    )
    assert result.returncode == 0, result.stderr
