"""Versioned Lesson Media contracts (DO-011)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.core.foundation import require_finite, require_non_empty

__all__ = [
    "MEDIA_SCHEMA_VERSION",
    "LessonMediaReferenceV1",
    "LessonMediaRole",
    "LessonMediaType",
    "LessonMediaV1",
    "MediaContractError",
    "MediaCueV1",
    "MediaProvenanceV1",
    "MediaSourceV1",
]

MEDIA_SCHEMA_VERSION = "1.0.0"


class MediaContractError(ValueError):
    """Raised when a Lesson Media contract is constructed with invalid data."""


class LessonMediaType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"


class LessonMediaRole(StrEnum):
    INTRODUCTION = "introduction"
    EXPLANATION = "explanation"
    DEMONSTRATION = "demonstration"
    PRACTICE_HINT = "practice_hint"
    REVIEW = "review"


def _require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise MediaContractError(f"{field_name} must be a non-empty, non-blank string")
    if value != value.strip():
        raise MediaContractError(f"{field_name} must not have leading or trailing whitespace")


def _coerce_enum(enum_cls: type[StrEnum], value: object, field_name: str) -> StrEnum:
    if not isinstance(value, str):
        raise MediaContractError(f"invalid {field_name}: {value!r}")
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise MediaContractError(f"invalid {field_name}: {value!r}") from exc


@dataclass(frozen=True)
class MediaCueV1:
    """Teaching-navigation metadata — never a musical event."""

    cue_id: str
    time_seconds: float
    label: str
    concept_ref: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.cue_id, "cue_id")
        require_finite(self.time_seconds, "time_seconds")
        if self.time_seconds < 0:
            raise MediaContractError("time_seconds must be nonnegative")
        require_non_empty(self.label, "label")
        if self.concept_ref is not None:
            _require_identifier(self.concept_ref, "concept_ref")


@dataclass(frozen=True)
class MediaProvenanceV1:
    source_type: str
    source_identifier: str
    content_digest: str
    creator: str | None = None
    license_status: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.source_type, "source_type")
        require_non_empty(self.source_identifier, "source_identifier")
        require_non_empty(self.content_digest, "content_digest")
        if not self.content_digest.startswith("sha256:"):
            raise MediaContractError("content_digest must use sha256:<hex> form")
        if self.creator is not None:
            require_non_empty(self.creator, "creator")
        if self.license_status is not None:
            require_non_empty(self.license_status, "license_status")
        if self.notes is not None:
            require_non_empty(self.notes, "notes")


@dataclass(frozen=True)
class MediaSourceV1:
    """Logical local asset reference relative to the media asset root."""

    kind: str
    relative_path: str
    mime_type: str
    text_body: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.kind, "kind")
        require_non_empty(self.relative_path, "relative_path")
        require_non_empty(self.mime_type, "mime_type")
        if self.relative_path.startswith("/") or "\\" in self.relative_path:
            raise MediaContractError("relative_path must be a posix-relative path")
        if self.relative_path.startswith("file:"):
            raise MediaContractError("relative_path must not be a file URI")
        parts = self.relative_path.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise MediaContractError("relative_path must not contain empty, '.', or '..' segments")
        if self.text_body is not None and not isinstance(self.text_body, str):
            raise MediaContractError("text_body must be a string when provided")


@dataclass(frozen=True)
class LessonMediaV1:
    schema_version: str
    media_id: str
    media_type: LessonMediaType
    title: str
    source: MediaSourceV1
    duration_seconds: float | None
    cues: tuple[MediaCueV1, ...] = ()
    provenance: MediaProvenanceV1 | None = None

    def __post_init__(self) -> None:
        if self.schema_version != MEDIA_SCHEMA_VERSION:
            raise MediaContractError(
                f"schema_version must be {MEDIA_SCHEMA_VERSION!r}, got {self.schema_version!r}"
            )
        _require_identifier(self.media_id, "media_id")
        object.__setattr__(
            self, "media_type", _coerce_enum(LessonMediaType, self.media_type, "media_type")
        )
        require_non_empty(self.title, "title")
        if not isinstance(self.source, MediaSourceV1):
            raise MediaContractError("source must be MediaSourceV1")
        if self.duration_seconds is not None:
            require_finite(self.duration_seconds, "duration_seconds")
            if self.duration_seconds < 0:
                raise MediaContractError("duration_seconds must be nonnegative")
        if not isinstance(self.cues, tuple):
            raise MediaContractError("cues must be a tuple")
        cue_ids = [cue.cue_id for cue in self.cues]
        if len(cue_ids) != len(set(cue_ids)):
            raise MediaContractError("cues must contain unique cue_id values")
        for cue in self.cues:
            if not isinstance(cue, MediaCueV1):
                raise MediaContractError("cues must contain MediaCueV1 values")
            if self.duration_seconds is not None and cue.time_seconds > self.duration_seconds:
                raise MediaContractError(
                    f"cue {cue.cue_id!r} time_seconds exceeds duration_seconds"
                )
        canonical = tuple(sorted(self.cues, key=lambda c: (c.time_seconds, c.cue_id)))
        object.__setattr__(self, "cues", canonical)
        if self.provenance is not None and not isinstance(self.provenance, MediaProvenanceV1):
            raise MediaContractError("provenance must be MediaProvenanceV1 when provided")


@dataclass(frozen=True)
class LessonMediaReferenceV1:
    """Associates instructional intent with media without owning the lesson."""

    schema_version: str
    reference_id: str
    lesson_key: str
    media_id: str
    role: LessonMediaRole
    optional: bool = True
    sort_order: int = 0

    def __post_init__(self) -> None:
        if self.schema_version != MEDIA_SCHEMA_VERSION:
            raise MediaContractError(
                f"schema_version must be {MEDIA_SCHEMA_VERSION!r}, got {self.schema_version!r}"
            )
        _require_identifier(self.reference_id, "reference_id")
        _require_identifier(self.lesson_key, "lesson_key")
        _require_identifier(self.media_id, "media_id")
        object.__setattr__(self, "role", _coerce_enum(LessonMediaRole, self.role, "role"))
        if not isinstance(self.optional, bool):
            raise MediaContractError("optional must be a boolean")
        if isinstance(self.sort_order, bool) or not isinstance(self.sort_order, int):
            raise MediaContractError("sort_order must be an integer")
