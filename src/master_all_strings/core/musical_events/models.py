"""Canonical musical event models."""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.core.foundation import (
    require_finite,
    require_index,
    require_midi_note,
    require_non_empty,
)


@dataclass(frozen=True)
class MusicalEvent:
    """A canonical pitch event independent of any instrument representation."""

    event_id: str
    midi_note: int
    start_tick: int
    duration_ticks: int
    velocity: int = 64
    cents_offset: float = 0.0
    voice_id: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.event_id, "event_id")
        require_midi_note(self.midi_note, "midi_note")
        require_index(self.start_tick, "start_tick")
        if isinstance(self.duration_ticks, bool) or not isinstance(self.duration_ticks, int):
            raise ValueError("duration_ticks must be an integer")
        if self.duration_ticks <= 0:
            raise ValueError("duration_ticks must be positive")
        if (
            isinstance(self.velocity, bool)
            or not isinstance(self.velocity, int)
            or not 0 <= self.velocity <= 127
        ):
            raise ValueError("velocity must be an integer between 0 and 127")
        require_finite(self.cents_offset, "cents_offset")
        if self.voice_id is not None:
            require_non_empty(self.voice_id, "voice_id")
