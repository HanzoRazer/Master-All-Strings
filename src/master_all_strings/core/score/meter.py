"""Meter map events."""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.core.score.errors import (
    ScoreContractError,
    require_nonnegative_int,
    require_schema_version,
)

# Powers of two: a denominator of 5 or 7 is not a meaningful note value.
SUPPORTED_DENOMINATORS = (1, 2, 4, 8, 16, 32, 64)
MAX_NUMERATOR = 64


@dataclass(frozen=True)
class MeterChangeV1:
    """A time signature in effect from ``tick`` until the next meter change."""

    schema_version: str
    tick: int
    numerator: int
    denominator: int

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_nonnegative_int(self.tick, "tick")
        if isinstance(self.numerator, bool) or not isinstance(self.numerator, int):
            raise ScoreContractError("numerator must be an integer")
        if not 1 <= self.numerator <= MAX_NUMERATOR:
            raise ScoreContractError(f"numerator must be between 1 and {MAX_NUMERATOR}")
        if self.denominator not in SUPPORTED_DENOMINATORS:
            raise ScoreContractError(
                f"denominator must be one of {list(SUPPORTED_DENOMINATORS)}"
            )

    def ticks_per_measure(self, ticks_per_quarter: int) -> int:
        """Ticks spanned by one measure of this meter."""
        return self.numerator * (ticks_per_quarter * 4) // self.denominator
