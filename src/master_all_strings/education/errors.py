"""Educational Engine contract errors."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from master_all_strings.core.foundation import SpatialMappingError

_T = TypeVar("_T")


class EducationContractError(SpatialMappingError):
    """Raised when an Educational Engine contract is constructed with invalid data."""


def require_schema_version(value: str, expected: str) -> None:
    if not isinstance(value, str) or value != expected:
        raise EducationContractError(f"schema_version must be {expected!r}, got {value!r}")


def require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise EducationContractError(f"{field_name} must be a non-empty, non-blank string")
    if value != value.strip():
        raise EducationContractError(f"{field_name} must not have leading or trailing whitespace")


def require_optional_identifier(value: str | None, field_name: str) -> None:
    if value is not None:
        require_identifier(value, field_name)


def require_nonnegative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EducationContractError(f"{field_name} must be an integer")
    if value < 0:
        raise EducationContractError(f"{field_name} must be nonnegative")


def require_positive_int(value: int, field_name: str) -> None:
    require_nonnegative_int(value, field_name)
    if value == 0:
        raise EducationContractError(f"{field_name} must be positive")


def require_finite_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EducationContractError(f"{field_name} must be a number")
    if value != value or value in (float("inf"), float("-inf")):
        raise EducationContractError(f"{field_name} must be finite")


def require_ratio(value: float, field_name: str) -> None:
    require_finite_number(value, field_name)
    if not 0.0 <= float(value) <= 1.0:
        raise EducationContractError(f"{field_name} must be between 0 and 1 inclusive")


def require_tuple(value: object, field_name: str) -> None:
    if not isinstance(value, tuple):
        raise EducationContractError(f"{field_name} must be a tuple")


def require_unique(values: Sequence[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise EducationContractError(f"{field_name} must contain unique entries")
