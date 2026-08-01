"""Tempo map events.

``microseconds_per_quarter`` is authoritative rather than BPM. BPM is a derived
convenience: storing it as a float would make two tempo maps that a musician considers
identical produce different content digests, because 120.0 and 119.99999999999999 are
different floats. Integer microseconds-per-quarter is what MIDI itself uses and it
compares exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.core.score.errors import (
    require_nonnegative_int,
    require_positive_int,
    require_schema_version,
)

MICROSECONDS_PER_MINUTE = 60_000_000
# 120 BPM. Named rather than inlined so tests and fixtures agree on one reference.
DEFAULT_MICROSECONDS_PER_QUARTER = 500_000


@dataclass(frozen=True)
class TempoChangeV1:
    """A tempo in effect from ``tick`` until the next tempo change."""

    schema_version: str
    tick: int
    microseconds_per_quarter: int

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_nonnegative_int(self.tick, "tick")
        require_positive_int(self.microseconds_per_quarter, "microseconds_per_quarter")

    @property
    def beats_per_minute(self) -> float:
        """Derived BPM. Read-only convenience; never part of canonical identity."""
        return MICROSECONDS_PER_MINUTE / self.microseconds_per_quarter


def tempo_from_bpm(beats_per_minute: float, *, tick: int = 0) -> TempoChangeV1:
    """Build a tempo change from BPM, rounding to whole microseconds.

    Provided so callers need not do the conversion by hand, and so the rounding
    happens in exactly one place.
    """
    if isinstance(beats_per_minute, bool) or not isinstance(beats_per_minute, (int, float)):
        raise TypeError("beats_per_minute must be a number")
    if beats_per_minute <= 0:
        from master_all_strings.core.score.errors import ScoreContractError

        raise ScoreContractError("beats_per_minute must be positive")
    return TempoChangeV1(
        schema_version=TempoChangeV1.SCHEMA_VERSION,
        tick=tick,
        microseconds_per_quarter=round(MICROSECONDS_PER_MINUTE / beats_per_minute),
    )
