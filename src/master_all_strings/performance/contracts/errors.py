"""Error type and shared validators for Performance Engine contracts.

``PerformanceContractError`` subclasses ``SpatialMappingError`` deliberately. That
type is the repository's base for domain-contract failures (see
``core/foundation.py``), despite its spatial-mapping name, so a caller catching it
catches every contract violation in the codebase uniformly. Subclassing keeps that
uniformity while letting a caller who cares distinguish a Performance failure.

Validators from ``core.foundation`` are reused directly wherever they apply; they
raise the base type, which is caught by the same ``except`` clause. Only rules with
no foundation equivalent are defined here.

Performance depends on Musical Core, which is a permitted direction. No import here
points at Educational, Creative, or any runtime implementation.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import TypeVar

from master_all_strings.core.foundation import SpatialMappingError

_T = TypeVar("_T")

# A single MIDI message is at most a few bytes; SysEx can be long but is not accepted
# as a captured performance event. The bound exists so a malformed or hostile stream
# cannot grow a capture record without limit (ADR-0007 security boundary).
MAX_RAW_PAYLOAD_BYTES = 64


class PerformanceContractError(SpatialMappingError):
    """Raised when a Performance Engine contract is constructed with invalid data."""


def require_schema_version(value: str, expected: str) -> None:
    """Require the exact declared schema version.

    Versions are fixed per contract rather than accepted as a range: a record that
    claims a version we do not implement must fail loudly at construction, not be
    read with the wrong field meanings.
    """
    if not isinstance(value, str) or value != expected:
        raise PerformanceContractError(f"schema_version must be {expected!r}, got {value!r}")


def require_identifier(value: str, field_name: str) -> None:
    """Require a stable, non-blank string identifier with no surrounding whitespace.

    Identifiers are compared and serialized, so ``"take-1"`` and ``" take-1 "`` must
    not be able to denote the same thing.
    """
    if not isinstance(value, str) or not value.strip():
        raise PerformanceContractError(f"{field_name} must be a non-empty, non-blank string")
    if value != value.strip():
        raise PerformanceContractError(f"{field_name} must not have leading or trailing whitespace")


def require_optional_identifier(value: str | None, field_name: str) -> None:
    """Require ``None`` or a valid identifier. ``None`` means *unresolved*, not absent."""
    if value is not None:
        require_identifier(value, field_name)


def require_utc_timestamp(value: str, field_name: str) -> None:
    """Require an ISO-8601 UTC timestamp ending in ``Z``.

    Wall-clock times use exactly this representation across every Performance
    contract. Event timing uses integer nanoseconds instead (``*_ns`` fields); the two
    never mix, because one is a point in civil time and the other is a monotonic
    offset that survives clock adjustment.
    """
    require_identifier(value, field_name)
    if not value.endswith("Z"):
        raise PerformanceContractError(f"{field_name} must be an ISO-8601 UTC timestamp ending 'Z'")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PerformanceContractError(f"{field_name} is not a valid ISO-8601 timestamp") from exc


def require_positive_int(value: int, field_name: str) -> None:
    """Require a strictly positive integer (``bool`` rejected)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise PerformanceContractError(f"{field_name} must be an integer")
    if value <= 0:
        raise PerformanceContractError(f"{field_name} must be positive")


def require_nonnegative_int(value: int, field_name: str) -> None:
    """Require a nonnegative integer (``bool`` rejected)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise PerformanceContractError(f"{field_name} must be an integer")
    if value < 0:
        raise PerformanceContractError(f"{field_name} must be nonnegative")


def require_bool(value: bool, field_name: str) -> None:
    """Require an actual ``bool``, not a truthy value."""
    if not isinstance(value, bool):
        raise PerformanceContractError(f"{field_name} must be a boolean")


def require_range(value: int, field_name: str, low: int, high: int) -> None:
    """Require an integer within an inclusive range."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise PerformanceContractError(f"{field_name} must be an integer")
    if not low <= value <= high:
        raise PerformanceContractError(f"{field_name} must be between {low} and {high}")


def require_tuple(value: object, field_name: str) -> None:
    """Require a ``tuple``.

    Collections on frozen contracts must be tuples, not lists: a list field would let
    a caller mutate an "immutable" record after construction, which is exactly the
    guarantee raw capture depends on.
    """
    if not isinstance(value, tuple):
        raise PerformanceContractError(f"{field_name} must be a tuple")


def require_unique(values: Iterable[_T], field_name: str) -> None:
    """Require no duplicates among hashable values."""
    items = list(values)
    if len(items) != len(set(items)):
        raise PerformanceContractError(f"{field_name} must not contain duplicates")


def require_non_empty_tuple(value: Sequence[_T], field_name: str) -> None:
    """Require a non-empty tuple."""
    require_tuple(value, field_name)
    if not value:
        raise PerformanceContractError(f"{field_name} must not be empty")


def require_raw_payload(value: tuple[int, ...], field_name: str) -> None:
    """Require a bounded tuple of byte values."""
    require_tuple(value, field_name)
    if len(value) > MAX_RAW_PAYLOAD_BYTES:
        raise PerformanceContractError(
            f"{field_name} must be at most {MAX_RAW_PAYLOAD_BYTES} bytes, got {len(value)}"
        )
    for byte in value:
        if isinstance(byte, bool) or not isinstance(byte, int) or not 0 <= byte <= 255:
            raise PerformanceContractError(f"{field_name} must contain byte values 0..255")
