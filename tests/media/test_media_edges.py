"""Additional Lesson Media coverage for DO-011 edge paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from master_all_strings.core.foundation import SpatialMappingError
from master_all_strings.media.catalog import LessonMediaCatalogV1, load_media_catalog
from master_all_strings.media.contracts import (
    MEDIA_SCHEMA_VERSION,
    LessonMediaReferenceV1,
    LessonMediaRole,
    LessonMediaType,
    LessonMediaV1,
    MediaContractError,
    MediaCueV1,
    MediaProvenanceV1,
    MediaSourceV1,
)
from master_all_strings.media.presentation import load_validated_catalog
from master_all_strings.media.resolver import MediaResolver
from master_all_strings.media.serialization import reference_to_dict
from master_all_strings.media.validation import MediaValidationError, validate_media_catalog

ROOT = Path(__file__).resolve().parents[2]
MEDIA_ROOT = ROOT / "resources" / "media"


def _text(media_id: str = "t1") -> LessonMediaV1:
    return LessonMediaV1(
        schema_version=MEDIA_SCHEMA_VERSION,
        media_id=media_id,
        media_type=LessonMediaType.TEXT,
        title="Text",
        source=MediaSourceV1(
            kind="inline",
            relative_path="x.txt",
            mime_type="text/plain",
            text_body="hello",
        ),
        duration_seconds=None,
    )


def test_catalog_rejects_duplicate_ids_and_get_miss() -> None:
    media = _text()
    with pytest.raises(MediaContractError):
        LessonMediaCatalogV1(media=(media, media), references=())
    ref = LessonMediaReferenceV1(
        schema_version=MEDIA_SCHEMA_VERSION,
        reference_id="r1",
        lesson_key="lesson",
        media_id="t1",
        role=LessonMediaRole.INTRODUCTION,
    )
    with pytest.raises(MediaContractError):
        LessonMediaCatalogV1(media=(media,), references=(ref, ref))
    catalog = LessonMediaCatalogV1(media=(media,), references=(ref,))
    assert catalog.get("t1").media_id == "t1"
    with pytest.raises(KeyError):
        catalog.get("missing")
    assert catalog.media_for_lesson("lesson")[0].media_id == "t1"
    assert reference_to_dict(ref)["lesson_key"] == "lesson"


def test_contract_edge_rejects() -> None:
    with pytest.raises(MediaContractError):
        MediaCueV1("c", -1.0, "bad")
    with pytest.raises((MediaContractError, SpatialMappingError)):
        MediaProvenanceV1("bundled", "id", "sha256:dead", creator="")
    with pytest.raises(MediaContractError):
        MediaSourceV1("file", "file:bad.mp4", "video/mp4")
    with pytest.raises(MediaContractError):
        LessonMediaV1(
            schema_version="9.9.9",
            media_id="m",
            media_type=LessonMediaType.TEXT,
            title="t",
            source=MediaSourceV1("inline", "a.txt", "text/plain", "x"),
            duration_seconds=None,
        )
    with pytest.raises(MediaContractError):
        LessonMediaReferenceV1(
            schema_version=MEDIA_SCHEMA_VERSION,
            reference_id="r",
            lesson_key="l",
            media_id="m",
            role=LessonMediaRole.REVIEW,
            optional="yes",  # type: ignore[arg-type]
        )


def test_resolver_marks_missing_and_unknown_reference(tmp_path: Path) -> None:
    asset_root = tmp_path / "examples"
    asset_root.mkdir()
    media = LessonMediaV1(
        schema_version=MEDIA_SCHEMA_VERSION,
        media_id="file-missing",
        media_type=LessonMediaType.IMAGE,
        title="Missing",
        source=MediaSourceV1("file", "gone.png", "image/png"),
        duration_seconds=None,
    )
    ref_ok = LessonMediaReferenceV1(
        schema_version=MEDIA_SCHEMA_VERSION,
        reference_id="r-ok",
        lesson_key="lesson",
        media_id="file-missing",
        role=LessonMediaRole.EXPLANATION,
        optional=True,
    )
    ref_unknown = LessonMediaReferenceV1(
        schema_version=MEDIA_SCHEMA_VERSION,
        reference_id="r-unknown",
        lesson_key="lesson",
        media_id="nope",
        role=LessonMediaRole.EXPLANATION,
        optional=True,
    )
    catalog = LessonMediaCatalogV1(media=(media,), references=(ref_ok, ref_unknown))
    resolver = MediaResolver(asset_root=asset_root)
    resolved = resolver.resolve_for_lesson(catalog, "lesson")
    assert len(resolved) == 2
    assert all(not item.available for item in resolved)


def test_validation_digest_mismatch(tmp_path: Path) -> None:
    asset_root = tmp_path / "examples"
    asset_root.mkdir()
    path = asset_root / "diagram.png"
    path.write_bytes(b"abc")
    media = LessonMediaV1(
        schema_version=MEDIA_SCHEMA_VERSION,
        media_id="img",
        media_type=LessonMediaType.IMAGE,
        title="Img",
        source=MediaSourceV1("file", "diagram.png", "image/png"),
        duration_seconds=None,
        provenance=MediaProvenanceV1(
            "bundled",
            "diagram.png",
            "sha256:" + ("0" * 64),
        ),
    )
    catalog = LessonMediaCatalogV1(media=(media,), references=())
    with pytest.raises(MediaValidationError, match="content_digest"):
        validate_media_catalog(catalog, asset_root=asset_root)


def test_load_validated_catalog_and_missing_catalog(tmp_path: Path) -> None:
    catalog = load_validated_catalog(MEDIA_ROOT)
    assert catalog.contains("half-steps-intro-text")
    with pytest.raises(FileNotFoundError):
        load_media_catalog(tmp_path)


def test_required_unknown_reference_fails_validation() -> None:
    media = _text()
    ref = LessonMediaReferenceV1(
        schema_version=MEDIA_SCHEMA_VERSION,
        reference_id="r-req",
        lesson_key="lesson",
        media_id="missing",
        role=LessonMediaRole.INTRODUCTION,
        optional=False,
    )
    catalog = LessonMediaCatalogV1(media=(media,), references=(ref,))
    with pytest.raises(MediaValidationError, match="required media reference"):
        validate_media_catalog(catalog, asset_root=MEDIA_ROOT / "examples")


def test_malformed_catalog_json(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    (catalog_dir / "lesson_media_catalog_v1.json").write_text(
        json.dumps({"media": "bad", "references": []}),
        encoding="utf-8",
    )
    with pytest.raises(MediaContractError):
        load_media_catalog(tmp_path)
