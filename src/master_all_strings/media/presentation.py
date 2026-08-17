"""Assemble browser-facing lesson media presentation metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from master_all_strings.media.catalog import (
    LessonMediaCatalogV1,
    default_media_root,
    load_media_catalog,
)
from master_all_strings.media.resolver import MediaResolver
from master_all_strings.media.serialization import resolved_to_dict
from master_all_strings.media.validation import validate_media_catalog

__all__ = ["lesson_media_payload", "load_validated_catalog"]


def load_validated_catalog(root: Path | None = None) -> LessonMediaCatalogV1:
    base = root or default_media_root()
    catalog = load_media_catalog(base)
    validate_media_catalog(catalog, asset_root=base / "examples")
    return catalog


def lesson_media_payload(
    lesson_key: str,
    *,
    catalog: LessonMediaCatalogV1 | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Return soft-fail presentation payload for a lesson key.

    Catalog build validation is separate. This runtime helper never raises for
    missing optional/required assets; it reports diagnostics instead.
    """

    base = root or default_media_root()
    cat = catalog or load_media_catalog(base)
    resolver = MediaResolver(asset_root=base / "examples")
    items = resolver.resolve_for_lesson(cat, lesson_key)
    available = [resolved_to_dict(item) for item in items if item.available]
    unavailable = [resolved_to_dict(item) for item in items if not item.available]
    return {
        "schema_version": "1.0.0",
        "lesson_key": lesson_key,
        "items": [resolved_to_dict(item) for item in items],
        "available_count": len(available),
        "unavailable_count": len(unavailable),
        "status": "ready" if not unavailable else "degraded",
        "message": None
        if not unavailable
        else "Teaching media unavailable. Practice lesson remains available.",
    }
