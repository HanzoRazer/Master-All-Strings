"""Presentation-layer contract errors.

Presentation records describe how already-authoritative information is shown
over time. A validation failure here is never a musical error: it means a
follower was handed state that could not honestly describe the transport.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite

from master_all_strings.core.foundation import SpatialMappingError

__all__ = [
    "PresentationContractError",
    "require_finite_number",
    "require_identifier",
    "require_nonnegative_int",
    "require_nonnegative_number",
    "require_optional_identifier",
    "require_schema_version",
    "require_tuple",
    "require_unique",
]


class PresentationContractError(SpatialMappingError):
    """Raised when a presentation contract is constructed with invalid data."""


def require_schema_version(value: str, expected: str) -> None:
    if not isinstance(value, str) or value != expected:
        raise PresentationContractError(f"schema_version must be {expected!r}, got {value!r}")


def require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise PresentationContractError(f"{field_name} must be a non-empty, non-blank string")
    if value != value.strip():
        raise PresentationContractError(
            f"{field_name} must not have leading or trailing whitespace"
        )


def require_optional_identifier(value: str | None, field_name: str) -> None:
    if value is not None:
        require_identifier(value, field_name)


def require_nonnegative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PresentationContractError(f"{field_name} must be an integer")
    if value < 0:
        raise PresentationContractError(f"{field_name} must be nonnegative")


def require_finite_number(value: float, field_name: str) -> None:
    # ``bool`` subclasses ``int``; without this guard True would pass as 1.0.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PresentationContractError(f"{field_name} must be a number")
    if not isfinite(value):
        raise PresentationContractError(f"{field_name} must be finite")


def require_nonnegative_number(value: float, field_name: str) -> None:
    require_finite_number(value, field_name)
    if float(value) < 0.0:
        raise PresentationContractError(f"{field_name} must be nonnegative")


def require_tuple(value: object, field_name: str) -> None:
    if not isinstance(value, tuple):
        raise PresentationContractError(f"{field_name} must be a tuple")


def require_unique(values: Sequence[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise PresentationContractError(f"{field_name} must contain unique entries")
