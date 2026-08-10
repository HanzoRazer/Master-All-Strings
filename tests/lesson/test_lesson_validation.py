"""Whole-object validation tests."""

from __future__ import annotations

import pytest

from master_all_strings.lesson.errors import LessonValidationError, TeacherOverrideError
from master_all_strings.lesson.models import LessonAssignmentV1, TeacherOverrideV1
from master_all_strings.lesson.validation import validate_assignment


def test_validate_minimal_ok(
    minimal_assignment: LessonAssignmentV1,
    instrument_catalog: dict,
) -> None:
    validate_assignment(minimal_assignment, instrument_profiles=instrument_catalog)


def test_unknown_instrument_rejected_when_catalog_supplied(
    minimal_assignment: LessonAssignmentV1,
) -> None:
    with pytest.raises(LessonValidationError, match="unknown_instrument"):
        validate_assignment(minimal_assignment, instrument_profiles={})


def test_override_unknown_event(
    minimal_assignment: LessonAssignmentV1,
    instrument_catalog: dict,
) -> None:
    bad = LessonAssignmentV1(
        schema_id=minimal_assignment.schema_id,
        schema_version=minimal_assignment.schema_version,
        identity=minimal_assignment.identity,
        musical_content=minimal_assignment.musical_content,
        playback=minimal_assignment.playback,
        spatial_guidance=minimal_assignment.spatial_guidance,
        teacher_overrides=(
            TeacherOverrideV1("missing", "string-1", 0),
        ),
        instruction=minimal_assignment.instruction,
        assessment=minimal_assignment.assessment,
        provenance=minimal_assignment.provenance,
    )
    with pytest.raises(TeacherOverrideError, match="override_unknown_event"):
        validate_assignment(bad, instrument_profiles=instrument_catalog)
