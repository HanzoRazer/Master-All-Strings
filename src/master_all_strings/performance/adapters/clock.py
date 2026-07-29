"""A deterministic clock for runtime adapters.

Separated from the fake runtime because it is not a fake-runtime concern: any adapter
that needs reproducible timestamps in tests can use it, and keeping it here stops the
fake from growing a second responsibility.

Contracts never read a clock themselves — timestamps are always supplied by the
caller — so this is the only place time enters the Performance package, and it never
reads real time at all.
"""

from __future__ import annotations

DEFAULT_ORIGIN_HOUR = 10
DEFAULT_DATE = "2026-07-24"


class DeterministicClock:
    """Emits ISO-8601 UTC timestamps one second apart from a fixed origin.

    Real time never enters a test, so the same scenario always produces
    byte-identical records.
    """

    def __init__(self, origin_second: int = 0, *, date: str = DEFAULT_DATE) -> None:
        self._tick = origin_second
        self._date = date

    def now(self) -> str:
        """Return the next timestamp and advance one second."""
        value = self._tick
        self._tick += 1
        hours, remainder = divmod(value, 3600)
        minutes, seconds = divmod(remainder, 60)
        hour = DEFAULT_ORIGIN_HOUR + hours
        if hour > 23:
            raise ValueError(
                "deterministic clock ran past midnight; a test needing more than "
                f"{(24 - DEFAULT_ORIGIN_HOUR) * 3600} ticks should set an explicit date"
            )
        return f"{self._date}T{hour:02d}:{minutes:02d}:{seconds:02d}Z"
