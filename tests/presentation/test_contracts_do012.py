"""DO-012 presentation contract validation.

These records are derived presentation state. The invariants worth testing are
the ones that stop a follower from claiming something it does not know: a loop
without bounds, a health status without its measurement, a binding that quietly
implies time warping.
"""

from __future__ import annotations

import pytest

from master_all_strings.presentation.contracts import (
    PRESENTATION_SCHEMA_VERSION,
    MediaSyncMode,
    MediaTimelineBindingV1,
    SyncCorrection,
    SynchronizationHealthV1,
    SynchronizationStatus,
    TeachingPlayheadStateV1,
    TeachingTimelineStateV1,
    TimelineAnchorV1,
)
from master_all_strings.presentation.errors import PresentationContractError

V = PRESENTATION_SCHEMA_VERSION
LESSON = "half_steps_one_string"


def _timeline(**overrides: object) -> TeachingTimelineStateV1:
    base: dict[str, object] = {
        "schema_version": V,
        "lesson_id": LESSON,
        "sequence": 1,
        "position_tick": 960,
        "position_seconds": 0.5,
        "playing": True,
        "playback_rate": 1.0,
        "loop_enabled": False,
        "repetition_index": 0,
    }
    base.update(overrides)
    return TeachingTimelineStateV1(**base)  # type: ignore[arg-type]


def _health(**overrides: object) -> SynchronizationHealthV1:
    base: dict[str, object] = {
        "schema_version": V,
        "follower_id": "media:demo",
        "sequence": 1,
        "status": SynchronizationStatus.DETACHED,
    }
    base.update(overrides)
    return SynchronizationHealthV1(**base)  # type: ignore[arg-type]


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


# --- TimelineAnchorV1 --------------------------------------------------------


def test_anchor_accepts_origin() -> None:
    anchor = TimelineAnchorV1(schema_version=V, tick=0, seconds=0.0)
    assert (anchor.tick, anchor.seconds) == (0, 0.0)


@pytest.mark.parametrize(
    ("field", "value"),
    [("tick", -1), ("seconds", -0.1), ("tick", True), ("seconds", float("nan"))],
)
def test_anchor_rejects_impossible_values(field: str, value: object) -> None:
    kwargs: dict[str, object] = {"schema_version": V, "tick": 0, "seconds": 0.0}
    kwargs[field] = value
    with pytest.raises(PresentationContractError):
        TimelineAnchorV1(**kwargs)  # type: ignore[arg-type]


def test_anchor_rejects_wrong_schema_version() -> None:
    with pytest.raises(PresentationContractError):
        TimelineAnchorV1(schema_version="2.0.0", tick=0, seconds=0.0)


# --- TeachingTimelineStateV1 -------------------------------------------------


def test_timeline_state_without_loop_is_valid() -> None:
    assert _timeline().loop_enabled is False


def test_timeline_state_with_complete_loop_is_valid() -> None:
    state = _timeline(
        loop_enabled=True,
        loop_start_tick=0,
        loop_end_tick=1920,
        loop_start_seconds=0.0,
        loop_end_seconds=1.0,
    )
    assert state.loop_end_tick == 1920


def test_enabled_loop_without_bounds_is_rejected() -> None:
    """An enabled loop with no bounds would let a follower invent its own range."""

    with pytest.raises(PresentationContractError, match="loop_enabled requires"):
        _timeline(loop_enabled=True)


def test_disabled_loop_with_stale_bounds_is_rejected() -> None:
    """Stale bounds beside loop_enabled=false read as an active loop to a follower."""

    with pytest.raises(PresentationContractError, match="must be absent"):
        _timeline(
            loop_enabled=False,
            loop_start_tick=0,
            loop_end_tick=1920,
            loop_start_seconds=0.0,
            loop_end_seconds=1.0,
        )


def test_inverted_loop_ticks_are_rejected() -> None:
    with pytest.raises(PresentationContractError, match="loop_end_tick"):
        _timeline(
            loop_enabled=True,
            loop_start_tick=1920,
            loop_end_tick=960,
            loop_start_seconds=0.0,
            loop_end_seconds=1.0,
        )


def test_inverted_loop_seconds_are_rejected() -> None:
    with pytest.raises(PresentationContractError, match="loop_end_seconds"):
        _timeline(
            loop_enabled=True,
            loop_start_tick=0,
            loop_end_tick=1920,
            loop_start_seconds=1.0,
            loop_end_seconds=0.5,
        )


@pytest.mark.parametrize("rate", [0.0, -1.0])
def test_nonpositive_playback_rate_is_rejected(rate: float) -> None:
    with pytest.raises(PresentationContractError, match="playback_rate"):
        _timeline(playback_rate=rate)


@pytest.mark.parametrize("field", ["playing", "loop_enabled"])
def test_boolean_fields_reject_non_booleans(field: str) -> None:
    with pytest.raises(PresentationContractError, match="boolean"):
        _timeline(**{field: "yes"})


def test_blank_lesson_id_is_rejected() -> None:
    with pytest.raises(PresentationContractError, match="lesson_id"):
        _timeline(lesson_id="   ")


def test_padded_lesson_id_is_rejected() -> None:
    with pytest.raises(PresentationContractError, match="whitespace"):
        _timeline(lesson_id=" lesson ")


def test_negative_sequence_is_rejected() -> None:
    with pytest.raises(PresentationContractError, match="sequence"):
        _timeline(sequence=-1)


# --- TeachingPlayheadStateV1 -------------------------------------------------


def test_playhead_carries_projection_event_ids() -> None:
    playhead = TeachingPlayheadStateV1(
        schema_version=V,
        lesson_id=LESSON,
        sequence=3,
        position_tick=960,
        position_seconds=0.5,
        active_event_ids=("evt-1", "evt-2"),
        repetition_index=1,
    )
    assert playhead.active_event_ids == ("evt-1", "evt-2")


def test_playhead_with_no_active_events_is_valid() -> None:
    """Silence between notes is a real playhead state, not an error."""

    playhead = TeachingPlayheadStateV1(
        schema_version=V,
        lesson_id=LESSON,
        sequence=0,
        position_tick=0,
        position_seconds=0.0,
        active_event_ids=(),
        repetition_index=0,
    )
    assert playhead.active_event_ids == ()


def test_playhead_rejects_duplicate_event_ids() -> None:
    with pytest.raises(PresentationContractError, match="unique"):
        TeachingPlayheadStateV1(
            schema_version=V,
            lesson_id=LESSON,
            sequence=0,
            position_tick=0,
            position_seconds=0.0,
            active_event_ids=("evt-1", "evt-1"),
            repetition_index=0,
        )


def test_playhead_rejects_list_instead_of_tuple() -> None:
    with pytest.raises(PresentationContractError, match="tuple"):
        TeachingPlayheadStateV1(
            schema_version=V,
            lesson_id=LESSON,
            sequence=0,
            position_tick=0,
            position_seconds=0.0,
            active_event_ids=["evt-1"],  # type: ignore[arg-type]
            repetition_index=0,
        )


def test_playhead_rejects_blank_event_id() -> None:
    with pytest.raises(PresentationContractError, match="active_event_ids entry"):
        TeachingPlayheadStateV1(
            schema_version=V,
            lesson_id=LESSON,
            sequence=0,
            position_tick=0,
            position_seconds=0.0,
            active_event_ids=("",),
            repetition_index=0,
        )


def test_playhead_carries_no_canonical_revision_id() -> None:
    """DO-012 must not anticipate DO-013's revision authority."""

    from dataclasses import fields

    names = {f.name for f in fields(TeachingPlayheadStateV1)}
    assert "canonical_revision_id" not in names


# --- MediaTimelineBindingV1 --------------------------------------------------


def test_open_ended_binding_is_valid() -> None:
    assert _binding().lesson_end_seconds is None


def test_bounded_binding_with_matching_spans_is_valid() -> None:
    binding = _binding(lesson_end_seconds=3.0, media_end_seconds=3.0)
    assert binding.media_end_seconds == 3.0


def test_offset_binding_with_matching_spans_is_valid() -> None:
    binding = _binding(
        lesson_anchor_seconds=10.0,
        media_anchor_seconds=3.0,
        lesson_end_seconds=14.0,
        media_end_seconds=7.0,
    )
    assert binding.lesson_anchor_seconds == 10.0


def test_unequal_spans_are_rejected_as_time_warping() -> None:
    """A 4.5 s lesson span mapped onto 3.0 s of media is a rate change V1 will not do."""

    with pytest.raises(PresentationContractError, match="time warping"):
        _binding(lesson_end_seconds=4.5, media_end_seconds=3.0)


def test_lesson_end_before_anchor_is_rejected() -> None:
    with pytest.raises(PresentationContractError, match="lesson_end_seconds"):
        _binding(lesson_anchor_seconds=2.0, lesson_end_seconds=1.0)


def test_media_end_before_anchor_is_rejected() -> None:
    with pytest.raises(PresentationContractError, match="media_end_seconds"):
        _binding(media_anchor_seconds=2.0, media_end_seconds=1.0)


def test_unknown_sync_mode_is_rejected() -> None:
    with pytest.raises(PresentationContractError, match="sync_mode"):
        _binding(sync_mode="elastic")


def test_sync_mode_accepts_its_string_form() -> None:
    assert _binding(sync_mode="detached").sync_mode is MediaSyncMode.DETACHED


def test_non_string_sync_mode_is_rejected() -> None:
    with pytest.raises(PresentationContractError, match="sync_mode"):
        _binding(sync_mode=3)


# --- SynchronizationHealthV1 -------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        SynchronizationStatus.DEGRADED,
        SynchronizationStatus.DETACHED,
        SynchronizationStatus.UNAVAILABLE,
        SynchronizationStatus.OUT_OF_BINDING_RANGE,
    ],
)
def test_unmeasurable_statuses_carry_no_drift(status: SynchronizationStatus) -> None:
    assert _health(status=status).drift_ms is None


@pytest.mark.parametrize(
    "status",
    [
        SynchronizationStatus.DEGRADED,
        SynchronizationStatus.DETACHED,
        SynchronizationStatus.UNAVAILABLE,
        SynchronizationStatus.OUT_OF_BINDING_RANGE,
    ],
)
def test_unmeasurable_status_with_drift_is_rejected(status: SynchronizationStatus) -> None:
    """Reporting zero drift for something you could not measure is a false claim."""

    with pytest.raises(PresentationContractError, match="drift_ms must be absent"):
        _health(status=status, drift_ms=0.0)


def test_measured_status_requires_its_measurement() -> None:
    with pytest.raises(PresentationContractError, match="requires expected_time_seconds"):
        _health(status=SynchronizationStatus.SYNCED)


def test_measured_status_rejects_inconsistent_drift() -> None:
    """A record must not claim a drift its own timestamps contradict."""

    with pytest.raises(PresentationContractError, match="drift_ms must equal"):
        _health(
            status=SynchronizationStatus.SYNCED,
            expected_time_seconds=1.0,
            actual_time_seconds=1.02,
            drift_ms=0.0,
        )


def test_measured_status_accepts_consistent_drift() -> None:
    health = _health(
        status=SynchronizationStatus.SYNCED,
        expected_time_seconds=1.0,
        actual_time_seconds=1.02,
        drift_ms=20.0,
        last_correction=SyncCorrection.NONE,
    )
    assert health.last_correction is SyncCorrection.NONE


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(PresentationContractError, match="status"):
        _health(status="confused")


def test_unknown_correction_is_rejected() -> None:
    with pytest.raises(PresentationContractError, match="last_correction"):
        _health(last_correction="teleport")


def test_non_finite_times_are_rejected() -> None:
    with pytest.raises(PresentationContractError, match="expected_time_seconds"):
        _health(
            status=SynchronizationStatus.SYNCED,
            expected_time_seconds=float("inf"),
            actual_time_seconds=1.0,
            drift_ms=0.0,
        )


def test_non_finite_drift_is_rejected() -> None:
    with pytest.raises(PresentationContractError, match="drift_ms"):
        _health(
            status=SynchronizationStatus.SYNCED,
            expected_time_seconds=1.0,
            actual_time_seconds=1.0,
            drift_ms=float("nan"),
        )


def test_blank_follower_id_is_rejected() -> None:
    with pytest.raises(PresentationContractError, match="follower_id"):
        _health(follower_id="")


def test_optional_identifier_validator_accepts_none_and_rejects_blanks() -> None:
    from master_all_strings.presentation.errors import require_optional_identifier

    require_optional_identifier(None, "field")
    require_optional_identifier("ok", "field")
    with pytest.raises(PresentationContractError, match="field"):
        require_optional_identifier("  ", "field")


def test_number_validator_rejects_non_numbers_before_checking_finiteness() -> None:
    from master_all_strings.presentation.errors import require_finite_number

    with pytest.raises(PresentationContractError, match="must be a number"):
        require_finite_number("1.0", "field")
    with pytest.raises(PresentationContractError, match="must be a number"):
        require_finite_number(True, "field")
