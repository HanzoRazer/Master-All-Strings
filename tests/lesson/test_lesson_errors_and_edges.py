"""Additional edge coverage for lesson validation and serialization."""

from __future__ import annotations

import pytest

from master_all_strings.lesson.enums import LessonSourceType
from master_all_strings.lesson.errors import LessonSchemaError, LessonValidationError
from master_all_strings.lesson.models import (
    LESSON_ASSIGNMENT_SCHEMA_ID,
    LessonProvenanceV1,
    LessonRoutingV1,
    TeacherOverrideV1,
)
from master_all_strings.lesson.resolver import LessonAssignmentResolver
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.lesson.validation import require_override_event


def test_deserialize_malformed_json() -> None:
    with pytest.raises(LessonValidationError, match="malformed"):
        deserialize_lesson_assignment("{not-json")


def test_deserialize_wrong_schema_id() -> None:
    with pytest.raises(LessonSchemaError, match="unsupported_schema"):
        deserialize_lesson_assignment(
            {
                "schema_id": "other",
                "schema_version": "1.0.0",
            }
        )


def test_absolute_unix_path_rejected() -> None:
    with pytest.raises(LessonValidationError, match="absolute_path"):
        LessonProvenanceV1(
            created_by="x",
            created_at_utc="2026-01-01T00:00:00Z",
            source_type=LessonSourceType.MIDI_IMPORT,
            source_name="/tmp/exercise.mid",
        )


def test_require_override_event() -> None:
    with pytest.raises(LessonValidationError, match="override_unknown_event"):
        require_override_event(
            TeacherOverrideV1("missing", "string-1", 0),
            event_ids={"ev-1"},
        )


def test_routing_blank_rejected() -> None:
    with pytest.raises(ValueError, match="sender_device_id"):
        LessonRoutingV1(sender_device_id=" ")


def test_schema_id_constant() -> None:
    assert LESSON_ASSIGNMENT_SCHEMA_ID == "master_all_strings.lesson_assignment"


def test_resolver_class_wrapper(minimal_assignment) -> None:
    resolved = LessonAssignmentResolver().resolve(minimal_assignment)
    assert resolved.assignment_id == minimal_assignment.assignment_id
