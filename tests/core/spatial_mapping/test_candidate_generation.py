"""Unit, boundary, and invariant tests for MSME candidate generation.

Expected counts and positions are derived by hand from each profile's tuning and
declared maxima, not captured from the implementation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from master_all_strings.core.foundation import FingerboardMode, SpatialMappingError
from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.spatial_mapping import (
    MappingConstraints,
    SpatialPosition,
    SpatialReferenceType,
    generate_candidates,
    instrument_profile_from_mapping,
)
from master_all_strings.instruments import InstrumentProfile, StringProfile

_EXAMPLES = Path(__file__).resolve().parents[3] / "resources" / "instruments" / "examples"


def _profile(name: str) -> InstrumentProfile:
    return instrument_profile_from_mapping(json.loads((_EXAMPLES / f"{name}.json").read_text()))


def _event(midi_note: int, cents_offset: float = 0.0) -> MusicalEvent:
    return MusicalEvent(
        event_id="event-1",
        midi_note=midi_note,
        start_tick=0,
        duration_ticks=480,
        cents_offset=cents_offset,
    )


@pytest.fixture
def guitar() -> InstrumentProfile:
    return _profile("guitar-standard-6")


@pytest.fixture
def violin() -> InstrumentProfile:
    return _profile("violin-standard")


@pytest.fixture
def bass() -> InstrumentProfile:
    return _profile("bass-fretless-4")


@pytest.fixture
def mandolin() -> InstrumentProfile:
    return _profile("mandolin-standard")


def _custom_profile(**overrides: Any) -> InstrumentProfile:
    base: dict[str, Any] = {
        "schema_version": "1.0.0",
        "instrument_id": "custom",
        "display_name": "Custom",
        "family": "test",
        "fingerboard_mode": FingerboardMode.FRETTED,
        "strings": (
            StringProfile(
                string_id="only",
                display_label="E2",
                display_order=0,
                open_midi_note=40,
                maximum_semitone_position=12,
            ),
        ),
        "scale_length_mm": 648.0,
        "physical_fret_count": 12,
    }
    return InstrumentProfile(**{**base, **overrides})


class TestOpenStrings:
    def test_open_string_pitch_yields_open_candidate(self, guitar: InstrumentProfile) -> None:
        # E2 = 40 is the open 6th string and is below every other string's open pitch.
        candidates = generate_candidates(_event(40), guitar)
        assert len(candidates) == 1
        assert candidates[0].string_id == "string-6"
        assert candidates[0].is_open_string is True
        assert candidates[0].relative_semitone_position == 0.0

    def test_open_string_is_one_of_several(self, guitar: InstrumentProfile) -> None:
        # G3 = 55 is open on string-3 and stopped on strings 4, 5 and 6.
        candidates = generate_candidates(_event(55), guitar)
        assert len(candidates) == 4
        assert sum(c.is_open_string for c in candidates) == 1


class TestAmbiguityIsPreserved:
    def test_multiple_strings_produce_multiple_candidates(
        self, guitar: InstrumentProfile
    ) -> None:
        # E4 = 64: playable on strings 5..1; string-6 would need 24 > max 22.
        candidates = generate_candidates(_event(64), guitar)
        assert [c.string_id for c in candidates] == [
            "string-5",
            "string-4",
            "string-3",
            "string-2",
            "string-1",
        ]

    def test_every_candidate_sounds_the_requested_pitch(
        self, guitar: InstrumentProfile
    ) -> None:
        for candidate in generate_candidates(_event(57), guitar):
            assert candidate.sounding_midi_note == 57


class TestRangeBoundaries:
    def test_lowest_playable_note(self, guitar: InstrumentProfile) -> None:
        assert len(generate_candidates(_event(40), guitar)) == 1

    def test_below_lowest_note_is_unplayable(self, guitar: InstrumentProfile) -> None:
        assert generate_candidates(_event(39), guitar) == ()

    def test_highest_playable_note(self, guitar: InstrumentProfile) -> None:
        # string-1 open 64 + 22 frets = 86.
        assert len(generate_candidates(_event(86), guitar)) == 1

    def test_above_highest_note_is_unplayable(self, guitar: InstrumentProfile) -> None:
        assert generate_candidates(_event(87), guitar) == ()

    def test_first_fret(self, guitar: InstrumentProfile) -> None:
        candidates = generate_candidates(_event(41), guitar)
        assert candidates[0].physical_fret_number == 1
        assert candidates[0].is_open_string is False

    def test_last_fret_inclusive(self, guitar: InstrumentProfile) -> None:
        candidate = generate_candidates(_event(86), guitar)[0]
        assert candidate.physical_fret_number == 22

    def test_unplayable_returns_empty_tuple_and_does_not_raise(
        self, guitar: InstrumentProfile
    ) -> None:
        result = generate_candidates(_event(100), guitar)
        assert result == ()
        assert isinstance(result, tuple)


class TestTightestBoundWins:
    """Every shipped fixture sets the two bounds equal, so this is otherwise untested."""

    def test_per_string_maximum_is_tighter_than_fret_count(self) -> None:
        profile = _custom_profile(
            strings=(
                StringProfile(
                    string_id="only",
                    display_label="E2",
                    display_order=0,
                    open_midi_note=40,
                    maximum_semitone_position=5,
                ),
            ),
            physical_fret_count=12,
        )
        assert len(generate_candidates(_event(45), profile)) == 1
        assert generate_candidates(_event(46), profile) == ()

    def test_fret_count_is_tighter_than_per_string_maximum(self) -> None:
        profile = _custom_profile(
            strings=(
                StringProfile(
                    string_id="only",
                    display_label="E2",
                    display_order=0,
                    open_midi_note=40,
                    maximum_semitone_position=12,
                ),
            ),
            physical_fret_count=5,
        )
        assert len(generate_candidates(_event(45), profile)) == 1
        assert generate_candidates(_event(46), profile) == ()

    def test_constraint_maximum_relative_is_applied(self, guitar: InstrumentProfile) -> None:
        unconstrained = generate_candidates(_event(64), guitar)
        constrained = generate_candidates(
            _event(64), guitar, MappingConstraints(maximum_relative_semitone_position=9.0)
        )
        assert len(unconstrained) == 5
        assert [c.string_id for c in constrained] == ["string-3", "string-2", "string-1"]

    def test_fretless_without_declared_maximum_is_bounded_by_midi(self) -> None:
        profile = _custom_profile(
            fingerboard_mode=FingerboardMode.FRETLESS,
            physical_fret_count=None,
            strings=(
                StringProfile(
                    string_id="only",
                    display_label="E2",
                    display_order=0,
                    open_midi_note=40,
                    maximum_semitone_position=None,
                ),
            ),
        )
        # No declared ceiling: the profile does not reject, and the MIDI domain bounds it.
        assert len(generate_candidates(_event(127), profile)) == 1


class TestDeterministicOrdering:
    def test_sorted_by_display_order_then_relative_position(
        self, guitar: InstrumentProfile
    ) -> None:
        candidates = generate_candidates(_event(64), guitar)
        keys = [(c.display_order, c.relative_semitone_position) for c in candidates]
        assert keys == sorted(keys)

    def test_repeated_calls_are_identical(self, guitar: InstrumentProfile) -> None:
        first = generate_candidates(_event(64), guitar)
        second = generate_candidates(_event(64), guitar)
        assert first == second

    def test_order_is_independent_of_profile_string_declaration_order(self) -> None:
        strings = (
            StringProfile(
                string_id="high", display_label="E4", display_order=1, open_midi_note=64,
                maximum_semitone_position=22,
            ),
            StringProfile(
                string_id="low", display_label="E2", display_order=0, open_midi_note=40,
                maximum_semitone_position=22,
            ),
        )
        forward = _custom_profile(strings=strings, physical_fret_count=22)
        reversed_profile = _custom_profile(strings=tuple(reversed(strings)), physical_fret_count=22)
        assert [c.string_id for c in generate_candidates(_event(64), forward)] == [
            c.string_id for c in generate_candidates(_event(64), reversed_profile)
        ]


class TestCapoBehavior:
    def test_capo_raises_the_effective_open_pitch(self, guitar: InstrumentProfile) -> None:
        # With a capo at 2 the open 6th string sounds 42, so 40 is no longer playable.
        assert generate_candidates(_event(40), guitar, MappingConstraints(capo_position=2.0)) == ()

    def test_note_stopped_at_the_capo_is_open_with_nut_distance(
        self, guitar: InstrumentProfile
    ) -> None:
        candidates = generate_candidates(
            _event(52), guitar, MappingConstraints(capo_position=2.0)
        )
        at_capo = next(c for c in candidates if c.string_id == "string-4")
        assert at_capo.is_open_string is True
        assert at_capo.relative_semitone_position == 0.0
        assert at_capo.physical_semitone_position_from_nut == 2.0
        assert at_capo.physical_fret_number == 2

    def test_fractional_capo_on_fretted_instrument_is_rejected(
        self, guitar: InstrumentProfile
    ) -> None:
        # Positions from the nut stay integral regardless of the capo, so nothing
        # downstream would flag this; it would instead silently erase every
        # open-string candidate, since relative position could never reach 0.0.
        with pytest.raises(SpatialMappingError, match="whole-semitone capo_position"):
            generate_candidates(_event(62), guitar, MappingConstraints(capo_position=2.5))

    def test_fractional_capo_is_allowed_on_fretless(self, bass: InstrumentProfile) -> None:
        candidates = generate_candidates(
            _event(35), bass, MappingConstraints(capo_position=2.5)
        )
        assert candidates
        # The reference type describes the position measured from the nut, which the
        # semitone markers are anchored to, so it stays an exact semitone reference
        # even though the position relative to the capo is fractional.
        assert candidates[0].physical_semitone_position_from_nut == 7.0
        assert candidates[0].relative_semitone_position == 4.5
        assert candidates[0].reference_type is SpatialReferenceType.IMAGINARY_SEMITONE

    def test_integral_capo_expressed_as_float_is_accepted(
        self, guitar: InstrumentProfile
    ) -> None:
        candidates = generate_candidates(
            _event(62), guitar, MappingConstraints(capo_position=2.0)
        )
        assert len(candidates) == 5


class TestStringSelectionConstraints:
    def test_excluded_string_is_skipped(self, guitar: InstrumentProfile) -> None:
        candidates = generate_candidates(
            _event(64), guitar, MappingConstraints(excluded_string_ids=("string-1",))
        )
        assert all(c.string_id != "string-1" for c in candidates)
        assert len(candidates) == 4

    def test_allowed_list_restricts_to_named_strings(self, guitar: InstrumentProfile) -> None:
        candidates = generate_candidates(
            _event(64), guitar, MappingConstraints(allowed_string_ids=("string-3",))
        )
        assert [c.string_id for c in candidates] == ["string-3"]

    def test_disabled_string_is_skipped(self) -> None:
        profile = _custom_profile(
            strings=(
                StringProfile(
                    string_id="off", display_label="E2", display_order=0,
                    open_midi_note=40, enabled=False, maximum_semitone_position=12,
                ),
            ),
        )
        assert generate_candidates(_event(45), profile) == ()


class TestFretlessBehavior:
    def test_exact_semitone_uses_imaginary_reference(self, bass: InstrumentProfile) -> None:
        candidate = generate_candidates(_event(31), bass)[0]
        assert candidate.reference_type is SpatialReferenceType.IMAGINARY_SEMITONE
        assert candidate.physical_fret_number is None

    def test_cents_displaced_target_uses_continuous_reference(
        self, bass: InstrumentProfile
    ) -> None:
        for candidate in generate_candidates(_event(33, cents_offset=14.0), bass):
            assert candidate.reference_type is SpatialReferenceType.CONTINUOUS_POSITION
            assert candidate.cents_offset == 14.0

    def test_one_candidate_per_viable_string_not_a_sampled_continuum(
        self, violin: InstrumentProfile
    ) -> None:
        # A4 = 69 is open on string-a and stopped on string-g and string-d.
        candidates = generate_candidates(_event(69), violin)
        assert len(candidates) == 3
        assert len({c.string_id for c in candidates}) == 3

    def test_normalized_position_and_distance_are_derived(
        self, violin: InstrumentProfile
    ) -> None:
        candidate = generate_candidates(_event(57), violin)[0]
        assert 0.0 <= candidate.normalized_position <= 1.0
        assert candidate.distance_from_nut_mm is not None
        assert candidate.distance_from_nut_mm > 0.0

    def test_distance_is_none_without_scale_length(self) -> None:
        profile = _custom_profile(
            fingerboard_mode=FingerboardMode.FRETLESS,
            physical_fret_count=None,
            scale_length_mm=None,
        )
        assert generate_candidates(_event(45), profile)[0].distance_from_nut_mm is None


class TestMicrotonalOnFrettedInstruments:
    def test_cents_offset_is_carried_onto_the_nearest_fret(
        self, guitar: InstrumentProfile
    ) -> None:
        candidates = generate_candidates(_event(64, cents_offset=14.0), guitar)
        assert candidates
        for candidate in candidates:
            assert candidate.cents_offset == 14.0
            assert candidate.reference_type is SpatialReferenceType.PHYSICAL_FRET
            assert candidate.physical_fret_number is not None

    def test_cents_offset_does_not_change_the_candidate_set(
        self, guitar: InstrumentProfile
    ) -> None:
        plain = generate_candidates(_event(64), guitar)
        offset = generate_candidates(_event(64, cents_offset=-30.0), guitar)
        assert [c.string_id for c in plain] == [c.string_id for c in offset]


class TestArbitraryInstrumentShapes:
    def test_single_string_instrument(self) -> None:
        assert len(generate_candidates(_event(45), _custom_profile())) == 1

    def test_alternate_tuning_changes_candidate_set(self, guitar: InstrumentProfile) -> None:
        drop_d = tuple(
            StringProfile(
                string_id=s.string_id,
                display_label=s.display_label,
                display_order=s.display_order,
                open_midi_note=38 if s.string_id == "string-6" else s.open_midi_note,
                maximum_semitone_position=s.maximum_semitone_position,
            )
            for s in guitar.strings
        )
        retuned = _custom_profile(strings=drop_d, physical_fret_count=22)
        assert generate_candidates(_event(38), guitar) == ()
        assert len(generate_candidates(_event(38), retuned)) == 1

    def test_courses_yield_one_candidate_per_course(self, mandolin: InstrumentProfile) -> None:
        candidates = generate_candidates(_event(74), mandolin)
        assert [c.course_id for c in candidates] == ["course-g", "course-d", "course-a"]


class TestUnsupportedAndInvalid:
    def test_hybrid_mode_raises_explicitly(self) -> None:
        profile = _custom_profile(
            fingerboard_mode=FingerboardMode.HYBRID, physical_fret_count=None
        )
        with pytest.raises(SpatialMappingError, match="hybrid"):
            generate_candidates(_event(45), profile)

    def test_hybrid_error_names_what_is_missing(self) -> None:
        profile = _custom_profile(
            fingerboard_mode=FingerboardMode.HYBRID, physical_fret_count=None
        )
        with pytest.raises(SpatialMappingError, match="transition model"):
            generate_candidates(_event(45), profile)


class TestInvariants:
    @pytest.mark.parametrize("midi_note", [40, 55, 64, 70, 86])
    def test_every_candidate_satisfies_the_contract(
        self, guitar: InstrumentProfile, midi_note: int
    ) -> None:
        for candidate in generate_candidates(_event(midi_note), guitar):
            assert isinstance(candidate, SpatialPosition)
            assert candidate.relative_semitone_position >= 0.0
            assert 0.0 <= candidate.normalized_position <= 1.0
            assert candidate.is_open_string == (candidate.relative_semitone_position == 0.0)

    def test_result_is_an_immutable_tuple(self, guitar: InstrumentProfile) -> None:
        assert isinstance(generate_candidates(_event(64), guitar), tuple)

    def test_event_and_profile_are_not_mutated(self, guitar: InstrumentProfile) -> None:
        event = _event(64)
        before_event = (event.midi_note, event.cents_offset, event.event_id)
        before_strings = tuple(s.open_midi_note for s in guitar.strings)
        generate_candidates(event, guitar)
        assert (event.midi_note, event.cents_offset, event.event_id) == before_event
        assert tuple(s.open_midi_note for s in guitar.strings) == before_strings

    def test_candidate_string_ids_exist_on_the_profile(self, guitar: InstrumentProfile) -> None:
        valid = {s.string_id for s in guitar.strings}
        assert all(c.string_id in valid for c in generate_candidates(_event(64), guitar))

    def test_display_order_matches_the_originating_string(
        self, guitar: InstrumentProfile
    ) -> None:
        orders = {s.string_id: s.display_order for s in guitar.strings}
        for candidate in generate_candidates(_event(64), guitar):
            assert candidate.display_order == orders[candidate.string_id]

    def test_no_renderer_coordinates_are_produced(self, guitar: InstrumentProfile) -> None:
        candidate = generate_candidates(_event(64), guitar)[0]
        fields = set(vars(candidate))
        assert not fields & {"x", "y", "pixel_x", "pixel_y", "screen_position"}
