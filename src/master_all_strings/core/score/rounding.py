"""The one rounding rule canonical identity is allowed to use.

Every place a canonical value is derived from a division — tick conversion, tempo
conversion — must round the same way, because the result reaches the content digest and
therefore the revision id. Python's built-in ``round`` uses banker's rounding, so
``round(0.5)`` is 0 and ``round(1.5)`` is 2. That is a surprising basis for an identity
and impossible to reimplement correctly by accident, so the rule is stated here and
imported rather than inherited from the language.

Kept in its own module so both ``timing`` and ``tempo`` can depend on it without either
depending on the other, and so there is exactly one definition to port when another
implementation has to reproduce these ids.
"""

from __future__ import annotations

from master_all_strings.core.score.errors import (
    ScoreContractError,
    require_positive_int,
)


def divide_round_half_away_from_zero(numerator: int, denominator: int) -> int:
    """Integer division rounding halves away from zero.

    ``5/2 -> 3``, ``-5/2 -> -3``, ``1/2 -> 1``, ``-1/2 -> -1``. Chosen over Python's
    ``round`` so the rule is stated rather than inherited, and so another
    implementation can reproduce it exactly.
    """
    if not isinstance(numerator, int) or isinstance(numerator, bool):
        raise ScoreContractError("numerator must be an integer")
    require_positive_int(denominator, "denominator")
    if numerator >= 0:
        return (2 * numerator + denominator) // (2 * denominator)
    return -((-2 * numerator + denominator) // (2 * denominator))
