"""Catalog, resolver, and validation tests (DO-011)."""

from __future__ import annotations

from pathlib import Path

import pytest

from master_all_strings.media.catalog import load_media_catalog
from master_all_strings.media.presentation import lesson_media_payload
from master_all_strings.media.resolver import MediaResolver, compute_file_digest
from master_all_strings.media.validation import MediaValidationError, validate_media_catalog

ROOT = Path(__file__).resolve().parents[2]
MEDIA_ROOT = ROOT / "resources" / "media"


def test_bundled_catalog_loads_and_validates() -> None:
    catalog = load_media_catalog(MEDIA_ROOT)
    validate_media_catalog(catalog, asset_root=MEDIA_ROOT / "examples")
    assert catalog.contains("half-steps-demo-video")
    refs = catalog.list_for_lesson("half_steps_one_string")
    assert [r.media_id for r in refs] == [
        "half-steps-intro-text",
        "half-steps-diagram-image",
        "half-steps-demo-video",
    ]


def test_resolver_rejects_path_escape(tmp_path: Path) -> None:
    asset_root = tmp_path / "examples"
    asset_root.mkdir()
    (asset_root / "ok.txt").write_text("ok", encoding="utf-8")
    resolver = MediaResolver(asset_root=asset_root)
    with pytest.raises(Exception, match="escapes|relative_path"):
        resolver.resolve_path("../ok.txt")


def test_runtime_payload_soft_fails_for_unknown_lesson() -> None:
    payload = lesson_media_payload("no-such-lesson", root=MEDIA_ROOT)
    assert payload["items"] == []
    assert payload["status"] == "ready"


def test_digest_is_deterministic() -> None:
    path = MEDIA_ROOT / "examples" / "half_steps_diagram.png"
    assert compute_file_digest(path) == compute_file_digest(path)
    assert compute_file_digest(path).startswith("sha256:")


def test_required_missing_media_fails_validation(tmp_path: Path) -> None:
    catalog = load_media_catalog(MEDIA_ROOT)
    # Point asset root at empty dir so file media become unavailable.
    empty = tmp_path / "examples"
    empty.mkdir()
    with pytest.raises(MediaValidationError):
        validate_media_catalog(catalog, asset_root=empty)
