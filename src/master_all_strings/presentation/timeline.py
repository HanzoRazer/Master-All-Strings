"""Deterministic timeline mapping for presentation followers (DO-012).

Pure functions only: no browser APIs, no media elements, no wall clock. Every
value here is derived from Musical Core timing or from an explicit binding.

The load-bearing idea is the **anchor table**. Musical Core owns tick-to-second
conversion (``core.score.musical_timeline.ticks_to_seconds``). Reimplementing it
in JavaScript would create a second canonical timing authority that could drift
from the first, so instead this module emits the mapping as a small table of
(tick, seconds) pairs at every tempo boundary. Between two consecutive anchors
the tempo is constant by construction, so linear interpolation *reproduces* the
Core mapping rather than approximating it, and the browser never needs to know
what a tempo is.
"""

from __future__ import annotations

from collections.abc import Sequence

from master_all_strings.core.score.musical_timeline import (
    normalize_tempo_map,
    ticks_to_seconds,
)
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.presentation.contracts import (
    PRESENTATION_SCHEMA_VERSION,
    MediaSyncMode,
    MediaTimelineBindingV1,
    TeachingPlayheadStateV1,
    TeachingTimelineStateV1,
    TimelineAnchorV1,
)
from master_all_strings.presentation.errors import (
    PresentationContractError,
    require_finite_number,
    require_identifier,
    require_nonnegative_int,
    require_nonnegative_number,
)

__all__ = [
    "anchors_to_payload",
    "binding_contains_lesson_time",
    "binding_contains_media_time",
    "build_teaching_playhead_state",
    "build_teaching_timeline_state",
    "build_timeline_anchors",
    "lesson_time_to_media_time",
    "media_time_to_lesson_time",
    "resolve_focus_range_seconds",
    "seconds_to_tick_from_anchors",
    "tick_to_seconds_from_anchors",
    "validate_media_timeline_binding",
    "validate_timeline_anchors",
]


def build_timeline_anchors(
    *,
    ticks_per_quarter: int,
    tempo_changes: Sequence[TempoChangeV1],
    total_ticks: int,
) -> tuple[TimelineAnchorV1, ...]:
    """Emit the Core-authored tick-to-second mapping as interpolatable anchors.

    An anchor is placed at tick 0, at every tempo-change boundary, and at
    ``total_ticks``. Those are exactly the points where the slope of the mapping
    can change, so the piecewise-linear function through them is the mapping.

    Tempo changes beyond ``total_ticks`` are still anchored: a lesson may be
    seeked or looped up to its declared end, and dropping a boundary inside that
    range would bend the interpolation across a tempo it should have honored.
    """

    require_nonnegative_int(total_ticks, "total_ticks")
    if isinstance(ticks_per_quarter, bool) or not isinstance(ticks_per_quarter, int):
        raise PresentationContractError("ticks_per_quarter must be an integer")
    if ticks_per_quarter <= 0:
        raise PresentationContractError("ticks_per_quarter must be positive")

    # normalize_tempo_map enforces "starts at tick 0, sorted, deduplicated" and
    # raises rather than inventing a leading tempo.
    tempo_map = normalize_tempo_map(tempo_changes)

    ticks = {0, total_ticks}
    ticks.update(change.tick for change in tempo_map if change.tick <= total_ticks)

    return tuple(
        TimelineAnchorV1(
            schema_version=PRESENTATION_SCHEMA_VERSION,
            tick=tick,
            seconds=ticks_to_seconds(
                tick,
                ticks_per_quarter=ticks_per_quarter,
                tempo_changes=tempo_map,
            ),
        )
        for tick in sorted(ticks)
    )


def anchors_to_payload(
    anchors: Sequence[TimelineAnchorV1],
) -> list[dict[str, float | int]]:
    """Render anchors as the plain JSON shape the static export carries."""

    return [{"tick": anchor.tick, "seconds": anchor.seconds} for anchor in anchors]


def validate_timeline_anchors(
    anchors: Sequence[TimelineAnchorV1],
) -> tuple[TimelineAnchorV1, ...]:
    """Validate an anchor table and return it as a tuple.

    A table must begin at tick 0, increase strictly in ticks, and never move
    backwards in seconds. Anything else makes interpolation ambiguous, and an
    ambiguous musical mapping is worse than a refused one.
    """

    if not anchors:
        raise PresentationContractError("anchor table must not be empty")
    table = tuple(anchors)
    for anchor in table:
        if not isinstance(anchor, TimelineAnchorV1):
            raise PresentationContractError("anchor table must contain TimelineAnchorV1 values")
    if table[0].tick != 0:
        raise PresentationContractError("anchor table must begin at tick 0")
    previous = table[0]
    for anchor in table[1:]:
        # Strictly increasing in ticks, non-decreasing in seconds: a table that
        # went backwards in either axis would make interpolation ambiguous.
        if anchor.tick <= previous.tick:
            raise PresentationContractError("anchor ticks must be strictly increasing")
        if anchor.seconds < previous.seconds:
            raise PresentationContractError("anchor seconds must be non-decreasing")
        previous = anchor
    return table


def tick_to_seconds_from_anchors(anchors: Sequence[TimelineAnchorV1], tick: int) -> float:
    """Interpolate seconds for ``tick`` within the anchor table.

    This is the Python reference for the browser's interpolation. Positions past
    the last anchor continue at the final segment's rate, matching how Musical
    Core continues at the last declared tempo.
    """

    table = validate_timeline_anchors(anchors)
    require_nonnegative_int(tick, "tick")

    if tick <= table[0].tick:
        return table[0].seconds
    for index in range(len(table) - 1):
        lower, upper = table[index], table[index + 1]
        if tick <= upper.tick:
            return _interpolate(
                tick, lower.tick, upper.tick, lower.seconds, upper.seconds
            )
    return _extrapolate_seconds(table, tick)


def seconds_to_tick_from_anchors(anchors: Sequence[TimelineAnchorV1], seconds: float) -> int:
    """Interpolate the tick at ``seconds``, rounding half away from zero.

    The inverse of :func:`seconds_at_tick` over the same table. A segment with
    zero elapsed seconds (possible only for a degenerate table) resolves to its
    lower tick rather than dividing by zero.
    """

    table = validate_timeline_anchors(anchors)
    require_nonnegative_number(seconds, "seconds")

    if seconds <= table[0].seconds:
        return table[0].tick
    for index in range(len(table) - 1):
        lower, upper = table[index], table[index + 1]
        if seconds <= upper.seconds:
            if upper.seconds == lower.seconds:  # pragma: no cover - defensive
                # Unreachable for a well-formed table: a flat segment can only be
                # selected when `seconds` equals its value, and that case is
                # already answered by the early return or by an earlier segment.
                # Kept so a hand-authored table degrades instead of dividing by zero.
                return lower.tick
            ticks = _interpolate(
                seconds, lower.seconds, upper.seconds, float(lower.tick), float(upper.tick)
            )
            return _round_half_away_from_zero(ticks)
    return _extrapolate_ticks(table, seconds)


def _interpolate(
    value: float,
    lower_in: float,
    upper_in: float,
    lower_out: float,
    upper_out: float,
) -> float:
    if upper_in == lower_in:  # pragma: no cover - defensive
        # Callers guard against a zero-width input span before calling.
        return lower_out
    ratio = (float(value) - float(lower_in)) / (float(upper_in) - float(lower_in))
    return float(lower_out) + ratio * (float(upper_out) - float(lower_out))


def _final_segment(
    table: tuple[TimelineAnchorV1, ...],
) -> tuple[TimelineAnchorV1, TimelineAnchorV1]:
    if len(table) < 2:
        # A single-anchor table has no slope; treat it as its own segment so
        # extrapolation degenerates to the anchor value instead of failing.
        return table[0], table[0]
    return table[-2], table[-1]


def _extrapolate_seconds(table: tuple[TimelineAnchorV1, ...], tick: int) -> float:
    lower, upper = _final_segment(table)
    if upper.tick == lower.tick:
        return upper.seconds
    rate = (upper.seconds - lower.seconds) / (upper.tick - lower.tick)
    return upper.seconds + (tick - upper.tick) * rate


def _extrapolate_ticks(table: tuple[TimelineAnchorV1, ...], seconds: float) -> int:
    lower, upper = _final_segment(table)
    if upper.seconds == lower.seconds or upper.tick == lower.tick:
        return upper.tick
    rate = (upper.tick - lower.tick) / (upper.seconds - lower.seconds)
    return _round_half_away_from_zero(upper.tick + (float(seconds) - upper.seconds) * rate)


def _round_half_away_from_zero(value: float) -> int:
    """Match the rounding rule Musical Core uses, rather than banker's rounding."""

    if value >= 0:
        return int(value + 0.5)
    # pragma: no cover - Python never sees a negative here (ticks and seconds are
    # validated nonnegative), but the JavaScript mirror does, and the two
    # implementations must stay arithmetically identical.
    return -int(-value + 0.5)  # pragma: no cover


def resolve_focus_range_seconds(
    anchors: Sequence[TimelineAnchorV1],
    *,
    start_tick: int,
    end_tick: int,
) -> tuple[float, float]:
    """Convert an Educational focus range into shared-transport loop seconds.

    The ticks come from ``PracticeNextActionV1``; they are already authoritative.
    This only changes their unit so the existing ``Transport.setLoop`` can accept
    them. It does not widen, snap, or reinterpret the range.
    """

    require_nonnegative_int(start_tick, "start_tick")
    require_nonnegative_int(end_tick, "end_tick")
    if end_tick <= start_tick:
        raise PresentationContractError("end_tick must exceed start_tick")
    return (
        tick_to_seconds_from_anchors(anchors, start_tick),
        tick_to_seconds_from_anchors(anchors, end_tick),
    )


def validate_media_timeline_binding(
    binding: MediaTimelineBindingV1,
    *,
    lesson_id: str,
    media_ids: Sequence[str] | None = None,
) -> None:
    """Check a binding against the lesson and media it claims to describe.

    Construction already enforces the binding's internal shape. This checks the
    binding against its context, so a binding authored for one lesson cannot
    silently synchronize another.
    """

    if not isinstance(binding, MediaTimelineBindingV1):
        raise PresentationContractError("expected MediaTimelineBindingV1")
    require_identifier(lesson_id, "lesson_id")
    if binding.lesson_id != lesson_id:
        raise PresentationContractError(
            f"binding lesson_id {binding.lesson_id!r} does not match lesson {lesson_id!r}"
        )
    if media_ids is not None and binding.media_id not in set(media_ids):
        raise PresentationContractError(
            f"binding media_id {binding.media_id!r} is not present in the lesson media set"
        )


def binding_contains_lesson_time(
    binding: MediaTimelineBindingV1, lesson_seconds: float
) -> bool:
    """Whether the binding claims to map this lesson position."""

    require_finite_number(lesson_seconds, "lesson_seconds")
    if float(lesson_seconds) < float(binding.lesson_anchor_seconds):
        return False
    if binding.lesson_end_seconds is None:
        return True
    return float(lesson_seconds) <= float(binding.lesson_end_seconds)


def binding_contains_media_time(binding: MediaTimelineBindingV1, media_seconds: float) -> bool:
    """Whether the binding claims to map this media position."""

    require_finite_number(media_seconds, "media_seconds")
    if float(media_seconds) < float(binding.media_anchor_seconds):
        return False
    if binding.media_end_seconds is None:
        return True
    return float(media_seconds) <= float(binding.media_end_seconds)


def lesson_time_to_media_time(
    binding: MediaTimelineBindingV1, lesson_seconds: float
) -> float | None:
    """Map lesson time to media time, or ``None`` outside the binding range.

    ``None`` is the explicit out-of-range answer. Returning an extrapolated
    number instead would let a follower seek a media element to a position the
    binding never claimed, which is how the golden lesson's 3.0 s clip would
    otherwise appear to keep playing through a 4.5 s lesson.
    """

    if binding.sync_mode is not MediaSyncMode.SYNCHRONIZED:
        return None
    if not binding_contains_lesson_time(binding, lesson_seconds):
        return None
    offset = float(lesson_seconds) - float(binding.lesson_anchor_seconds)
    media_seconds = float(binding.media_anchor_seconds) + offset
    # The two ends are independently optional, so a binding may declare where the
    # media stops without declaring where the lesson stops. Checking only the
    # lesson end would then hand back a position past the media end -- exactly the
    # 3.0 s clip answering for a 4.5 s lesson this function exists to refuse.
    if not binding_contains_media_time(binding, media_seconds):
        return None
    return media_seconds


def media_time_to_lesson_time(
    binding: MediaTimelineBindingV1, media_seconds: float
) -> float | None:
    """Map media time back to lesson time, or ``None`` outside the range."""

    if binding.sync_mode is not MediaSyncMode.SYNCHRONIZED:
        return None
    if not binding_contains_media_time(binding, media_seconds):
        return None
    offset = float(media_seconds) - float(binding.media_anchor_seconds)
    lesson_seconds = float(binding.lesson_anchor_seconds) + offset
    # Symmetrical to the forward direction: honor whichever end is declared.
    if not binding_contains_lesson_time(binding, lesson_seconds):
        return None
    return lesson_seconds


def build_teaching_timeline_state(
    *,
    lesson_id: str,
    sequence: int,
    position_seconds: float,
    anchors: Sequence[TimelineAnchorV1],
    playing: bool,
    playback_rate: float,
    repetition_index: int,
    loop_start_seconds: float | None = None,
    loop_end_seconds: float | None = None,
) -> TeachingTimelineStateV1:
    """Derive a timeline snapshot from a transport position plus anchors.

    Loop bounds arrive in seconds because that is the unit the shared transport
    speaks; their tick equivalents are derived here so followers that think in
    ticks do not have to convert.
    """

    loop_enabled = loop_start_seconds is not None and loop_end_seconds is not None
    if (loop_start_seconds is None) != (loop_end_seconds is None):
        raise PresentationContractError(
            "loop_start_seconds and loop_end_seconds must be provided together"
        )

    return TeachingTimelineStateV1(
        schema_version=PRESENTATION_SCHEMA_VERSION,
        lesson_id=lesson_id,
        sequence=sequence,
        position_tick=seconds_to_tick_from_anchors(anchors, position_seconds),
        position_seconds=float(position_seconds),
        playing=playing,
        playback_rate=float(playback_rate),
        loop_enabled=loop_enabled,
        repetition_index=repetition_index,
        loop_start_tick=(
            seconds_to_tick_from_anchors(anchors, loop_start_seconds)
            if loop_start_seconds is not None
            else None
        ),
        loop_end_tick=(
            seconds_to_tick_from_anchors(anchors, loop_end_seconds)
            if loop_end_seconds is not None
            else None
        ),
        loop_start_seconds=float(loop_start_seconds) if loop_start_seconds is not None else None,
        loop_end_seconds=float(loop_end_seconds) if loop_end_seconds is not None else None,
    )


def build_teaching_playhead_state(
    state: TeachingTimelineStateV1,
    *,
    active_event_ids: Sequence[str],
) -> TeachingPlayheadStateV1:
    """Project a timeline snapshot into the score-agnostic playhead.

    ``active_event_ids`` are supplied by whoever knows which events are sounding
    (today the fretboard projection; tomorrow TAB and notation too). This
    function never derives event identity itself.
    """

    return TeachingPlayheadStateV1(
        schema_version=PRESENTATION_SCHEMA_VERSION,
        lesson_id=state.lesson_id,
        sequence=state.sequence,
        position_tick=state.position_tick,
        position_seconds=state.position_seconds,
        active_event_ids=tuple(active_event_ids),
        repetition_index=state.repetition_index,
    )
