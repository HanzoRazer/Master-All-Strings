"""Teacher override physical validation and selection priority."""

from __future__ import annotations

import pytest

from master_all_strings.core.spatial_mapping import generate_candidates
from master_all_strings.lesson.errors import TeacherOverrideError
from master_all_strings.lesson.models import (
    LessonAssignmentV1,
    TeacherOverrideV1,
)
from master_all_strings.lesson.overrides import validate_teacher_override
from master_all_strings.lesson.pipeline import run_mvp_lesson_pipeline
from master_all_strings.lesson.resolver import resolve_lesson_assignment


def test_valid_override_controls_selection(
    minimal_assignment: LessonAssignmentV1,
    instrument_catalog: dict,
) -> None:
    # E4 (64) has multiple candidates; choose B-string fret 5.
    assignment = LessonAssignmentV1(
        schema_id=minimal_assignment.schema_id,
        schema_version=minimal_assignment.schema_version,
        identity=minimal_assignment.identity,
        musical_content=minimal_assignment.musical_content,
        playback=minimal_assignment.playback,
        spatial_guidance=minimal_assignment.spatial_guidance,
        teacher_overrides=(TeacherOverrideV1("ev-1", "string-2", 5),),
        provenance=minimal_assignment.provenance,
    )
    result = run_mvp_lesson_pipeline(assignment, instrument_profiles=instrument_catalog)
    selected = result.selected_events[0]
    assert selected.selection_source == "teacher_override"
    assert selected.position.string_id == "string-2"
    assert selected.position.physical_fret_number == 5
    assert result.projection.notes[0].string_id == "string-2"


def test_invalid_string_rejected(
    minimal_assignment: LessonAssignmentV1,
    guitar_profile,
) -> None:
    event = minimal_assignment.musical_content.events[0]
    with pytest.raises(TeacherOverrideError, match="override_impossible_position"):
        validate_teacher_override(
            TeacherOverrideV1("ev-1", "string-99", 0),
            event=event,
            instrument=guitar_profile,
        )


def test_pitch_mismatch_rejected(
    minimal_assignment: LessonAssignmentV1,
    guitar_profile,
) -> None:
    event = minimal_assignment.musical_content.events[0]
    with pytest.raises(TeacherOverrideError, match="override_impossible_position"):
        validate_teacher_override(
            TeacherOverrideV1("ev-1", "string-1", 22),
            event=event,
            instrument=guitar_profile,
        )


def test_override_wins_over_soft_guidance(
    minimal_assignment: LessonAssignmentV1,
    instrument_catalog: dict,
) -> None:
    from master_all_strings.lesson.models import LessonSpatialGuidanceV1

    # Soft guidance prefers open strings / low frets; override forces string-2 fret 5.
    assignment = LessonAssignmentV1(
        schema_id=minimal_assignment.schema_id,
        schema_version=minimal_assignment.schema_version,
        identity=minimal_assignment.identity,
        musical_content=minimal_assignment.musical_content,
        playback=minimal_assignment.playback,
        spatial_guidance=LessonSpatialGuidanceV1(
            instrument_profile_id="guitar-standard-6",
            fingering_policy_id="enumeration_v1",
            preferred_fret_min=0,
            preferred_fret_max=3,
            open_string_preference="prefer",
        ),
        teacher_overrides=(TeacherOverrideV1("ev-1", "string-2", 5),),
        provenance=minimal_assignment.provenance,
    )
    result = run_mvp_lesson_pipeline(assignment, instrument_profiles=instrument_catalog)
    assert result.selected_events[0].position.physical_fret_number == 5


def test_candidates_still_come_from_msme(
    minimal_assignment: LessonAssignmentV1,
    guitar_profile,
) -> None:
    resolved = resolve_lesson_assignment(minimal_assignment)
    candidates = generate_candidates(resolved.events[0], guitar_profile)
    assert len(candidates) >= 2
