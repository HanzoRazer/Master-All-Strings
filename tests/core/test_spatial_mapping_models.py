from __future__ import annotations

import pytest

from master_all_strings.core.spatial_mapping import (
    AuditoryPositionReference,
    CandidateScore,
    MappingConstraints,
    MappingPreferences,
    OpenStringPolicy,
    SpatialAnnotation,
    SpatialPosition,
    SpatialReferenceType,
    to_serializable_dict,
)


def test_spatial_position_requires_physical_fret_number_for_physical_frets() -> None:
    with pytest.raises(ValueError, match="physical_fret_number"):
        SpatialPosition(
            string_id="string-1",
            course_id=None,
            sounding_midi_note=64,
            cents_offset=0.0,
            relative_semitone_position=1.0,
            physical_semitone_position_from_nut=1.0,
            physical_fret_number=None,
            reference_type=SpatialReferenceType.PHYSICAL_FRET,
            normalized_position=0.1,
            distance_from_nut_mm=12.0,
            is_open_string=False,
        )


def test_open_string_position_requires_zero_relative_semitone_position() -> None:
    with pytest.raises(ValueError, match="open-string"):
        SpatialPosition(
            string_id="string-1",
            course_id=None,
            sounding_midi_note=64,
            cents_offset=0.0,
            relative_semitone_position=1.0,
            physical_semitone_position_from_nut=1.0,
            physical_fret_number=1,
            reference_type=SpatialReferenceType.PHYSICAL_FRET,
            normalized_position=0.1,
            distance_from_nut_mm=12.0,
            is_open_string=True,
        )


def test_contracts_are_serializable() -> None:
    score = CandidateScore(total=1.5, components={"movement": 1.0}, explanation=("stable",))
    payload = to_serializable_dict(score)

    assert payload == {
        "total": 1.5,
        "components": {"movement": 1.0},
        "explanation": ["stable"],
    }


def test_phase_one_supporting_contracts_validate() -> None:
    constraints = MappingConstraints(capo_position=2.0, maximum_relative_semitone_position=12.0)
    preferences = MappingPreferences(open_string_policy=OpenStringPolicy.PREFER, lower_position_bias=1.0)
    auditory_reference = AuditoryPositionReference(
        open_string_midi_note=55,
        target_midi_note=59,
        interval_semitones=4.0,
        target_cents_offset=0.0,
        interval_label="major third",
    )
    annotation = SpatialAnnotation(
        primary_label="Guitar string 1 fret 3",
        secondary_label=None,
        pitch_label="G4",
        string_label="string 1",
        position_label="physical fret 3",
        reference_marker_label=None,
        accessibility_text="Play G4 on string 1 at physical fret 3.",
        auditory_reference=auditory_reference,
    )

    assert constraints.capo_position == 2.0
    assert preferences.open_string_policy is OpenStringPolicy.PREFER
    assert annotation.auditory_reference is auditory_reference
