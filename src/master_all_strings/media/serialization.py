"""Serialize Lesson Media objects for browser/API consumption."""

from __future__ import annotations

from typing import Any

from master_all_strings.media.contracts import (
    LessonMediaReferenceV1,
    LessonMediaV1,
    MediaCueV1,
    MediaProvenanceV1,
    MediaSourceV1,
)
from master_all_strings.media.resolver import ResolvedMediaV1
from master_all_strings.presentation.contracts import MediaTimelineBindingV1
from master_all_strings.presentation.serialization import to_dict as presentation_to_dict

__all__ = [
    "binding_to_dict",
    "cue_to_dict",
    "media_to_dict",
    "provenance_to_dict",
    "reference_to_dict",
    "resolved_to_dict",
    "source_to_dict",
]


def cue_to_dict(cue: MediaCueV1) -> dict[str, Any]:
    return {
        "cue_id": cue.cue_id,
        "time_seconds": cue.time_seconds,
        "label": cue.label,
        "concept_ref": cue.concept_ref,
        "lesson_time_seconds": cue.lesson_time_seconds,
    }


def binding_to_dict(binding: MediaTimelineBindingV1 | None) -> dict[str, Any] | None:
    """Reuse the presentation encoder so one contract has one wire shape."""

    return presentation_to_dict(binding) if binding is not None else None


def source_to_dict(source: MediaSourceV1) -> dict[str, Any]:
    return {
        "kind": source.kind,
        "relative_path": source.relative_path,
        "mime_type": source.mime_type,
        "text_body": source.text_body,
    }


def provenance_to_dict(provenance: MediaProvenanceV1) -> dict[str, Any]:
    return {
        "source_type": provenance.source_type,
        "source_identifier": provenance.source_identifier,
        "content_digest": provenance.content_digest,
        "creator": provenance.creator,
        "license_status": provenance.license_status,
        "notes": provenance.notes,
    }


def media_to_dict(media: LessonMediaV1) -> dict[str, Any]:
    return {
        "schema_version": media.schema_version,
        "media_id": media.media_id,
        "media_type": media.media_type.value,
        "title": media.title,
        "source": source_to_dict(media.source),
        "duration_seconds": media.duration_seconds,
        "cues": [cue_to_dict(cue) for cue in media.cues],
        "provenance": provenance_to_dict(media.provenance) if media.provenance else None,
    }


def reference_to_dict(ref: LessonMediaReferenceV1) -> dict[str, Any]:
    return {
        "schema_version": ref.schema_version,
        "reference_id": ref.reference_id,
        "lesson_key": ref.lesson_key,
        "media_id": ref.media_id,
        "role": ref.role.value,
        "optional": ref.optional,
        "sort_order": ref.sort_order,
        "timeline_binding": binding_to_dict(ref.timeline_binding),
    }


def resolved_to_dict(item: ResolvedMediaV1) -> dict[str, Any]:
    return {
        "available": item.available,
        "diagnostic": item.diagnostic,
        "public_url": item.public_url,
        "reference_id": item.reference_id,
        "role": item.role,
        "optional": item.optional,
        "media": media_to_dict(item.media),
        "timeline_binding": binding_to_dict(item.timeline_binding),
    }
