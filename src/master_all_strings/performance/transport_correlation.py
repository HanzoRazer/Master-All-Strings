"""Map capture-clock observations through explicit practice transport anchors."""

from __future__ import annotations

from dataclasses import dataclass, replace

from master_all_strings.core.score.musical_timeline import seconds_to_ticks
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.performance.contracts.errors import (
    PerformanceContractError,
    require_nonnegative_int,
    require_positive_int,
)
from master_all_strings.performance.contracts.live_midi import ObservedMidiNoteV1


@dataclass(frozen=True)
class PracticeTransportAnchorV1:
    capture_time_ns: int
    practice_position_seconds: float
    playback_rate: float
    repetition_index: int
    playing: bool

    def __post_init__(self) -> None:
        require_nonnegative_int(self.capture_time_ns, "capture_time_ns")
        require_nonnegative_int(self.repetition_index, "repetition_index")
        if self.practice_position_seconds < 0:
            raise PerformanceContractError("practice_position_seconds must be nonnegative")
        if self.playback_rate not in (0.5, 0.75, 1.0, 1.5):
            raise PerformanceContractError("playback_rate is unsupported")


def locate_observed_notes(
    notes: tuple[ObservedMidiNoteV1, ...],
    anchors: tuple[PracticeTransportAnchorV1, ...],
    *,
    ticks_per_quarter: int,
    tempo_changes: tuple[TempoChangeV1, ...],
) -> tuple[ObservedMidiNoteV1, ...]:
    require_positive_int(ticks_per_quarter, "ticks_per_quarter")
    if not anchors:
        raise PerformanceContractError("transport anchors must not be empty")
    ordered = tuple(sorted(anchors, key=lambda item: item.capture_time_ns))
    located = []
    for note in notes:
        eligible = [a for a in ordered if a.capture_time_ns <= note.note_on_time_ns]
        if not eligible:
            raise PerformanceContractError("observation precedes every transport anchor")
        anchor = eligible[-1]
        elapsed = (note.note_on_time_ns - anchor.capture_time_ns) / 1_000_000_000
        position = anchor.practice_position_seconds
        if anchor.playing:
            position += elapsed * anchor.playback_rate
        located.append(
            replace(
                note,
                repetition_index=anchor.repetition_index,
                practice_onset_seconds=position,
                estimated_start_tick=seconds_to_ticks(
                    position,
                    ticks_per_quarter=ticks_per_quarter,
                    tempo_changes=tempo_changes,
                ),
            )
        )
    return tuple(located)
