"""DO-012 timeline mapping: anchors, interpolation, and binding arithmetic.

The anchor table is the mechanism that lets the browser report ``position_tick``
without owning a second implementation of canonical tick conversion. So the
tests that matter most are the ones proving interpolation *reproduces* Musical
Core's mapping rather than approximating it.
"""

from __future__ import annotations

import pytest

from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.musical_timeline import ticks_to_seconds
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.presentation.contracts import (
    PRESENTATION_SCHEMA_VERSION,
    MediaSyncMode,
    MediaTimelineBindingV1,
    TimelineAnchorV1,
)
from master_all_strings.presentation.errors import PresentationContractError
from master_all_strings.presentation.timeline import (
    anchors_to_payload,
    binding_contains_lesson_time,
    binding_contains_media_time,
    build_teaching_playhead_state,
    build_teaching_timeline_state,
    build_timeline_anchors,
    lesson_time_to_media_time,
    media_time_to_lesson_time,
    resolve_focus_range_seconds,
    seconds_at_tick,
    tick_at_seconds,
    validate_media_timeline_binding,
)

V = PRESENTATION_SCHEMA_VERSION
PPQ = 960
LESSON = "half_steps_one_string"

TEMPO_120 = TempoChangeV1(schema_version=V, tick=0, microseconds_per_quarter=500_000)
TEMPO_90 = TempoChangeV1(schema_version=V, tick=1920, microseconds_per_quarter=666_667)


@pytest.fixture
def constant_anchors() -> tuple[TimelineAnchorV1, ...]:
    return build_timeline_anchors(
        ticks_per_quarter=PPQ, tempo_changes=(TEMPO_120,), total_ticks=8640
    )


@pytest.fixture
def tempo_change_anchors() -> tuple[TimelineAnchorV1, ...]:
    return build_timeline_anchors(
        ticks_per_quarter=PPQ, tempo_changes=(TEMPO_120, TEMPO_90), total_ticks=8640
    )


def _binding(**overrides: object) -> MediaTimelineBindingV1:
    base: dict[str, object] = {
        "schema_version": V,
        "binding_id": "binding-1",
        "lesson_id": LESSON,
        "media_id": "demo-video",
        "sync_mode": MediaSyncMode.SYNCHRONIZED,
        "lesson_anchor_seconds": 0.0,
        "media_anchor_seconds": 0.0,
    }
    base.update(overrides)
    return MediaTimelineBindingV1(**base)  # type: ignore[arg-type]


# --- anchor construction -----------------------------------------------------


def test_constant_tempo_needs_only_endpoints(constant_anchors) -> None:
    assert [a.tick for a in constant_anchors] == [0, 8640]


def test_tempo_change_becomes_an_anchor(tempo_change_anchors) -> None:
    """A boundary the table skipped would bend interpolation across two tempi."""

    assert [a.tick for a in tempo_change_anchors] == [0, 1920, 8640]


def test_anchors_begin_at_the_origin(tempo_change_anchors) -> None:
    assert tempo_change_anchors[0].tick == 0
    assert tempo_change_anchors[0].seconds == 0.0


def test_tempo_change_beyond_the_end_is_not_anchored() -> None:
    late = TempoChangeV1(schema_version=V, tick=99_999, microseconds_per_quarter=400_000)
    anchors = build_timeline_anchors(
        ticks_per_quarter=PPQ, tempo_changes=(TEMPO_120, late), total_ticks=1920
    )
    assert [a.tick for a in anchors] == [0, 1920]


def test_zero_length_lesson_yields_a_single_anchor() -> None:
    anchors = build_timeline_anchors(
        ticks_per_quarter=PPQ, tempo_changes=(TEMPO_120,), total_ticks=0
    )
    assert [a.tick for a in anchors] == [0]


def test_missing_tempo_map_is_refused() -> None:
    """Musical Core refuses to invent a leading tempo; so does the anchor builder."""

    with pytest.raises(ScoreContractError, match="refusing to assume a default tempo"):
        build_timeline_anchors(ticks_per_quarter=PPQ, tempo_changes=(), total_ticks=960)


@pytest.mark.parametrize("ppq", [0, -1, True])
def test_invalid_ticks_per_quarter_is_refused(ppq: object) -> None:
    with pytest.raises(PresentationContractError, match="ticks_per_quarter"):
        build_timeline_anchors(
            ticks_per_quarter=ppq,  # type: ignore[arg-type]
            tempo_changes=(TEMPO_120,),
            total_ticks=960,
        )


def test_anchors_to_payload_drops_schema_noise(constant_anchors) -> None:
    payload = anchors_to_payload(constant_anchors)
    assert payload == [{"tick": 0, "seconds": 0.0}, {"tick": 8640, "seconds": 4.5}]


# --- interpolation fidelity --------------------------------------------------


@pytest.mark.parametrize("tick", [0, 1, 480, 960, 1919, 1920, 1921, 4800, 8640])
def test_interpolation_reproduces_core_timing_across_a_tempo_change(
    tempo_change_anchors, tick: int
) -> None:
    """The whole design rests on this: interpolation must equal the Core mapping."""

    expected = ticks_to_seconds(
        tick, ticks_per_quarter=PPQ, tempo_changes=(TEMPO_120, TEMPO_90)
    )
    assert seconds_at_tick(tempo_change_anchors, tick) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize("tick", [0, 960, 2880, 8640])
def test_round_trip_tick_to_seconds_to_tick_is_stable(constant_anchors, tick: int) -> None:
    seconds = seconds_at_tick(constant_anchors, tick)
    assert tick_at_seconds(constant_anchors, seconds) == tick


def test_interpolation_is_monotonic(tempo_change_anchors) -> None:
    values = [seconds_at_tick(tempo_change_anchors, tick) for tick in range(0, 8641, 137)]
    assert values == sorted(values)


def test_positions_past_the_last_anchor_continue_at_the_final_rate(constant_anchors) -> None:
    """Seeking past the declared end must not fall off the table."""

    assert seconds_at_tick(constant_anchors, 17280) == pytest.approx(9.0, abs=1e-6)
    assert tick_at_seconds(constant_anchors, 9.0) == 17280


def test_single_anchor_table_degenerates_without_dividing_by_zero() -> None:
    anchors = build_timeline_anchors(
        ticks_per_quarter=PPQ, tempo_changes=(TEMPO_120,), total_ticks=0
    )
    assert seconds_at_tick(anchors, 500) == 0.0
    assert tick_at_seconds(anchors, 5.0) == 0


def test_negative_tick_is_refused(constant_anchors) -> None:
    with pytest.raises(PresentationContractError, match="tick"):
        seconds_at_tick(constant_anchors, -1)


def test_negative_seconds_is_refused(constant_anchors) -> None:
    with pytest.raises(PresentationContractError, match="seconds"):
        tick_at_seconds(constant_anchors, -0.5)


def test_empty_anchor_table_is_refused() -> None:
    with pytest.raises(PresentationContractError, match="must not be empty"):
        seconds_at_tick((), 0)


def test_anchor_table_not_starting_at_zero_is_refused() -> None:
    with pytest.raises(PresentationContractError, match="begin at tick 0"):
        seconds_at_tick((TimelineAnchorV1(schema_version=V, tick=960, seconds=0.5),), 960)


def test_non_increasing_anchor_ticks_are_refused() -> None:
    table = (
        TimelineAnchorV1(schema_version=V, tick=0, seconds=0.0),
        TimelineAnchorV1(schema_version=V, tick=0, seconds=1.0),
    )
    with pytest.raises(PresentationContractError, match="strictly increasing"):
        seconds_at_tick(table, 0)


def test_backwards_anchor_seconds_are_refused() -> None:
    table = (
        TimelineAnchorV1(schema_version=V, tick=0, seconds=1.0),
        TimelineAnchorV1(schema_version=V, tick=960, seconds=0.5),
    )
    with pytest.raises(PresentationContractError, match="non-decreasing"):
        seconds_at_tick(table, 0)


def test_foreign_values_in_the_anchor_table_are_refused() -> None:
    with pytest.raises(PresentationContractError, match="TimelineAnchorV1"):
        seconds_at_tick(({"tick": 0, "seconds": 0.0},), 0)  # type: ignore[arg-type]


# --- focus range -------------------------------------------------------------


def test_focus_range_converts_educational_ticks_to_transport_seconds(constant_anchors) -> None:
    start, end = resolve_focus_range_seconds(constant_anchors, start_tick=1920, end_tick=3840)
    assert (start, end) == pytest.approx((1.0, 2.0))


def test_focus_range_rejects_an_inverted_span(constant_anchors) -> None:
    with pytest.raises(PresentationContractError, match="end_tick"):
        resolve_focus_range_seconds(constant_anchors, start_tick=3840, end_tick=1920)


def test_focus_range_rejects_a_zero_width_span(constant_anchors) -> None:
    with pytest.raises(PresentationContractError, match="end_tick"):
        resolve_focus_range_seconds(constant_anchors, start_tick=960, end_tick=960)


# --- binding mapping ---------------------------------------------------------


def test_zero_offset_binding_is_identity() -> None:
    assert lesson_time_to_media_time(_binding(), 4.5) == pytest.approx(4.5)


def test_offset_binding_shifts_by_the_declared_anchors() -> None:
    """Lesson anchor 10 s / media anchor 3 s means lesson 14 s is media 7 s."""

    binding = _binding(lesson_anchor_seconds=10.0, media_anchor_seconds=3.0)
    assert lesson_time_to_media_time(binding, 14.0) == pytest.approx(7.0)


def test_reverse_mapping_round_trips() -> None:
    binding = _binding(lesson_anchor_seconds=10.0, media_anchor_seconds=3.0)
    media = lesson_time_to_media_time(binding, 14.0)
    assert media is not None
    assert media_time_to_lesson_time(binding, media) == pytest.approx(14.0)


def test_detached_binding_maps_nothing() -> None:
    """Detached media is not a follower, so it has no expected position."""

    binding = _binding(sync_mode=MediaSyncMode.DETACHED)
    assert lesson_time_to_media_time(binding, 1.0) is None
    assert media_time_to_lesson_time(binding, 1.0) is None


def test_position_past_the_binding_end_is_out_of_range() -> None:
    """The golden case: a 3.0 s clip cannot answer for a 4.5 s lesson."""

    binding = _binding(lesson_end_seconds=3.0, media_end_seconds=3.0)
    assert lesson_time_to_media_time(binding, 2.9) == pytest.approx(2.9)
    assert lesson_time_to_media_time(binding, 3.0) == pytest.approx(3.0)
    assert lesson_time_to_media_time(binding, 3.1) is None


def test_position_before_the_binding_start_is_out_of_range() -> None:
    binding = _binding(lesson_anchor_seconds=10.0, media_anchor_seconds=0.0)
    assert lesson_time_to_media_time(binding, 9.99) is None


def test_open_ended_binding_has_no_upper_bound() -> None:
    assert lesson_time_to_media_time(_binding(), 9_999.0) == pytest.approx(9_999.0)


def test_media_range_predicates_agree_with_the_declared_bounds() -> None:
    binding = _binding(lesson_end_seconds=3.0, media_end_seconds=3.0)
    assert binding_contains_lesson_time(binding, 1.5)
    assert not binding_contains_lesson_time(binding, 3.5)
    assert binding_contains_media_time(binding, 1.5)
    assert not binding_contains_media_time(binding, 3.5)


def test_open_ended_media_predicate_has_no_upper_bound() -> None:
    assert binding_contains_media_time(_binding(), 10_000.0)


def test_media_predicate_rejects_a_position_before_the_anchor() -> None:
    binding = _binding(media_anchor_seconds=3.0)
    assert not binding_contains_media_time(binding, 2.9)


# --- binding validation ------------------------------------------------------


def test_binding_for_another_lesson_is_refused() -> None:
    """A binding authored for one lesson must not silently synchronize another."""

    with pytest.raises(PresentationContractError, match="does not match lesson"):
        validate_media_timeline_binding(_binding(), lesson_id="ascending_scale")


def test_binding_naming_absent_media_is_refused() -> None:
    with pytest.raises(PresentationContractError, match="not present"):
        validate_media_timeline_binding(
            _binding(), lesson_id=LESSON, media_ids=["some-other-media"]
        )


def test_binding_matching_its_lesson_and_media_passes() -> None:
    validate_media_timeline_binding(
        _binding(), lesson_id=LESSON, media_ids=["demo-video", "intro-text"]
    )


def test_binding_validation_rejects_foreign_objects() -> None:
    with pytest.raises(PresentationContractError, match="MediaTimelineBindingV1"):
        validate_media_timeline_binding({"lesson_id": LESSON}, lesson_id=LESSON)  # type: ignore[arg-type]


# --- state builders ----------------------------------------------------------


def test_timeline_state_derives_ticks_from_seconds(constant_anchors) -> None:
    state = build_teaching_timeline_state(
        lesson_id=LESSON,
        sequence=1,
        position_seconds=1.5,
        anchors=constant_anchors,
        playing=True,
        playback_rate=1.0,
        repetition_index=0,
    )
    assert state.position_tick == 2880
    assert state.loop_enabled is False


def test_timeline_state_derives_loop_ticks(constant_anchors) -> None:
    state = build_teaching_timeline_state(
        lesson_id=LESSON,
        sequence=2,
        position_seconds=1.5,
        anchors=constant_anchors,
        playing=True,
        playback_rate=0.75,
        repetition_index=3,
        loop_start_seconds=1.0,
        loop_end_seconds=2.5,
    )
    assert (state.loop_start_tick, state.loop_end_tick) == (1920, 4800)
    assert state.loop_enabled is True


def test_half_a_loop_boundary_is_refused(constant_anchors) -> None:
    with pytest.raises(PresentationContractError, match="together"):
        build_teaching_timeline_state(
            lesson_id=LESSON,
            sequence=1,
            position_seconds=0.0,
            anchors=constant_anchors,
            playing=False,
            playback_rate=1.0,
            repetition_index=0,
            loop_start_seconds=1.0,
        )


def test_playhead_inherits_identity_and_position_from_the_timeline(constant_anchors) -> None:
    state = build_teaching_timeline_state(
        lesson_id=LESSON,
        sequence=7,
        position_seconds=1.5,
        anchors=constant_anchors,
        playing=True,
        playback_rate=1.0,
        repetition_index=2,
    )
    playhead = build_teaching_playhead_state(state, active_event_ids=["evt-1", "evt-2"])
    assert playhead.lesson_id == state.lesson_id
    assert playhead.sequence == state.sequence
    assert playhead.position_tick == state.position_tick
    assert playhead.repetition_index == state.repetition_index
    assert playhead.active_event_ids == ("evt-1", "evt-2")


def test_playback_rate_does_not_change_derived_position(constant_anchors) -> None:
    """Rate changes how fast time passes, not where a given second sits musically."""

    ticks = {
        rate: build_teaching_timeline_state(
            lesson_id=LESSON,
            sequence=1,
            position_seconds=1.5,
            anchors=constant_anchors,
            playing=True,
            playback_rate=rate,
            repetition_index=0,
        ).position_tick
        for rate in (0.5, 0.75, 1.0, 1.5)
    }
    assert len(set(ticks.values())) == 1


# --- degenerate-table guards -------------------------------------------------
#
# These paths only fire on tables a well-formed export cannot produce. They
# exist so a hand-authored or corrupted table degrades predictably instead of
# dividing by zero, and they are exercised here for exactly that reason.


def test_a_zero_duration_segment_resolves_to_its_lower_tick() -> None:
    """Two anchors at the same instant: no slope, so the earlier tick wins."""

    table = (
        TimelineAnchorV1(schema_version=V, tick=0, seconds=0.0),
        TimelineAnchorV1(schema_version=V, tick=960, seconds=0.0),
        TimelineAnchorV1(schema_version=V, tick=1920, seconds=1.0),
    )
    assert tick_at_seconds(table, 0.0) == 0
    assert tick_at_seconds(table, 0.5) == 1440


def test_extrapolating_past_a_flat_final_segment_returns_its_endpoint() -> None:
    table = (
        TimelineAnchorV1(schema_version=V, tick=0, seconds=0.0),
        TimelineAnchorV1(schema_version=V, tick=960, seconds=0.0),
    )
    assert seconds_at_tick(table, 5000) == 0.0
    assert tick_at_seconds(table, 5.0) == 960


def test_detached_binding_reverse_mapping_returns_nothing() -> None:
    binding = _binding(sync_mode=MediaSyncMode.DETACHED)
    assert media_time_to_lesson_time(binding, 1.0) is None


def test_reverse_mapping_outside_the_media_range_returns_nothing() -> None:
    binding = _binding(lesson_end_seconds=3.0, media_end_seconds=3.0)
    assert media_time_to_lesson_time(binding, 3.5) is None
    assert media_time_to_lesson_time(binding, 2.5) == pytest.approx(2.5)
