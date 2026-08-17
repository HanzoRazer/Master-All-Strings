"""Lesson Media presentation-support subsystem (DO-011 / MVP 2A).

Media explains; it does not own curriculum, musical timing, Zone semantics,
Performance evidence, or Educational evaluation.
"""

from __future__ import annotations

from master_all_strings.media.catalog import LessonMediaCatalogV1, load_media_catalog
from master_all_strings.media.contracts import (
    MEDIA_SCHEMA_VERSION,
    LessonMediaReferenceV1,
    LessonMediaRole,
    LessonMediaType,
    LessonMediaV1,
    MediaCueV1,
    MediaProvenanceV1,
    MediaSourceV1,
)
from master_all_strings.media.resolver import MediaResolver, ResolvedMediaV1
from master_all_strings.media.validation import MediaValidationError, validate_media_catalog

__all__ = [
    "MEDIA_SCHEMA_VERSION",
    "LessonMediaCatalogV1",
    "LessonMediaReferenceV1",
    "LessonMediaRole",
    "LessonMediaType",
    "LessonMediaV1",
    "MediaCueV1",
    "MediaProvenanceV1",
    "MediaResolver",
    "MediaSourceV1",
    "MediaValidationError",
    "ResolvedMediaV1",
    "load_media_catalog",
    "validate_media_catalog",
]
