"""The committed Markdown views must exactly match what the registry renders.

This is the bidirectional authority rule: a view edited to disagree with the JSON
fails here, and a JSON change not reflected in the committed views fails here too.
"""

from __future__ import annotations

from typing import Any

import pytest

from master_all_strings.governance import engine_boundaries as eb


@pytest.fixture
def registry() -> dict[str, Any]:
    return eb.load_registry()


def test_committed_views_match_the_registry(registry: dict[str, Any]) -> None:
    assert eb.check_views(registry) == []


@pytest.mark.parametrize("filename", list(eb.VIEWS))
def test_each_view_exists_and_is_generated(filename: str, registry: dict[str, Any]) -> None:
    path = eb.VIEW_DIR / filename
    assert path.exists(), filename
    assert path.read_text(encoding="utf-8").startswith("<!-- GENERATED")


def test_a_hand_edited_view_is_detected(tmp_path: Any, registry: dict[str, Any]) -> None:
    eb.write_views(registry, tmp_path)
    target = tmp_path / "ENGINE_DEPENDENCY_MATRIX.md"
    edited = target.read_text(encoding="utf-8") + "\n<!-- sneaky edit -->\n"
    target.write_text(edited, encoding="utf-8")
    codes = {v.code for v in eb.check_views(registry, tmp_path)}
    assert "VIEW_STALE" in codes


def test_a_missing_view_is_detected(tmp_path: Any, registry: dict[str, Any]) -> None:
    codes = {v.code for v in eb.check_views(registry, tmp_path)}
    assert "VIEW_MISSING" in codes


def test_a_registry_change_not_regenerated_is_detected(
    tmp_path: Any, registry: dict[str, Any]
) -> None:
    eb.write_views(registry, tmp_path)
    # Change the registry without regenerating the on-disk views.
    registry["capabilities"][0]["name"] = "Renamed capability"
    codes = {v.code for v in eb.check_views(registry, tmp_path)}
    assert "VIEW_STALE" in codes


def test_write_then_check_roundtrips(tmp_path: Any, registry: dict[str, Any]) -> None:
    eb.write_views(registry, tmp_path)
    assert eb.check_views(registry, tmp_path) == []
