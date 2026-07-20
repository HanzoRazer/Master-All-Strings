"""Canonical musical event models."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


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
        if not self.event_id:
            msg = "event_id must not be empty"
            raise ValueError(msg)
        if not 0 <= self.midi_note <= 127:
            msg = "midi_note must be between 0 and 127"
            raise ValueError(msg)
        if self.start_tick < 0:
            msg = "start_tick must be nonnegative"
            raise ValueError(msg)
        if self.duration_ticks <= 0:
            msg = "duration_ticks must be positive"
            raise ValueError(msg)
        if not 0 <= self.velocity <= 127:
            msg = "velocity must be between 0 and 127"
            raise ValueError(msg)
        if not isfinite(self.cents_offset):
            msg = "cents_offset must be finite"
            raise ValueError(msg)
