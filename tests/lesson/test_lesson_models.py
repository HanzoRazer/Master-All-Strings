"""Model construction and identity invariants for LessonAssignmentV1."""

from __future__ import annotations

import pytest

from master_all_strings.lesson.enums import LessonContentFormat, LessonSourceType
from master_all_strings.lesson.errors import LessonSchemaError, LessonValidationError
from master_all_strings.lesson.models import (
    LESSON_ASSIGNMENT_SCHEMA_ID,
    LESSON_ASSIGNMENT_SCHEMA_VERSION,
    LessonAssignmentV1,
    LessonIdentityV1,
    LessonMusicalContentV1,
    LessonPlaybackPolicyV1,
    LessonProvenanceV1,
    LessonSpatialGuidanceV1,
    SerializedCanonicalEventV1,
)


def _base(**identity_kwargs: object) -> LessonAssignmentV1:
    identity = {
        "assignment_id": "a1",
        "content_id": "c1",
        "title": "T",
        **identity_kwargs,
    }
    return LessonAssignmentV1(
        schema_id=LESSON_ASSIGNMENT_SCHEMA_ID,
        schema_version=LESSON_ASSIGNMENT_SCHEMA_VERSION,
        identity=LessonIdentityV1(**identity),  # type: ignore[arg-type]
        musical_content=LessonMusicalContentV1(
            format=LessonContentFormat.CANONICAL_EVENTS,
            ticks_per_quarter=480,
            events=(SerializedCanonicalEventV1("ev-1", 60, 0, 120),),
        ),
        playback=LessonPlaybackPolicyV1(),
        spatial_guidance=LessonSpatialGuidanceV1(
            instrument_profile_id="guitar-standard-6",
            fingering_policy_id="enumeration_v1",
        ),
        provenance=LessonProvenanceV1(
            created_by="t",
            created_at_utc="2026-01-01T00:00:00Z",
            source_type=LessonSourceType.MANUAL,
        ),
    )


def test_valid_minimal_assignment(minimal_assignment: LessonAssignmentV1) -> None:
    assert minimal_assignment.assignment_id == "assign-1"
    assert minimal_assignment.content_id == "content-1"
    assert minimal_assignment.assignment_id != minimal_assignment.content_id


def test_valid_fully_populated_assignment(populated_assignment: LessonAssignmentV1) -> None:
    assert populated_assignment.routing is not None
    assert populated_assignment.instruction.repetitions == 4
    assert populated_assignment.assessment.enabled is True
    assert len(populated_assignment.teacher_overrides) == 1


def test_empty_assignment_id_rejected() -> None:
    with pytest.raises(Exception, match="assignment_id"):
        _base(assignment_id="")


def test_empty_content_id_rejected() -> None:
    with pytest.raises(Exception, match="content_id"):
        _base(content_id=" ")


def test_missing_title_rejected() -> None:
    with pytest.raises(Exception, match="title"):
        _base(title="")


def test_unsupported_schema_rejected() -> None:
    with pytest.raises(LessonSchemaError, match="unsupported_schema"):
        LessonAssignmentV1(
            schema_id=LESSON_ASSIGNMENT_SCHEMA_ID,
            schema_version="2.0.0",
            identity=LessonIdentityV1("a", "c", "t"),
            musical_content=LessonMusicalContentV1(
                format=LessonContentFormat.CANONICAL_EVENTS,
                ticks_per_quarter=480,
                events=(SerializedCanonicalEventV1("ev-1", 60, 0, 120),),
            ),
            playback=LessonPlaybackPolicyV1(),
            spatial_guidance=LessonSpatialGuidanceV1("guitar-standard-6", "enumeration_v1"),
            provenance=LessonProvenanceV1(
                "t", "2026-01-01T00:00:00Z", LessonSourceType.MANUAL
            ),
        )


def test_immutable_dataclass(minimal_assignment: LessonAssignmentV1) -> None:
    with pytest.raises(AttributeError):
        minimal_assignment.title = "x"  # type: ignore[misc]


def test_deterministic_collection_types(minimal_assignment: LessonAssignmentV1) -> None:
    assert isinstance(minimal_assignment.musical_content.events, tuple)
    assert isinstance(minimal_assignment.teacher_overrides, tuple)


def test_duplicate_event_ids_rejected() -> None:
    with pytest.raises(LessonValidationError, match="duplicate_event_id"):
        LessonMusicalContentV1(
            format=LessonContentFormat.CANONICAL_EVENTS,
            ticks_per_quarter=480,
            events=(
                SerializedCanonicalEventV1("ev-1", 60, 0, 120),
                SerializedCanonicalEventV1("ev-1", 62, 120, 120),
            ),
        )


def test_invalid_ppq_rejected() -> None:
    with pytest.raises(LessonValidationError, match="invalid_ppq"):
        LessonMusicalContentV1(
            format=LessonContentFormat.CANONICAL_EVENTS,
            ticks_per_quarter=0,
            events=(SerializedCanonicalEventV1("ev-1", 60, 0, 120),),
        )
