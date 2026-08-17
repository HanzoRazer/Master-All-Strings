"""Safe local media asset resolution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from master_all_strings.media.catalog import LessonMediaCatalogV1, default_media_root
from master_all_strings.media.contracts import (
    MEDIA_SCHEMA_VERSION,
    LessonMediaType,
    LessonMediaV1,
    MediaContractError,
    MediaSourceV1,
)

__all__ = ["MediaResolver", "ResolvedMediaV1", "compute_file_digest"]


def compute_file_digest(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


@dataclass(frozen=True)
class ResolvedMediaV1:
    media: LessonMediaV1
    absolute_path: Path | None
    public_url: str | None
    available: bool
    reference_id: str | None = None
    role: str | None = None
    optional: bool = True
    diagnostic: str | None = None


def _unavailable_text(media_id: str) -> LessonMediaV1:
    return LessonMediaV1(
        schema_version=MEDIA_SCHEMA_VERSION,
        media_id=media_id,
        media_type=LessonMediaType.TEXT,
        title="Unavailable teaching aid",
        source=MediaSourceV1(
            kind="inline",
            relative_path="unavailable.txt",
            mime_type="text/plain",
            text_body="Teaching media unavailable. Practice lesson remains available.",
        ),
        duration_seconds=None,
    )


class MediaResolver:
    """Resolve catalog media into browser-safe local URLs under a fixed asset root."""

    def __init__(
        self, *, asset_root: Path | None = None, url_prefix: str = "/media/assets"
    ) -> None:
        self.asset_root = (asset_root or (default_media_root() / "examples")).resolve()
        self.url_prefix = url_prefix.rstrip("/")

    def resolve_path(self, relative_path: str) -> Path:
        candidate = (self.asset_root / relative_path).resolve()
        try:
            candidate.relative_to(self.asset_root)
        except ValueError as exc:
            raise MediaContractError("media path escapes asset root") from exc
        return candidate

    def resolve(
        self,
        media: LessonMediaV1,
        *,
        reference_id: str | None = None,
        role: str | None = None,
        optional: bool = True,
    ) -> ResolvedMediaV1:
        if media.media_type is LessonMediaType.TEXT and media.source.text_body is not None:
            return ResolvedMediaV1(
                media=media,
                absolute_path=None,
                public_url=None,
                available=True,
                reference_id=reference_id,
                role=role,
                optional=optional,
            )
        try:
            path = self.resolve_path(media.source.relative_path)
        except MediaContractError as exc:
            return ResolvedMediaV1(
                media=media,
                absolute_path=None,
                public_url=None,
                available=False,
                reference_id=reference_id,
                role=role,
                optional=optional,
                diagnostic=str(exc),
            )
        if not path.is_file():
            return ResolvedMediaV1(
                media=media,
                absolute_path=path,
                public_url=None,
                available=False,
                reference_id=reference_id,
                role=role,
                optional=optional,
                diagnostic="Teaching media unavailable",
            )
        return ResolvedMediaV1(
            media=media,
            absolute_path=path,
            public_url=f"{self.url_prefix}/{media.source.relative_path}",
            available=True,
            reference_id=reference_id,
            role=role,
            optional=optional,
        )

    def resolve_for_lesson(
        self, catalog: LessonMediaCatalogV1, lesson_key: str
    ) -> tuple[ResolvedMediaV1, ...]:
        resolved: list[ResolvedMediaV1] = []
        for ref in catalog.list_for_lesson(lesson_key):
            if not catalog.contains(ref.media_id):
                resolved.append(
                    ResolvedMediaV1(
                        media=_unavailable_text(ref.media_id),
                        absolute_path=None,
                        public_url=None,
                        available=False,
                        reference_id=ref.reference_id,
                        role=ref.role.value,
                        optional=ref.optional,
                        diagnostic=(
                            f"Teaching media unavailable: unknown media_id {ref.media_id}"
                        ),
                    )
                )
                continue
            resolved.append(
                self.resolve(
                    catalog.get(ref.media_id),
                    reference_id=ref.reference_id,
                    role=ref.role.value,
                    optional=ref.optional,
                )
            )
        return tuple(resolved)
