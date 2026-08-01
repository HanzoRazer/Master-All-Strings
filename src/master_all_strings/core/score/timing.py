"""Converting monotonic capture nanoseconds into canonical musical ticks.

Captured performance carries elapsed nanoseconds. Canonical music carries integer
ticks. Something has to bridge them, and the name matters (ADR-0008 D8):

**Tick-grid rounding** — the required numerical conversion from continuous elapsed time
into the integer tick domain ``MusicalEvent`` uses. At 120 BPM and 960 PPQ one tick is
about 0.52 ms, so the residue is numerical.

**Musical quantization** — intentional movement of events toward musically meaningful
rhythmic locations. Not performed here, and not performed anywhere in DO-007. A note
played 30 ms late stays 30 ms late.

Two design choices are load-bearing:

* **Integer arithmetic throughout.** Floating point would make the conversion
  irreproducible across platforms and languages, and the digest depends on it.
* **A named tie rule.** Halves round away from zero, which for nonnegative elapsed time
  is half-up. The rule itself lives in ``core.score.rounding`` because tempo conversion
  needs the same one, and two derivations of canonical values must not round
  differently.

This module converts a single elapsed duration. Deciding *which* note-on and note-off
belong together is a separate concern and belongs to the ingestion policy (A5).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from master_all_strings.core.score.errors import (
    ScoreContractError,
    require_positive_int,
)
from master_all_strings.core.score.provenance import RoundingPolicy
from master_all_strings.core.score.rounding import divide_round_half_away_from_zero

NANOSECONDS_PER_SECOND = 1_000_000_000
MICROSECONDS_PER_SECOND = 1_000_000
# The DO-007 conversion basis.
DEFAULT_TICKS_PER_QUARTER = 960

__all__ = [
    "DEFAULT_TICKS_PER_QUARTER",
    "MICROSECONDS_PER_SECOND",
    "NANOSECONDS_PER_SECOND",
    "TickConversion",
    "convert_duration",
    "convert_elapsed",
    # Re-exported: the rule now lives in ``rounding`` so ``tempo`` can use it too, but
    # it is still part of this module's vocabulary for anyone reading the conversion.
    "divide_round_half_away_from_zero",
    "nanoseconds_to_ticks",
    "require_convertible_tempo",
    "ticks_to_nanoseconds",
]


def require_convertible_tempo(microseconds_per_quarter: int | None) -> int:
    """Require a tempo the conversion can actually use.

    A missing, zero, or non-finite tempo is rejected rather than defaulted. Silently
    assuming 120 BPM would put a fabricated tempo into canonical music and into the
    content digest, where it would be indistinguishable from a declared one.
    """
    if microseconds_per_quarter is None:
        raise ScoreContractError(
            "tempo is required to convert capture timing; refusing to assume a default"
        )
    if isinstance(microseconds_per_quarter, bool):
        raise ScoreContractError("microseconds_per_quarter must be an integer")
    if isinstance(microseconds_per_quarter, float):
        if not isfinite(microseconds_per_quarter):
            raise ScoreContractError("microseconds_per_quarter must be finite")
        raise ScoreContractError("microseconds_per_quarter must be an integer")
    require_positive_int(microseconds_per_quarter, "microseconds_per_quarter")
    return microseconds_per_quarter


def nanoseconds_to_ticks(
    elapsed_ns: int,
    *,
    ticks_per_quarter: int = DEFAULT_TICKS_PER_QUARTER,
    microseconds_per_quarter: int,
) -> int:
    """Convert elapsed nanoseconds to ticks by tick-grid rounding.

    ``ticks = elapsed_ns * ppq / (microseconds_per_quarter * 1000)`` evaluated in
    integer arithmetic with halves rounded away from zero.
    """
    if isinstance(elapsed_ns, bool) or not isinstance(elapsed_ns, int):
        raise ScoreContractError("elapsed_ns must be an integer")
    if elapsed_ns < 0:
        raise ScoreContractError(
            "elapsed_ns must not be negative; an event cannot precede the capture origin"
        )
    require_positive_int(ticks_per_quarter, "ticks_per_quarter")
    mpq = require_convertible_tempo(microseconds_per_quarter)
    numerator = elapsed_ns * ticks_per_quarter
    denominator = mpq * (NANOSECONDS_PER_SECOND // MICROSECONDS_PER_SECOND)
    return divide_round_half_away_from_zero(numerator, denominator)


def ticks_to_nanoseconds(
    ticks: int,
    *,
    ticks_per_quarter: int = DEFAULT_TICKS_PER_QUARTER,
    microseconds_per_quarter: int,
) -> int:
    """Convert ticks back to nanoseconds, for computing the rounding residue."""
    if isinstance(ticks, bool) or not isinstance(ticks, int):
        raise ScoreContractError("ticks must be an integer")
    require_positive_int(ticks_per_quarter, "ticks_per_quarter")
    mpq = require_convertible_tempo(microseconds_per_quarter)
    numerator = ticks * mpq * (NANOSECONDS_PER_SECOND // MICROSECONDS_PER_SECOND)
    return divide_round_half_away_from_zero(numerator, ticks_per_quarter)


@dataclass(frozen=True)
class TickConversion:
    """One converted value with the evidence needed to check the arithmetic."""

    elapsed_ns: int
    ticks: int
    rounding_delta_ns: int
    ticks_per_quarter: int
    microseconds_per_quarter: int
    rounding_policy: RoundingPolicy = RoundingPolicy.ROUND_HALF_AWAY_FROM_ZERO

    @property
    def is_exact(self) -> bool:
        """Whether the conversion landed exactly on a tick boundary."""
        return self.rounding_delta_ns == 0


def convert_elapsed(
    elapsed_ns: int,
    *,
    ticks_per_quarter: int = DEFAULT_TICKS_PER_QUARTER,
    microseconds_per_quarter: int,
) -> TickConversion:
    """Convert elapsed nanoseconds and report the residue.

    ``rounding_delta_ns`` is ``elapsed_ns`` minus the nanosecond position of the tick
    chosen — positive when the event was rounded earlier than it happened, negative
    when later. Retained so the conversion is auditable rather than asserted.
    """
    ticks = nanoseconds_to_ticks(
        elapsed_ns,
        ticks_per_quarter=ticks_per_quarter,
        microseconds_per_quarter=microseconds_per_quarter,
    )
    reconstructed_ns = ticks_to_nanoseconds(
        ticks,
        ticks_per_quarter=ticks_per_quarter,
        microseconds_per_quarter=microseconds_per_quarter,
    )
    return TickConversion(
        elapsed_ns=elapsed_ns,
        ticks=ticks,
        rounding_delta_ns=elapsed_ns - reconstructed_ns,
        ticks_per_quarter=ticks_per_quarter,
        microseconds_per_quarter=microseconds_per_quarter,
    )


def convert_duration(
    onset_ns: int,
    release_ns: int,
    *,
    ticks_per_quarter: int = DEFAULT_TICKS_PER_QUARTER,
    microseconds_per_quarter: int,
) -> TickConversion:
    """Convert a note duration from its onset and release nanoseconds.

    A duration that rounds below one tick is rejected as ``DURATION_BELOW_ONE_TICK``
    rather than widened to one tick. ``MusicalEvent`` requires a positive duration, and
    inflating a sub-tick note would invent length the performance did not contain.
    """
    if release_ns < onset_ns:
        raise ScoreContractError("release_ns must not precede onset_ns")
    conversion = convert_elapsed(
        release_ns - onset_ns,
        ticks_per_quarter=ticks_per_quarter,
        microseconds_per_quarter=microseconds_per_quarter,
    )
    if conversion.ticks < 1:
        raise ScoreContractError(
            "DURATION_BELOW_ONE_TICK: "
            f"{release_ns - onset_ns} ns rounds to {conversion.ticks} ticks at "
            f"{ticks_per_quarter} PPQ; refusing to widen it to one tick"
        )
    return conversion
