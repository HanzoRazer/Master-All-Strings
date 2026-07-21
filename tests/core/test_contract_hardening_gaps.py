"""Regression tests for contract holes found while triaging the PR #2 risk review.

These cover fields that the first hardening pass declared but did not enforce:
integer-typed fields that still accepted ``bool``, an entirely unvalidated fret
number, optional identifiers that accepted blanks, and the mixed exception
families. Exception classes are asserted exactly (``SpatialMappingError``, not the
``ValueError`` base) so the error surface cannot silently drift back apart.
"""

from __future__ import annotations

from typing import Any

import pytest

from master_all_strings.core.foundation import FingerboardMode, SpatialMappingError
from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.spatial_mapping import (
    AuditoryPositionReference,
    MappingConstraints,
    MappingPreferences,
    SpatialAnnotation,
    SpatialPosition,
    SpatialReferenceType,
)
from master_all_strings.instruments import InstrumentProfile, ReferenceMarker, StringProfile


def _string(**overrides: Any) -> StringProfile:
    base: dict[str, Any] = {
        "string_id": "string-1",
        "display_label": "E4",
        "display_order": 0,
        "open_midi_note": 64,
    }
    return StringProfile(**{**base, **overrides})


def _profile(**overrides: Any) -> InstrumentProfile:
    base: dict[str, Any] = {
        "schema_version": "1.0.0",
        "instrument_id": "test-instrument",
        "display_name": "Test Instrument",
        "family": "guitar",
        "fingerboard_mode": FingerboardMode.FRETTED,
        "strings": (_string(),),
        "scale_length_mm": 648.0,
        "physical_fret_count": 22,
    }
    return InstrumentProfile(**{**base, **overrides})


def _position(**overrides: Any) -> SpatialPosition:
    base: dict[str, Any] = {
        "string_id": "string-1",
        "course_id": None,
        "sounding_midi_note": 66,
        "cents_offset": 0.0,
        "relative_semitone_position": 2.0,
        "physical_semitone_position_from_nut": 2.0,
        "physical_fret_number": 2,
        "reference_type": SpatialReferenceType.PHYSICAL_FRET,
        "normalized_position": 0.109,
        "distance_from_nut_mm": None,
        "is_open_string": False,
    }
    return SpatialPosition(**{**base, **overrides})


class TestPhysicalFretCountRejectsNonIndexValues:
    """``True < 0`` is False, so a boolean previously passed every check."""

    @pytest.mark.parametrize("value", [True, False, 1.5, "22"])
    def test_rejects_non_integer_fret_count(self, value: Any) -> None:
        with pytest.raises(SpatialMappingError, match="physical_fret_count"):
            _profile(physical_fret_count=value)

    def test_rejects_negative_fret_count(self) -> None:
        with pytest.raises(SpatialMappingError, match="physical_fret_count"):
            _profile(physical_fret_count=-1)

    def test_accepts_zero_fret_count(self) -> None:
        assert _profile(physical_fret_count=0).physical_fret_count == 0


class TestPhysicalFretNumberIsValidated:
    """Presence was checked; the value itself never was."""

    @pytest.mark.parametrize("value", [-1, True, 1.5, "3"])
    def test_rejects_invalid_fret_number(self, value: Any) -> None:
        with pytest.raises(SpatialMappingError, match="physical_fret_number"):
            _position(physical_fret_number=value)

    def test_accepts_open_string_fret_zero(self) -> None:
        position = _position(
            relative_semitone_position=0.0,
            physical_semitone_position_from_nut=0.0,
            physical_fret_number=0,
            normalized_position=0.0,
            is_open_string=True,
        )
        assert position.physical_fret_number == 0


class TestReferenceTypeCoercionRaisesDomainError:
    @pytest.mark.parametrize("value", ["banana", "", True, 1, None])
    def test_invalid_reference_type_raises_domain_error(self, value: Any) -> None:
        with pytest.raises(SpatialMappingError, match="invalid reference_type"):
            _position(reference_type=value)

    def test_valid_raw_string_is_coerced_to_enum(self) -> None:
        position = _position(reference_type="physical_fret")
        assert position.reference_type is SpatialReferenceType.PHYSICAL_FRET


class TestOptionalIdentifiersRejectBlanks:
    @pytest.mark.parametrize("value", ["", "   "])
    def test_string_profile_course_id(self, value: str) -> None:
        with pytest.raises(SpatialMappingError, match="course_id"):
            _string(course_id=value)

    @pytest.mark.parametrize("value", ["", "   "])
    def test_spatial_position_course_id(self, value: str) -> None:
        with pytest.raises(SpatialMappingError, match="course_id"):
            _position(course_id=value)

    def test_none_course_id_still_allowed(self) -> None:
        assert _string(course_id=None).course_id is None

    def test_auditory_reference_interval_label(self) -> None:
        with pytest.raises(SpatialMappingError, match="interval_label"):
            AuditoryPositionReference(
                open_string_midi_note=64,
                target_midi_note=66,
                interval_semitones=2.0,
                target_cents_offset=0.0,
                interval_label="  ",
            )

    @pytest.mark.parametrize(
        "field_name", ["secondary_label", "reference_marker_label"]
    )
    def test_annotation_optional_labels(self, field_name: str) -> None:
        kwargs: dict[str, Any] = {
            "primary_label": "2",
            "secondary_label": None,
            "pitch_label": "F#4",
            "string_label": "E4",
            "position_label": "fret 2",
            "reference_marker_label": None,
            "accessibility_text": "F sharp 4 on the E string at fret 2",
        }
        kwargs[field_name] = "   "
        with pytest.raises(SpatialMappingError, match=field_name):
            SpatialAnnotation(**kwargs)


class TestMappingPreferencesIdentifierDiscipline:
    """MappingConstraints validated its id collections; preferences did not."""

    def test_rejects_blank_preferred_id(self) -> None:
        with pytest.raises(SpatialMappingError, match="preferred_string_ids"):
            MappingPreferences(preferred_string_ids=("",))

    def test_rejects_duplicate_preferred_ids(self) -> None:
        with pytest.raises(SpatialMappingError, match="duplicate"):
            MappingPreferences(preferred_string_ids=("s1", "s1"))


class TestReferenceMarkerCollectionInvariants:
    def test_rejects_duplicate_marker_ids(self) -> None:
        markers = (
            ReferenceMarker(marker_id="fret-3", semitone_offset=3.0, label="3rd"),
            ReferenceMarker(marker_id="fret-3", semitone_offset=5.0, label="5th"),
        )
        with pytest.raises(SpatialMappingError, match="marker_id"):
            _profile(reference_markers=markers)

    def test_allows_distinct_marker_ids(self) -> None:
        markers = (
            ReferenceMarker(marker_id="fret-3", semitone_offset=3.0, label="3rd"),
            ReferenceMarker(marker_id="fret-5", semitone_offset=5.0, label="5th"),
        )
        assert len(_profile(reference_markers=markers).reference_markers) == 2


class TestMetadataMatchesDeclaredContract:
    """``Mapping[str, JSONScalar]`` was annotated but never enforced."""

    @pytest.mark.parametrize("metadata", [{"": 1}, {"   ": 1}, {1: "x"}])
    def test_rejects_invalid_keys(self, metadata: Any) -> None:
        with pytest.raises(SpatialMappingError, match="metadata key"):
            _profile(metadata=metadata)

    @pytest.mark.parametrize("value", [{"nested": 1}, ["a"], object()])
    def test_rejects_non_scalar_values(self, value: Any) -> None:
        with pytest.raises(SpatialMappingError, match="JSON scalar"):
            _profile(metadata={"k": value})

    @pytest.mark.parametrize("value", ["s", 1, 1.5, True, None])
    def test_accepts_json_scalars(self, value: Any) -> None:
        assert _profile(metadata={"k": value}).metadata["k"] == value


class TestEnabledFlagIsBoolean:
    @pytest.mark.parametrize("value", [1, 0, "yes", None])
    def test_rejects_non_boolean_enabled(self, value: Any) -> None:
        with pytest.raises(SpatialMappingError, match="enabled"):
            _string(enabled=value)


class TestExceptionFamilyIsConsistent:
    """Every contract violation raises SpatialMappingError, which subclasses
    ValueError -- so pre-existing ``except ValueError`` handlers keep working."""

    def test_domain_error_subclasses_value_error(self) -> None:
        assert issubclass(SpatialMappingError, ValueError)

    @pytest.mark.parametrize(
        "factory",
        [
            lambda: MusicalEvent(event_id="e", midi_note=64, start_tick=0, duration_ticks=0),
            lambda: MusicalEvent(
                event_id="e", midi_note=64, start_tick=0, duration_ticks=1, velocity=200
            ),
            lambda: MusicalEvent(
                event_id="e", midi_note=64, start_tick=0, duration_ticks=True
            ),
            lambda: MappingConstraints(excluded_string_ids=("s1", "s1")),
            lambda: MappingConstraints(
                allowed_string_ids=("s1",), excluded_string_ids=("s1",)
            ),
            lambda: _position(relative_semitone_position=0.0, is_open_string=False),
        ],
    )
    def test_contract_violations_raise_domain_error(self, factory: Any) -> None:
        with pytest.raises(SpatialMappingError):
            factory()
