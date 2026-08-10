"""Serialization, digests, and round-trip tests."""

from __future__ import annotations

from master_all_strings.lesson.models import LessonAssignmentV1, LessonRoutingV1
from master_all_strings.lesson.serialization import (
    compute_assignment_artifact_digest,
    compute_lesson_behavior_digest,
    deserialize_lesson_assignment,
    serialize_lesson_assignment,
)


def test_round_trip_equality(populated_assignment: LessonAssignmentV1) -> None:
    text = serialize_lesson_assignment(populated_assignment)
    restored = deserialize_lesson_assignment(text)
    assert restored == populated_assignment


def test_utf8_json(minimal_assignment: LessonAssignmentV1) -> None:
    text = serialize_lesson_assignment(minimal_assignment)
    assert isinstance(text, str)
    text.encode("utf-8")
    assert text.endswith("\n")


def test_deterministic_output(minimal_assignment: LessonAssignmentV1) -> None:
    assert serialize_lesson_assignment(minimal_assignment) == serialize_lesson_assignment(
        minimal_assignment
    )


def test_schema_version_retained(minimal_assignment: LessonAssignmentV1) -> None:
    restored = deserialize_lesson_assignment(serialize_lesson_assignment(minimal_assignment))
    assert restored.schema_version == "1.0.0"
    assert restored.schema_id == minimal_assignment.schema_id


def test_null_routing_preserved(minimal_assignment: LessonAssignmentV1) -> None:
    restored = deserialize_lesson_assignment(serialize_lesson_assignment(minimal_assignment))
    assert restored.routing is None


def test_future_metadata_survives_round_trip(populated_assignment: LessonAssignmentV1) -> None:
    restored = deserialize_lesson_assignment(serialize_lesson_assignment(populated_assignment))
    assert restored.instruction.curriculum_ref == "curriculum/blues/unit-2"
    assert restored.assessment.timing_tolerance_ms == 40


def test_behavior_digest_excludes_routing(minimal_assignment: LessonAssignmentV1) -> None:
    with_routing = LessonAssignmentV1(
        schema_id=minimal_assignment.schema_id,
        schema_version=minimal_assignment.schema_version,
        identity=minimal_assignment.identity,
        musical_content=minimal_assignment.musical_content,
        playback=minimal_assignment.playback,
        spatial_guidance=minimal_assignment.spatial_guidance,
        teacher_overrides=minimal_assignment.teacher_overrides,
        instruction=minimal_assignment.instruction,
        assessment=minimal_assignment.assessment,
        provenance=minimal_assignment.provenance,
        routing=LessonRoutingV1("a", "b", "c"),
    )
    assert compute_lesson_behavior_digest(minimal_assignment) == compute_lesson_behavior_digest(
        with_routing
    )
    assert compute_assignment_artifact_digest(
        minimal_assignment
    ) != compute_assignment_artifact_digest(with_routing)


def test_save_reload_same_behavior_digest(populated_assignment: LessonAssignmentV1) -> None:
    restored = deserialize_lesson_assignment(serialize_lesson_assignment(populated_assignment))
    assert compute_lesson_behavior_digest(restored) == compute_lesson_behavior_digest(
        populated_assignment
    )
