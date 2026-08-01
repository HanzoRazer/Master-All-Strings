"""Tempo map events.

``microseconds_per_quarter`` is authoritative rather than BPM. BPM is a derived
convenience: storing it as a float would make two tempo maps that a musician considers
identical produce different content digests, because 120.0 and 119.99999999999999 are
different floats. Integer microseconds-per-quarter is what MIDI itself uses and it
compares exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from master_all_strings.core.score.errors import (
    ScoreContractError,
    require_nonnegative_int,
    require_positive_int,
    require_schema_version,
)
from master_all_strings.core.score.rounding import divide_round_half_away_from_zero

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

    Provided so callers need not do the conversion by hand, and so the rounding happens
    in exactly one place.

    The division is exact and the rounding is named. ``Fraction`` represents the BPM
    the caller actually passed — including a float's true binary value — so the quotient
    is a rational rather than an approximation, and the tie is then broken by the
    repository's one rounding rule. Python's ``round`` was used here originally, which
    contradicted the rule ``timing`` states at length: this value becomes a
    ``TempoChangeV1`` in the tempo map, the tempo map is inside the content digest, and
    the Performance seam calls this function to build every ingestion request. Banker's
    rounding on that path meant a BPM landing on a half-microsecond produced a different
    revision id than a faithful reimplementation of the documented rule would.

    Rejects a non-numeric or non-positive BPM the same way, with ``ScoreContractError``.
    A caller catching contract failures should not have to also catch ``TypeError`` to
    handle one bad argument, and every other validator in this package raises the
    contract error for a wrong type.
    """
    if isinstance(beats_per_minute, bool) or not isinstance(beats_per_minute, (int, float)):
        raise ScoreContractError("beats_per_minute must be a number")
    if beats_per_minute != beats_per_minute or beats_per_minute in (
        float("inf"),
        float("-inf"),
    ):
        raise ScoreContractError("beats_per_minute must be finite")
    if beats_per_minute <= 0:
        raise ScoreContractError("beats_per_minute must be positive")
    exact = Fraction(MICROSECONDS_PER_MINUTE) / Fraction(beats_per_minute)
    return TempoChangeV1(
        schema_version=TempoChangeV1.SCHEMA_VERSION,
        tick=tick,
        microseconds_per_quarter=divide_round_half_away_from_zero(
            exact.numerator, exact.denominator
        ),
    )
