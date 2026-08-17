"""Cross-object Lesson Media catalog validation."""

from __future__ import annotations

from pathlib import Path

from master_all_strings.media.catalog import LessonMediaCatalogV1
from master_all_strings.media.contracts import LessonMediaType, MediaContractError
from master_all_strings.media.resolver import MediaResolver, compute_file_digest

__all__ = ["MediaValidationError", "validate_media_catalog"]


class MediaValidationError(MediaContractError):
    """Catalog/build-time media validation failure."""


def validate_media_catalog(
    catalog: LessonMediaCatalogV1,
    *,
    asset_root: Path | None = None,
    require_digests: bool = True,
) -> None:
    resolver = MediaResolver(asset_root=asset_root)
    for media in catalog.media:
        if media.media_type is LessonMediaType.TEXT and media.source.text_body is not None:
            continue
        path = resolver.resolve_path(media.source.relative_path)
        if not path.is_file():
            raise MediaValidationError(
                f"media asset missing for {media.media_id!r}: {media.source.relative_path}"
            )
        if require_digests and media.provenance is not None:
            actual = compute_file_digest(path)
            if actual != media.provenance.content_digest:
                raise MediaValidationError(
                    f"content_digest mismatch for {media.media_id!r}: "
                    f"expected {media.provenance.content_digest}, got {actual}"
                )

    for ref in catalog.references:
        if not catalog.contains(ref.media_id):
            if ref.optional:
                continue
            raise MediaValidationError(
                f"required media reference {ref.reference_id!r} "
                f"points to unknown media_id {ref.media_id!r}"
            )
        resolved = resolver.resolve(catalog.get(ref.media_id))
        if not resolved.available and not ref.optional:
            raise MediaValidationError(
                f"required media reference {ref.reference_id!r} is unavailable: "
                f"{resolved.diagnostic or 'missing asset'}"
            )
