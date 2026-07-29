"""Adapter-private Ardour models.

Every type here is Ardour vocabulary and stays inside this package. None of it may
appear in a contract, in the port, or in any signature a caller outside
``adapters/ardour/`` can reach (ADR-0007 D2).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# The version policy from ADR-0007. 9.7 is the only inspected source revision, and no
# runtime version has passed conformance.
SUPPORTED_MAJOR = 9
MINIMUM_VERSION = (9, 7)
VERIFIED_SOURCE_VERSION = "9.7"
VERIFIED_RUNTIME_VERSIONS: tuple[str, ...] = ()


class ArdourSessionState(StrEnum):
    """Ardour's own session lifecycle, as the adapter models it."""

    ABSENT = "absent"
    LOADING = "loading"
    LOADED = "loaded"
    FAILED = "failed"


@dataclass(frozen=True)
class ArdourSessionRef:
    """A reference to a prepared Ardour session on disk."""

    session_name: str
    session_path: str
    template_id: str
    state: ArdourSessionState


@dataclass(frozen=True)
class ArdourTrackRef:
    """A reference to a track inside a prepared Ardour session."""

    strip_index: int
    track_name: str
    record_armed: bool


def parse_version(reported: str) -> tuple[int, int]:
    """Parse an Ardour version string such as ``"9.7"`` into ``(major, minor)``."""
    parts = reported.strip().split(".")
    if len(parts) < 2 or not all(p.isdigit() for p in parts[:2]):
        raise ValueError(f"unparseable Ardour version {reported!r}")
    return int(parts[0]), int(parts[1])


def is_supported_version(reported: str | None) -> bool:
    """Whether a reported version satisfies ``>=9.7,<10``.

    An unresolved version is never supported. Ardour 9.7 exposes no version over OSC
    (GAP-002), so ``None`` is a real case and must not read as acceptable.
    """
    if reported is None:
        return False
    try:
        major, minor = parse_version(reported)
    except ValueError:
        return False
    return major == SUPPORTED_MAJOR and (major, minor) >= MINIMUM_VERSION
