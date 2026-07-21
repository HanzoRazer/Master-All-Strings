"""Direct tests for the internal candidate builders.

These cover the contract guards the builder enforces for callers that bypass
``generate_candidates``, which the generation-level tests cannot reach because
generation only ever supplies positions derived from integer MIDI arithmetic.
"""

from __future__ import annotations

import pytest

from master_all_strings.core.foundation import FingerboardMode, SpatialMappingError
from master_all_strings.core.spatial_mapping.candidate_builders import build_candidate
from master_all_strings.core.spatial_mapping.enums import SpatialReferenceType
from master_all_strings.instruments import StringProfile

_STRING = StringProfile(
    string_id="string-1",
    display_label="E4",
    display_order=5,
    open_midi_note=64,
    course_id="course-e",
    maximum_semitone_position=22,
)


def _build(**overrides: object) -> object:
    base: dict[str, object] = {
        "string": _STRING,
        "fingerboard_mode": FingerboardMode.FRETTED,
        "scale_length_mm": 648.0,
        "sounding_midi_note": 69,
        "cents_offset": 0.0,
        "relative_semitone_position": 5.0,
        "physical_semitone_position_from_nut": 5.0,
    }
    return build_candidate(**{**base, **overrides})  # type: ignore[arg-type]


def test_fretted_rejects_a_fractional_position_from_the_nut() -> None:
    with pytest.raises(SpatialMappingError, match="whole-semitone positions"):
        _build(physical_semitone_position_from_nut=5.5, relative_semitone_position=5.5)


def test_hybrid_is_rejected_at_the_builder_too() -> None:
    with pytest.raises(SpatialMappingError, match="hybrid"):
        _build(fingerboard_mode=FingerboardMode.HYBRID)


def test_near_integral_positions_are_snapped() -> None:
    candidate = _build(
        relative_semitone_position=5.0 + 1e-13,
        physical_semitone_position_from_nut=5.0 + 1e-13,
    )
    assert candidate.relative_semitone_position == 5.0  # type: ignore[attr-defined]
    assert candidate.physical_fret_number == 5  # type: ignore[attr-defined]


def test_snapping_keeps_the_open_string_biconditional_exact() -> None:
    candidate = _build(
        relative_semitone_position=1e-13,
        physical_semitone_position_from_nut=1e-13,
    )
    assert candidate.relative_semitone_position == 0.0  # type: ignore[attr-defined]
    assert candidate.is_open_string is True  # type: ignore[attr-defined]


def test_course_and_display_order_are_copied_from_the_string() -> None:
    candidate = _build()
    assert candidate.course_id == "course-e"  # type: ignore[attr-defined]
    assert candidate.display_order == 5  # type: ignore[attr-defined]


def test_fretless_exact_semitone_uses_imaginary_reference() -> None:
    candidate = _build(fingerboard_mode=FingerboardMode.FRETLESS)
    assert candidate.reference_type is SpatialReferenceType.IMAGINARY_SEMITONE  # type: ignore[attr-defined]
    assert candidate.physical_fret_number is None  # type: ignore[attr-defined]


def test_fretless_fractional_position_uses_continuous_reference() -> None:
    candidate = _build(
        fingerboard_mode=FingerboardMode.FRETLESS,
        relative_semitone_position=5.5,
        physical_semitone_position_from_nut=5.5,
    )
    assert candidate.reference_type is SpatialReferenceType.CONTINUOUS_POSITION  # type: ignore[attr-defined]
