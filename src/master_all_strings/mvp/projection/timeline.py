"""Adapt Core musical timeline conversion for fretboard projection."""

from __future__ import annotations

from collections.abc import Sequence

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.score.musical_timeline import ticks_to_seconds
from master_all_strings.core.score.tempo import TempoChangeV1, tempo_from_bpm
from master_all_strings.mvp.errors import ProjectionBuildError
from master_all_strings.mvp.projection.models import (
    FretboardTimelineV1,
    TempoChangeProjectionV1,
)

__all__ = [
    "build_core_tempo_map",
    "build_projected_timeline",
    "event_time_bounds",
    "project_tempo_changes",
]

DEFAULT_SECONDS_PER_SCREEN = 4.0
DEFAULT_PLAY_LINE_FRACTION = 0.22


def build_core_tempo_map(
    *,
    tempo_override_bpm: float | None,
    source_tempo_changes: Sequence[tuple[int, float]],
) -> tuple[TempoChangeV1, ...]:
    """Build a Core tempo map. Tempo is required; never defaulted to 120 BPM."""

    if tempo_override_bpm is not None:
        return (tempo_from_bpm(tempo_override_bpm, tick=0),)
    if not source_tempo_changes:
        raise ProjectionBuildError(
            "lesson tempo is required for projection; refusing to assume a default tempo"
        )
    changes = tuple(tempo_from_bpm(bpm, tick=tick) for tick, bpm in source_tempo_changes)
    if changes[0].tick != 0:
        # Ensure tick 0 coverage using the earliest declared tempo value.
        earliest = min(changes, key=lambda item: item.tick)
        changes = (tempo_from_bpm(earliest.beats_per_minute, tick=0), *changes)
    return changes


def project_tempo_changes(
    tempo_map: Sequence[TempoChangeV1],
) -> tuple[TempoChangeProjectionV1, ...]:
    return tuple(
        TempoChangeProjectionV1(
            tick=change.tick,
            tempo_bpm=change.beats_per_minute,
            microseconds_per_quarter=change.microseconds_per_quarter,
        )
        for change in tempo_map
    )


def event_time_bounds(
    events: Sequence[MusicalEvent],
    *,
    ticks_per_quarter: int,
    tempo_map: Sequence[TempoChangeV1],
) -> list[tuple[float, float]]:
    bounds: list[tuple[float, float]] = []
    for event in events:
        onset = ticks_to_seconds(
            event.start_tick,
            ticks_per_quarter=ticks_per_quarter,
            tempo_changes=tempo_map,
        )
        release = ticks_to_seconds(
            event.start_tick + event.duration_ticks,
            ticks_per_quarter=ticks_per_quarter,
            tempo_changes=tempo_map,
        )
        bounds.append((onset, release))
    return bounds


def build_projected_timeline(
    events: Sequence[MusicalEvent],
    *,
    ticks_per_quarter: int,
    tempo_map: Sequence[TempoChangeV1],
    seconds_per_screen: float = DEFAULT_SECONDS_PER_SCREEN,
    play_line_fraction: float = DEFAULT_PLAY_LINE_FRACTION,
) -> FretboardTimelineV1:
    if not events:
        total_ticks = 0
        total_seconds = 0.0
    else:
        total_ticks = max(event.start_tick + event.duration_ticks for event in events)
        total_seconds = ticks_to_seconds(
            total_ticks,
            ticks_per_quarter=ticks_per_quarter,
            tempo_changes=tempo_map,
        )
    return FretboardTimelineV1(
        ticks_per_quarter=ticks_per_quarter,
        total_ticks=total_ticks,
        total_seconds=total_seconds,
        seconds_per_screen=seconds_per_screen,
        play_line_fraction=play_line_fraction,
    )
