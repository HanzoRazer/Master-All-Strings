"""Dependency-neutral primitives shared across core domain packages.

This is a LEAF module: it imports nothing from within ``master_all_strings``, so
both ``instruments`` and ``core.spatial_mapping`` can depend on it without forming
an import cycle. Previously these primitives lived under ``core.spatial_mapping``,
which made ``instruments`` depend outward on the spatial-mapping package; because
``core.spatial_mapping.__init__`` re-exports ``serialization`` (which imports
``instruments``), that produced an order-dependent circular import. Keeping the
shared error, validators, JSON type aliases, and the cross-cutting
``FingerboardMode`` enum here breaks that cycle at the root.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from math import isfinite
from typing import TypeAlias

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | tuple["JSONValue", ...] | Mapping[str, "JSONValue"]


class SpatialMappingError(ValueError):
    """Base error for domain-contract failures."""


class FingerboardMode(StrEnum):
    """Supported fingerboard semantics (a cross-cutting instrument concept)."""

    FRETTED = "fretted"
    FRETLESS = "fretless"
    HYBRID = "hybrid"


def require_non_empty(value: str, field_name: str) -> None:
    """Require a non-empty, non-whitespace string.

    Whitespace-only values (e.g. ``"   "``) are rejected: for contract identifiers
    and labels a blank string is not a meaningful value.
    """
    if not isinstance(value, str) or not value.strip():
        raise SpatialMappingError(f"{field_name} must be a non-empty, non-blank string")


def require_midi_note(value: int, field_name: str) -> None:
    """Require an integer MIDI note in the inclusive range 0..127.

    ``bool`` is explicitly rejected: because ``bool`` subclasses ``int`` in Python,
    ``True``/``False`` would otherwise silently pass as notes 1/0.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise SpatialMappingError(f"{field_name} must be an integer MIDI note")
    if not 0 <= value <= 127:
        raise SpatialMappingError(f"{field_name} must be between 0 and 127")


def require_finite(value: float, field_name: str) -> None:
    """Require a finite real number (``bool`` rejected, ``NaN``/``inf`` rejected)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise SpatialMappingError(f"{field_name} must be a finite number")


def require_nonnegative(value: float, field_name: str) -> None:
    """Require a nonnegative numeric value (assumes finiteness already checked)."""
    if value < 0:
        raise SpatialMappingError(f"{field_name} must be nonnegative")


def require_positive(value: float, field_name: str) -> None:
    """Require a strictly positive numeric value (assumes finiteness already checked)."""
    if value <= 0:
        raise SpatialMappingError(f"{field_name} must be positive")


def require_index(value: int, field_name: str) -> None:
    """Require a nonnegative integer (``bool`` rejected)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise SpatialMappingError(f"{field_name} must be an integer")
    if value < 0:
        raise SpatialMappingError(f"{field_name} must be nonnegative")
