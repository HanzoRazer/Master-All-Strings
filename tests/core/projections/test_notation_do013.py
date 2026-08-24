"""Notation projection (DO-013).

Most of these test a refusal rather than a feature. Notation's failure mode is
not crashing — it is rendering something plausible that misstates the music, so
the interesting assertions are the ones proving it declined to guess.
"""

from __future__ import annotations

import pytest

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.projections.contracts import (
    DisplayDuration,
    NotationDisplayPolicy,
    NotationEventKind,
    RestDerivation,
    UnsupportedFeatureCode,
)
from master_all_strings.core.projections.notation import (
    build_notation_projection,
    derive_display_duration,
    derive_global_silence_intervals,
    measure_length_ticks,
    partition_events_into_measures,
    spell_display_pitch,
)
from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.lesson.canonicalization import build_authored_lesson_revision
from master_all_strings.lesson.resolver import resolve_lesson_assignment
from master_all_strings.mvp.demo_library import load_demo_assignment, load_demo_manifest

PPQ = 480


def _event(event_id: str, start: int, duration: int, note: int = 60) -> MusicalEvent:
    return MusicalEvent(
        event_id=event_id, midi_note=note, start_tick=start, duration_ticks=duration
    )


def _meter(numerator: int = 4, denominator: int = 4, tick: int = 0) -> MeterChangeV1:
    return MeterChangeV1(
        schema_version=MeterChangeV1.SCHEMA_VERSION,
        tick=tick,
        numerator=numerator,
        denominator=denominator,
    )


def _revision(demo_id: str = "half_steps_one_string"):
    return build_authored_lesson_revision(
        resolve_lesson_assignment(load_demo_assignment(demo_id))
    ).revision


def _demo_ids() -> list[str]:
    return [entry.demo_id for entry in load_demo_manifest()]


# --- display durations: exact or nothing -------------------------------------


@pytest.mark.parametrize(
    ("ticks", "expected"),
    [
        (1920, DisplayDuration.WHOLE),
        (2880, DisplayDuration.DOTTED_WHOLE),
        (960, DisplayDuration.HALF),
        (1440, DisplayDuration.DOTTED_HALF),
        (480, DisplayDuration.QUARTER),
        (720, DisplayDuration.DOTTED_QUARTER),
        (240, DisplayDuration.EIGHTH),
        (360, DisplayDuration.DOTTED_EIGHTH),
        (120, DisplayDuration.SIXTEENTH),
        (180, DisplayDuration.DOTTED_SIXTEENTH),
        (60, DisplayDuration.THIRTY_SECOND),
        (90, DisplayDuration.DOTTED_THIRTY_SECOND),
    ],
)
def test_exact_durations_map_at_480_ppq(ticks: int, expected: DisplayDuration) -> None:
    assert derive_display_duration(ticks, ticks_per_quarter=PPQ) is expected


@pytest.mark.parametrize("ticks", [160, 320, 640])
def test_a_tuplet_duration_is_unsupported_not_rounded(ticks: int) -> None:
    """A triplet eighth is 160 ticks at 480 PPQ. The nearest value would be a lie."""

    assert derive_display_duration(ticks, ticks_per_quarter=PPQ) is None


def test_a_double_dotted_duration_is_unsupported() -> None:
    """Double-dotted quarter is 840 ticks. Single dots only."""

    assert derive_display_duration(840, ticks_per_quarter=PPQ) is None


def test_a_near_miss_is_not_accepted() -> None:
    """500 ticks is nearly a quarter, which is exactly why it must be refused."""

    assert derive_display_duration(500, ticks_per_quarter=PPQ) is None
    assert derive_display_duration(479, ticks_per_quarter=PPQ) is None
    assert derive_display_duration(481, ticks_per_quarter=PPQ) is None


def test_duration_mapping_follows_the_ppq_it_is_given() -> None:
    assert derive_display_duration(960, ticks_per_quarter=960) is DisplayDuration.QUARTER
    assert derive_display_duration(960, ticks_per_quarter=480) is DisplayDuration.HALF


def test_a_nonpositive_duration_is_refused() -> None:
    with pytest.raises(ScoreContractError):
        derive_display_duration(0, ticks_per_quarter=PPQ)


# --- pitch spelling ----------------------------------------------------------


@pytest.mark.parametrize(
    ("midi", "spelled"),
    [(60, "C4"), (61, "C#4"), (69, "A4"), (71, "B4"), (72, "C5"), (0, "C-1"), (127, "G9")],
)
def test_sharp_preferred_spelling(midi: int, spelled: str) -> None:
    assert spell_display_pitch(midi) == spelled


def test_spelling_is_deterministic_across_all_pitch_classes() -> None:
    first = [spell_display_pitch(n) for n in range(128)]
    assert first == [spell_display_pitch(n) for n in range(128)]
    assert all("b" not in name for name in first), "V1 policy is sharp-preferred"


def test_an_out_of_range_note_is_refused() -> None:
    with pytest.raises(ScoreContractError):
        spell_display_pitch(128)


# --- measures ----------------------------------------------------------------


def test_measure_length_for_common_meters() -> None:
    assert measure_length_ticks(_meter(4, 4), ticks_per_quarter=PPQ) == 1920
    assert measure_length_ticks(_meter(3, 4), ticks_per_quarter=PPQ) == 1440
    assert measure_length_ticks(_meter(6, 8), ticks_per_quarter=PPQ) == 1440
    assert measure_length_ticks(_meter(2, 2), ticks_per_quarter=PPQ) == 1920


def test_a_meter_that_does_not_divide_evenly_is_refused() -> None:
    """Rounding here would put the error into every subsequent barline."""

    with pytest.raises(ScoreContractError, match="divide evenly"):
        measure_length_ticks(_meter(1, 64), ticks_per_quarter=10)


def test_measures_restart_at_a_meter_change() -> None:
    measures = partition_events_into_measures(
        events=(),
        meter_changes=(_meter(4, 4, 0), _meter(3, 4, 1920)),
        ticks_per_quarter=PPQ,
        total_ticks=1920 + 1440 * 2,
    )
    spans = [(start, end, f"{m.numerator}/{m.denominator}") for start, end, m in measures]
    assert spans == [
        (0, 1920, "4/4"),
        (1920, 3360, "3/4"),
        (3360, 4800, "3/4"),
    ]


def test_a_meter_map_not_starting_at_zero_is_refused() -> None:
    with pytest.raises(ScoreContractError, match="begin at tick 0"):
        partition_events_into_measures(
            events=(), meter_changes=(_meter(4, 4, 480),), ticks_per_quarter=PPQ, total_ticks=1920
        )


def test_an_absent_meter_map_is_refused() -> None:
    with pytest.raises(ScoreContractError, match="refusing to assume"):
        partition_events_into_measures(
            events=(), meter_changes=(), ticks_per_quarter=PPQ, total_ticks=1920
        )


# --- rests: global silence only ----------------------------------------------


def test_a_gap_between_notes_becomes_a_rest() -> None:
    events = (_event("a", 0, 480), _event("b", 720, 240))
    assert derive_global_silence_intervals(events, total_ticks=960) == ((480, 720),)


def test_silence_before_the_first_note_is_a_rest() -> None:
    events = (_event("a", 480, 480),)
    assert derive_global_silence_intervals(events, total_ticks=960) == ((0, 480),)


def test_a_held_note_suppresses_a_rest_under_a_later_onset() -> None:
    """The failure the naive version makes.

    Looking at gaps between consecutive *starts* sees 480 ticks between these two
    onsets and writes a rest there -- straight through a note that is still
    sounding.
    """

    events = (_event("held", 0, 1920), _event("second", 480, 240))
    assert derive_global_silence_intervals(events, total_ticks=1920) == ()


def test_overlapping_spans_merge_before_the_complement_is_taken() -> None:
    events = (_event("a", 0, 480), _event("b", 240, 480), _event("c", 960, 240))
    assert derive_global_silence_intervals(events, total_ticks=1200) == ((720, 960),)


def test_no_events_yields_no_rests() -> None:
    assert derive_global_silence_intervals((), total_ticks=1920) == ()


def test_the_polyphonic_demo_produces_no_false_rests() -> None:
    """simultaneous_notes is the real corpus case for this."""

    projection = build_notation_projection(_revision("simultaneous_notes"))
    rests = [
        event
        for measure in projection.measures
        for event in measure.events
        if event.event_kind is NotationEventKind.REST
    ]
    for rest in rests:
        overlapping = [
            note
            for measure in projection.measures
            for note in measure.events
            if note.event_kind is NotationEventKind.NOTE
            and note.start_tick < rest.start_tick + rest.duration_ticks
            and note.start_tick + note.duration_ticks > rest.start_tick
        ]
        assert not overlapping, "a rest overlaps a sounding note"


def test_polyphony_reports_the_voice_limitation() -> None:
    projection = build_notation_projection(_revision("simultaneous_notes"))
    codes = {feature.code for feature in projection.unsupported_features}
    assert UnsupportedFeatureCode.VOICE_SPECIFIC_REST_INFERENCE_UNAVAILABLE in codes


def test_a_monophonic_lesson_claims_no_voice_limitation() -> None:
    projection = build_notation_projection(_revision("half_steps_one_string"))
    codes = {feature.code for feature in projection.unsupported_features}
    assert UnsupportedFeatureCode.VOICE_SPECIFIC_REST_INFERENCE_UNAVAILABLE not in codes


def test_rests_are_projection_derived_and_cite_no_canonical_event() -> None:
    projection = build_notation_projection(_revision("half_steps_one_string"))
    for measure in projection.measures:
        for event in measure.events:
            if event.event_kind is NotationEventKind.REST:
                assert event.canonical_event_id is None
                assert event.derivation is RestDerivation.GLOBAL_SILENCE


def test_deriving_rests_does_not_add_canonical_events() -> None:
    revision = _revision("half_steps_one_string")
    before = len(revision.events)
    build_notation_projection(revision)
    assert len(revision.events) == before


# --- ties --------------------------------------------------------------------


def test_adjacent_same_pitch_notes_are_not_tied() -> None:
    """A tie asserts one sounded event. Nothing canonical says these are."""

    projection = build_notation_projection(_revision("half_steps_one_string"))
    notes = [
        event
        for measure in projection.measures
        for event in measure.events
        if event.event_kind is NotationEventKind.NOTE
    ]
    assert notes
    for event in notes:
        assert not hasattr(event, "tie")
        assert not hasattr(event, "tie_state")


# --- whole-projection behaviour ----------------------------------------------


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_every_bundled_lesson_projects(demo_id: str) -> None:
    projection = build_notation_projection(_revision(demo_id))
    assert projection.measures
    assert projection.display_policy is NotationDisplayPolicy.SHARP_PREFERRED_V1
    assert projection.ticks_per_quarter == PPQ


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_every_canonical_note_appears_exactly_once(demo_id: str) -> None:
    revision = _revision(demo_id)
    projection = build_notation_projection(revision)
    notated = [
        event.canonical_event_id
        for measure in projection.measures
        for event in measure.events
        if event.event_kind is NotationEventKind.NOTE
    ]
    assert sorted(notated) == sorted(event.event_id for event in revision.events)


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_notation_is_deterministic(demo_id: str) -> None:
    revision = _revision(demo_id)
    assert build_notation_projection(revision) == build_notation_projection(revision)


def test_notation_carries_no_instrument_profile() -> None:
    """Notation of a melody is the same notation however it is fingered."""

    from dataclasses import fields

    from master_all_strings.core.projections.contracts import NotationProjectionV1

    names = {field.name for field in fields(NotationProjectionV1)}
    assert "instrument_profile_id" not in names
    assert not any("string" in name or "fret" in name for name in names)


def test_a_foreign_object_is_refused() -> None:
    with pytest.raises(ScoreContractError, match="CanonicalScoreRevisionV1"):
        build_notation_projection({"revision_id": "nope"})  # type: ignore[arg-type]
