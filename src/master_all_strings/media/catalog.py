"""Deterministic local Lesson Media catalog (no network)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

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

__all__ = ["LessonMediaCatalogV1", "default_media_root", "load_media_catalog"]

_REPO_ROOT = Path(__file__).resolve().parents[3]


def default_media_root() -> Path:
    return _REPO_ROOT / "resources" / "media"


@dataclass(frozen=True)
class LessonMediaCatalogV1:
    media: tuple[LessonMediaV1, ...]
    references: tuple[LessonMediaReferenceV1, ...]

    def __post_init__(self) -> None:
        media_ids = [item.media_id for item in self.media]
        if len(media_ids) != len(set(media_ids)):
            raise MediaContractError("catalog media_id values must be unique")
        ref_ids = [item.reference_id for item in self.references]
        if len(ref_ids) != len(set(ref_ids)):
            raise MediaContractError("catalog reference_id values must be unique")

    def get(self, media_id: str) -> LessonMediaV1:
        for item in self.media:
            if item.media_id == media_id:
                return item
        raise KeyError(media_id)

    def contains(self, media_id: str) -> bool:
        return any(item.media_id == media_id for item in self.media)

    def list_for_lesson(self, lesson_key: str) -> tuple[LessonMediaReferenceV1, ...]:
        matched = [ref for ref in self.references if ref.lesson_key == lesson_key]
        return tuple(sorted(matched, key=lambda r: (r.sort_order, r.reference_id)))

    def media_for_lesson(self, lesson_key: str) -> tuple[LessonMediaV1, ...]:
        items: list[LessonMediaV1] = []
        for ref in self.list_for_lesson(lesson_key):
            if self.contains(ref.media_id):
                items.append(self.get(ref.media_id))
        return tuple(items)


def _cue_from_dict(raw: dict[str, object]) -> MediaCueV1:
    return MediaCueV1(
        cue_id=str(raw["cue_id"]),
        time_seconds=float(str(raw["time_seconds"])),
        label=str(raw["label"]),
        concept_ref=str(raw["concept_ref"]) if raw.get("concept_ref") is not None else None,
    )


def _media_from_dict(raw: dict[str, object]) -> LessonMediaV1:
    source_raw = raw["source"]
    assert isinstance(source_raw, dict)
    provenance = None
    if raw.get("provenance") is not None:
        prov = raw["provenance"]
        assert isinstance(prov, dict)
        provenance = MediaProvenanceV1(
            source_type=str(prov["source_type"]),
            source_identifier=str(prov["source_identifier"]),
            content_digest=str(prov["content_digest"]),
            creator=str(prov["creator"]) if prov.get("creator") is not None else None,
            license_status=(
                str(prov["license_status"]) if prov.get("license_status") is not None else None
            ),
            notes=str(prov["notes"]) if prov.get("notes") is not None else None,
        )
    cues_raw = raw.get("cues") or []
    assert isinstance(cues_raw, list)
    duration_raw = raw.get("duration_seconds")
    duration = float(str(duration_raw)) if duration_raw is not None else None
    return LessonMediaV1(
        schema_version=str(raw.get("schema_version", MEDIA_SCHEMA_VERSION)),
        media_id=str(raw["media_id"]),
        media_type=LessonMediaType(str(raw["media_type"])),
        title=str(raw["title"]),
        source=MediaSourceV1(
            kind=str(source_raw["kind"]),
            relative_path=str(source_raw["relative_path"]),
            mime_type=str(source_raw["mime_type"]),
            text_body=(
                str(source_raw["text_body"]) if source_raw.get("text_body") is not None else None
            ),
        ),
        duration_seconds=duration,
        cues=tuple(_cue_from_dict(item) for item in cues_raw if isinstance(item, dict)),
        provenance=provenance,
    )


def _reference_from_dict(raw: dict[str, object]) -> LessonMediaReferenceV1:
    return LessonMediaReferenceV1(
        schema_version=str(raw.get("schema_version", MEDIA_SCHEMA_VERSION)),
        reference_id=str(raw["reference_id"]),
        lesson_key=str(raw["lesson_key"]),
        media_id=str(raw["media_id"]),
        role=LessonMediaRole(str(raw["role"])),
        optional=bool(raw.get("optional", True)),
        sort_order=int(str(raw.get("sort_order", 0))),
    )


def load_media_catalog(root: Path | None = None) -> LessonMediaCatalogV1:
    base = root or default_media_root()
    catalog_path = base / "catalog" / "lesson_media_catalog_v1.json"
    if not catalog_path.is_file():
        raise FileNotFoundError(f"media catalog missing: {catalog_path}")
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    media_raw = raw.get("media") or []
    refs_raw = raw.get("references") or []
    if not isinstance(media_raw, list) or not isinstance(refs_raw, list):
        raise MediaContractError("catalog media/references must be lists")
    return LessonMediaCatalogV1(
        media=tuple(_media_from_dict(item) for item in media_raw),
        references=tuple(_reference_from_dict(item) for item in refs_raw),
    )
