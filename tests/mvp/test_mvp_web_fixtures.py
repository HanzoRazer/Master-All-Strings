"""Drift guard for the checked-in static-UI exports under ``web/mvp1``.

The browser slice ships pre-exported JSON so the static UI runs with no backend.
Those files are golden fixtures, not runtime output: regenerating them must be a
byte-for-byte no-op. If this test fails, run::

    python scripts/run_mvp1.py --lesson ascending_scale --refresh-fixtures

and commit the result together with the change that moved the digests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.demo_library import load_demo_manifest
from master_all_strings.mvp.projection.serialization import (
    deserialize_fretboard_projection,
    validate_projection,
    verify_projection_digest,
)
from master_all_strings.mvp.web_export import export_web_fixtures

WEB_ROOT = Path("web/mvp1")


def _projection_paths() -> list[Path]:
    return [
        WEB_ROOT / "projections" / f"{entry.demo_id}.json"
        for entry in load_demo_manifest()
    ]


def _fixture_paths() -> list[Path]:
    paths = [WEB_ROOT / "demos.json", WEB_ROOT / "instruments.json"]
    paths += _projection_paths()
    paths += [WEB_ROOT / "playback" / f"{entry.demo_id}.json" for entry in load_demo_manifest()]
    paths += [WEB_ROOT / "practice" / f"{entry.demo_id}.json" for entry in load_demo_manifest()]
    return paths


def test_committed_web_fixtures_are_not_stale(app: MvpApplication, tmp_path: Path) -> None:
    export_web_fixtures(app, tmp_path)
    for committed in _fixture_paths():
        regenerated = tmp_path / committed.relative_to(WEB_ROOT)
        assert committed.exists(), f"missing checked-in fixture: {committed}"
        assert regenerated.read_bytes() == committed.read_bytes(), (
            f"{committed} is stale; re-run scripts/run_mvp1.py --refresh-fixtures"
        )


def test_no_untracked_projection_fixtures() -> None:
    """Every exported projection maps to a manifest demo, and vice versa."""

    expected = {f"{entry.demo_id}.json" for entry in load_demo_manifest()}
    actual = {path.name for path in (WEB_ROOT / "projections").glob("*.json")}
    assert actual == expected


def test_runtime_output_path_is_not_committed() -> None:
    """The CLI's default output must not shadow a tracked fixture."""

    assert not (WEB_ROOT / "projection.json").exists()
    assert not (WEB_ROOT / "runtime").exists() or not any(
        (WEB_ROOT / "runtime").glob("*.tmp")
    )


@pytest.mark.parametrize("path", _projection_paths(), ids=lambda p: p.stem)
def test_committed_projections_satisfy_the_delivery_contract(path: Path) -> None:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    projection = deserialize_fretboard_projection(payload["projection"])
    validate_projection(projection)
    verify_projection_digest(projection)
