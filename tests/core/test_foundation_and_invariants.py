"""Regression tests for the foundation validators, enum coercion, and the
tightened model invariants added when fixing the Phase 0-2 foundation review.
"""

from __future__ import annotations

import pytest

from master_all_strings.core.foundation import (
    require_index,
    require_midi_note,
    require_non_empty,
)
from master_all_strings.core.spatial_mapping import (
    CandidateScore,
    FingerboardMode,
    MappingConstraints,
    SpatialPosition,
    SpatialReferenceType,
    instrument_profile_from_mapping,
)
from master_all_strings.instruments import InstrumentProfile, StringProfile


class TestValidatorHardening:
    def test_require_midi_note_rejects_bool(self) -> None:
        with pytest.raises(ValueError, match="note"):
            require_midi_note(True, "note")  # type: ignore[arg-type]

    def test_require_non_empty_rejects_whitespace(self) -> None:
        with pytest.raises(ValueError, match="label"):
            require_non_empty("   ", "label")

    def test_require_index_rejects_bool(self) -> None:
        with pytest.raises(ValueError, match="order"):
            require_index(True, "order")  # type: ignore[arg-type]


class TestEnumCoercion:
    def test_instrument_profile_coerces_string_mode_and_enforces_invariant(self) -> None:
        # A raw string mode must still trip the fretted invariant (it would be
        # silently skipped if `is FingerboardMode.FRETTED` compared against a str).
        with pytest.raises(ValueError, match="physical_fret_count"):
            InstrumentProfile(
                schema_version="1.0.0",
                instrument_id="g",
                display_name="G",
                family="guitar",
                fingerboard_mode="fretted",  # type: ignore[arg-type]
                strings=(StringProfile("s1", "E2", 0, 40),),
                scale_length_mm=648.0,
                physical_fret_count=None,
            )

    def test_instrument_profile_rejects_unknown_mode(self) -> None:
        with pytest.raises(ValueError, match="fingerboard_mode"):
            InstrumentProfile(
                schema_version="1.0.0",
                instrument_id="g",
                display_name="G",
                family="guitar",
                fingerboard_mode="banana",  # type: ignore[arg-type]
                strings=(StringProfile("s1", "E2", 0, 40),),
                scale_length_mm=648.0,
                physical_fret_count=22,
            )

    def test_from_mapping_produces_real_enum(self) -> None:
        profile = instrument_profile_from_mapping(
            {
                "schema_version": "1.0.0",
                "instrument_id": "g",
                "display_name": "G",
                "family": "guitar",
                "fingerboard_mode": "fretted",
                "strings": [
                    {
                        "string_id": "s1",
                        "display_label": "E2",
                        "display_order": 0,
                        "open_midi_note": 40,
                    }
                ],
                "scale_length_mm": 648.0,
                "physical_fret_count": 22,
            }
        )
        assert isinstance(profile.fingerboard_mode, FingerboardMode)
        assert profile.fingerboard_mode is FingerboardMode.FRETTED

    def test_spatial_position_coerces_string_reference_type(self) -> None:
        with pytest.raises(ValueError, match="physical_fret_number"):
            SpatialPosition(
                string_id="string-1",
                course_id=None,
                sounding_midi_note=64,
                cents_offset=0.0,
                relative_semitone_position=1.0,
                physical_semitone_position_from_nut=1.0,
                physical_fret_number=None,
                reference_type="physical_fret",  # type: ignore[arg-type]
                normalized_position=0.1,
                distance_from_nut_mm=12.0,
                is_open_string=False,
            )


class TestTightenedInvariants:
    def test_zero_relative_position_must_be_open(self) -> None:
        with pytest.raises(ValueError, match="is_open_string"):
            SpatialPosition(
                string_id="string-1",
                course_id=None,
                sounding_midi_note=64,
                cents_offset=0.0,
                relative_semitone_position=0.0,
                physical_semitone_position_from_nut=0.0,
                physical_fret_number=0,
                reference_type=SpatialReferenceType.PHYSICAL_FRET,
                normalized_position=0.0,
                distance_from_nut_mm=0.0,
                is_open_string=False,
            )

    def test_candidate_score_rejects_blank_explanation(self) -> None:
        with pytest.raises(ValueError, match="explanation"):
            CandidateScore(total=1.0, components={}, explanation=("  ",))

    def test_constraints_reject_allowed_excluded_overlap(self) -> None:
        with pytest.raises(ValueError, match="allowed and excluded"):
            MappingConstraints(
                allowed_string_ids=("string-1",),
                excluded_string_ids=("string-1",),
            )

    def test_constraints_reject_duplicate_ids(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            MappingConstraints(excluded_string_ids=("s1", "s1"))

    def test_constraints_reject_blank_id(self) -> None:
        with pytest.raises(ValueError, match="entry"):
            MappingConstraints(excluded_string_ids=("",))
