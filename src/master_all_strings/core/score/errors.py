"""Error type and validators for canonical score contracts.

``ScoreContractError`` subclasses ``SpatialMappingError``, the repository's base for
domain-contract failures (see ``core/foundation.py``), so one ``except`` clause still
catches every contract violation in the codebase while a caller who cares can tell a
score failure apart.

The UTC-timestamp validator is deliberately defined here rather than imported from the
Performance Engine's equivalent. Musical Core must not depend on Performance
(ADR-0006 dependency matrix), and a shared helper would create exactly that edge. The
duplication is the cost of the boundary and is small.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TypeVar

from master_all_strings.core.foundation import SpatialMappingError

_T = TypeVar("_T")

# sha256 hex, lowercase.
DIGEST_LENGTH = 64
# How much of the digest the public revision id carries. Documented and
# collision-tested; the full digest is always stored alongside it.
REVISION_ID_DIGEST_PREFIX = 24
REVISION_ID_PREFIX = "rev-"


class ScoreContractError(SpatialMappingError):
    """Raised when a canonical score contract is constructed with invalid data."""


def require_schema_version(value: str, expected: str) -> None:
    """Require the exact declared schema version."""
    if not isinstance(value, str) or value != expected:
        raise ScoreContractError(f"schema_version must be {expected!r}, got {value!r}")


def require_identifier(value: str, field_name: str) -> None:
    """Require a stable, non-blank identifier with no surrounding whitespace."""
    if not isinstance(value, str) or not value.strip():
        raise ScoreContractError(f"{field_name} must be a non-empty, non-blank string")
    if value != value.strip():
        raise ScoreContractError(f"{field_name} must not have leading or trailing whitespace")


def require_optional_identifier(value: str | None, field_name: str) -> None:
    """Require ``None`` or a valid identifier."""
    if value is not None:
        require_identifier(value, field_name)


def require_utc_timestamp(value: str, field_name: str) -> None:
    """Require an ISO-8601 UTC timestamp ending in ``Z``."""
    require_identifier(value, field_name)
    if not value.endswith("Z"):
        raise ScoreContractError(f"{field_name} must be an ISO-8601 UTC timestamp ending 'Z'")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScoreContractError(f"{field_name} is not a valid ISO-8601 timestamp") from exc


def require_positive_int(value: int, field_name: str) -> None:
    """Require a strictly positive integer (``bool`` rejected)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScoreContractError(f"{field_name} must be an integer")
    if value <= 0:
        raise ScoreContractError(f"{field_name} must be positive")


def require_nonnegative_int(value: int, field_name: str) -> None:
    """Require a nonnegative integer (``bool`` rejected)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScoreContractError(f"{field_name} must be an integer")
    if value < 0:
        raise ScoreContractError(f"{field_name} must be nonnegative")


def require_bool(value: bool, field_name: str) -> None:
    """Require an actual ``bool``, not a truthy value."""
    if not isinstance(value, bool):
        raise ScoreContractError(f"{field_name} must be a boolean")


def require_tuple(value: object, field_name: str) -> None:
    """Require a ``tuple``.

    Collections on an immutable revision must be tuples; a list would let a consumer
    mutate a record whose whole purpose is to be unchanging.
    """
    if not isinstance(value, tuple):
        raise ScoreContractError(f"{field_name} must be a tuple")


def require_unique(values: Iterable[_T], field_name: str) -> None:
    """Require no duplicates among hashable values."""
    items = list(values)
    if len(items) != len(set(items)):
        raise ScoreContractError(f"{field_name} must not contain duplicates")


def require_digest(value: str, field_name: str) -> None:
    """Require a lowercase sha256 hex digest."""
    require_identifier(value, field_name)
    if len(value) != DIGEST_LENGTH or any(c not in "0123456789abcdef" for c in value):
        raise ScoreContractError(
            f"{field_name} must be {DIGEST_LENGTH} lowercase hex characters (sha256)"
        )
