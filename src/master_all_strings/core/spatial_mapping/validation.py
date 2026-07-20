"""Shared validation helpers for spatial-mapping contracts."""

from __future__ import annotations

from math import isfinite

from .errors import SpatialMappingError


def require_non_empty(value: str, field_name: str) -> None:
    """Require a non-empty string value."""

    if not value:
        raise SpatialMappingError(f"{field_name} must not be empty")


def require_midi_note(value: int, field_name: str) -> None:
    """Require a MIDI note number in the inclusive range 0..127."""

    if not 0 <= value <= 127:
        raise SpatialMappingError(f"{field_name} must be between 0 and 127")


def require_finite(value: float, field_name: str) -> None:
    """Require a finite floating-point value."""

    if not isfinite(value):
        raise SpatialMappingError(f"{field_name} must be finite")


def require_nonnegative(value: float, field_name: str) -> None:
    """Require a nonnegative numeric value."""

    if value < 0:
        raise SpatialMappingError(f"{field_name} must be nonnegative")


def require_positive(value: float, field_name: str) -> None:
    """Require a strictly positive numeric value."""

    if value <= 0:
        raise SpatialMappingError(f"{field_name} must be positive")
