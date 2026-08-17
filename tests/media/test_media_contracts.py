"""Lesson Media contract tests (DO-011)."""

from __future__ import annotations

import pytest

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


def _source(**kwargs: object) -> MediaSourceV1:
    base = {
        "kind": "file",
        "relative_path": "demo.mp4",
        "mime_type": "video/mp4",
        "text_body": None,
    }
    base.update(kwargs)
    return MediaSourceV1(**base)  # type: ignore[arg-type]


def test_cues_are_canonicalized_by_time_then_id() -> None:
    media = LessonMediaV1(
        schema_version=MEDIA_SCHEMA_VERSION,
        media_id="m1",
        media_type=LessonMediaType.VIDEO,
        title="Demo",
        source=_source(),
        duration_seconds=10.0,
        cues=(
            MediaCueV1("b", 2.0, "Second"),
            MediaCueV1("a", 1.0, "First"),
            MediaCueV1("c", 1.0, "Also first-ish"),
        ),
    )
    assert [c.cue_id for c in media.cues] == ["a", "c", "b"]


def test_rejects_unsupported_media_type_and_empty_ids() -> None:
    with pytest.raises(MediaContractError):
        LessonMediaV1(
            schema_version=MEDIA_SCHEMA_VERSION,
            media_id="m1",
            media_type="audio",  # type: ignore[arg-type]
            title="x",
            source=_source(),
            duration_seconds=1.0,
        )
    with pytest.raises(MediaContractError):
        LessonMediaV1(
            schema_version=MEDIA_SCHEMA_VERSION,
            media_id=" ",
            media_type=LessonMediaType.TEXT,
            title="x",
            source=_source(
                kind="inline",
                relative_path="a.txt",
                mime_type="text/plain",
                text_body="hi",
            ),
            duration_seconds=None,
        )


def test_rejects_cue_beyond_duration_and_duplicate_cue_ids() -> None:
    with pytest.raises(MediaContractError, match="exceeds"):
        LessonMediaV1(
            schema_version=MEDIA_SCHEMA_VERSION,
            media_id="m1",
            media_type=LessonMediaType.VIDEO,
            title="Demo",
            source=_source(),
            duration_seconds=1.0,
            cues=(MediaCueV1("a", 2.0, "Late"),),
        )
    with pytest.raises(MediaContractError, match="unique"):
        LessonMediaV1(
            schema_version=MEDIA_SCHEMA_VERSION,
            media_id="m1",
            media_type=LessonMediaType.VIDEO,
            title="Demo",
            source=_source(),
            duration_seconds=5.0,
            cues=(MediaCueV1("a", 1.0, "One"), MediaCueV1("a", 2.0, "Two")),
        )


def test_rejects_path_traversal_in_source() -> None:
    with pytest.raises(MediaContractError):
        _source(relative_path="../secret.mp4")
    with pytest.raises(MediaContractError):
        _source(relative_path="/abs.mp4")


def test_reference_and_provenance_contracts() -> None:
    ref = LessonMediaReferenceV1(
        schema_version=MEDIA_SCHEMA_VERSION,
        reference_id="r1",
        lesson_key="half_steps_one_string",
        media_id="half-steps-demo-video",
        role=LessonMediaRole.DEMONSTRATION,
        optional=True,
        sort_order=2,
    )
    assert ref.role is LessonMediaRole.DEMONSTRATION
    with pytest.raises(MediaContractError):
        MediaProvenanceV1("bundled", "x", "md5:abc")
