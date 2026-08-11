"""Musical timeline conversion: ticks ↔ elapsed seconds under a tempo map.

This is the Core-owned authority for converting canonical musical ticks into
wall-clock elapsed seconds (and back) using a piecewise tempo map. Capture
nanosecond conversion remains in ``timing``; this module is for score/playback/
projection consumers that already work in the tick domain.

Tempo is never defaulted. A map that does not cover tick 0 is rejected rather
than silently assuming 120 BPM.
"""

from __future__ import annotations

from collections.abc import Sequence

from master_all_strings.core.score.errors import (
    ScoreContractError,
    require_nonnegative_int,
    require_positive_int,
)
from master_all_strings.core.score.rounding import divide_round_half_away_from_zero
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.core.score.timing import (
    MICROSECONDS_PER_SECOND,
    require_convertible_tempo,
)

__all__ = [
    "SECONDS_PER_MICROSECOND",
    "normalize_tempo_map",
    "seconds_to_ticks",
    "ticks_to_microseconds",
    "ticks_to_seconds",
]

SECONDS_PER_MICROSECOND = 1.0 / MICROSECONDS_PER_SECOND


def normalize_tempo_map(tempo_changes: Sequence[TempoChangeV1]) -> tuple[TempoChangeV1, ...]:
    """Validate and return a sorted, deduplicated tempo map covering tick 0.

    When multiple changes share a tick, the last one in input order wins (MIDI
    convention for same-tick meta events). The earliest resulting change must
    start at tick 0; otherwise conversion would invent a leading tempo.
    """

    if not tempo_changes:
        raise ScoreContractError(
            "tempo map is required for musical timeline conversion; "
            "refusing to assume a default tempo"
        )
    for change in tempo_changes:
        if not isinstance(change, TempoChangeV1):
            raise ScoreContractError("tempo_changes must contain TempoChangeV1 values")
        require_convertible_tempo(change.microseconds_per_quarter)

    # Last-writer-wins per tick, then sort ascending.
    by_tick: dict[int, TempoChangeV1] = {}
    for change in tempo_changes:
        by_tick[change.tick] = change
    ordered = tuple(by_tick[tick] for tick in sorted(by_tick))
    if ordered[0].tick != 0:
        raise ScoreContractError(
            "tempo map must include a tempo at tick 0; refusing to invent a leading tempo"
        )
    return ordered


def _segment_microseconds(tick_delta: int, *, ticks_per_quarter: int, mpq: int) -> int:
    """Elapsed microseconds for ``tick_delta`` ticks at a constant tempo."""

    require_nonnegative_int(tick_delta, "tick_delta")
    # us = ticks * mpq / ppq
    return divide_round_half_away_from_zero(tick_delta * mpq, ticks_per_quarter)


def ticks_to_microseconds(
    tick: int,
    *,
    ticks_per_quarter: int,
    tempo_changes: Sequence[TempoChangeV1],
) -> int:
    """Convert an absolute tick position to elapsed microseconds from tick 0."""

    require_nonnegative_int(tick, "tick")
    require_positive_int(ticks_per_quarter, "ticks_per_quarter")
    tempo_map = normalize_tempo_map(tempo_changes)

    elapsed = 0
    for index, change in enumerate(tempo_map):
        next_tick = tempo_map[index + 1].tick if index + 1 < len(tempo_map) else None
        segment_end = tick if next_tick is None else min(tick, next_tick)
        if segment_end > change.tick:
            elapsed += _segment_microseconds(
                segment_end - change.tick,
                ticks_per_quarter=ticks_per_quarter,
                mpq=change.microseconds_per_quarter,
            )
        if next_tick is None or tick <= next_tick:
            break
    return elapsed


def ticks_to_seconds(
    tick: int,
    *,
    ticks_per_quarter: int,
    tempo_changes: Sequence[TempoChangeV1],
) -> float:
    """Convert an absolute tick position to elapsed seconds from tick 0."""

    microseconds = ticks_to_microseconds(
        tick,
        ticks_per_quarter=ticks_per_quarter,
        tempo_changes=tempo_changes,
    )
    return microseconds * SECONDS_PER_MICROSECOND


def seconds_to_ticks(
    seconds: float,
    *,
    ticks_per_quarter: int,
    tempo_changes: Sequence[TempoChangeV1],
) -> int:
    """Convert elapsed seconds from tick 0 into the nearest tick (half away from zero).

    Negative elapsed time is rejected. Times beyond the last tempo-map breakpoint
    continue at the final tempo. Float seconds are converted through integer
    microseconds so the same half-away-from-zero rule used elsewhere applies.
    """

    from fractions import Fraction

    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise ScoreContractError("seconds must be a finite number")
    if seconds != seconds or seconds in (float("inf"), float("-inf")):  # noqa: PLR0124
        raise ScoreContractError("seconds must be a finite number")
    if seconds < 0:
        raise ScoreContractError("seconds must not be negative")
    require_positive_int(ticks_per_quarter, "ticks_per_quarter")
    tempo_map = normalize_tempo_map(tempo_changes)

    exact_us = Fraction(seconds) * MICROSECONDS_PER_SECOND
    remaining = divide_round_half_away_from_zero(exact_us.numerator, exact_us.denominator)

    for index, change in enumerate(tempo_map):
        next_tick = tempo_map[index + 1].tick if index + 1 < len(tempo_map) else None
        mpq = change.microseconds_per_quarter
        if next_tick is None:
            return change.tick + divide_round_half_away_from_zero(
                remaining * ticks_per_quarter, mpq
            )
        segment_ticks = next_tick - change.tick
        segment_us = _segment_microseconds(
            segment_ticks,
            ticks_per_quarter=ticks_per_quarter,
            mpq=mpq,
        )
        if remaining <= segment_us:
            return change.tick + divide_round_half_away_from_zero(
                remaining * ticks_per_quarter, mpq
            )
        remaining -= segment_us
    raise ScoreContractError("unreachable tempo map walk")  # pragma: no cover
