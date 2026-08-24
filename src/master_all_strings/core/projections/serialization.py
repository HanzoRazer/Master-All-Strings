"""Deterministic serialization and digests for canonical projections (DO-013).

A projection digest has one job: change when the projection changes and not
otherwise. That makes the exclusions as load-bearing as the inclusions —
``digest`` cannot feed itself, and ``projection_id`` is an envelope label rather
than a statement about the music.

Enum values are written as their strings and tuples as arrays, so the JSON is
the same on every platform and in every Python version.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from master_all_strings.core.projections.contracts import (
    NotationProjectionV1,
    ProjectionRequestV1,
    TabProjectionV1,
)
from master_all_strings.core.score.errors import ScoreContractError

__all__ = [
    "canonical_projection_digest",
    "projection_to_dict",
    "projection_to_json",
]

#: Fields that are outputs of the digest or labels around it, never inputs.
#: Including ``digest`` would be circular; including ``projection_id`` would make
#: two identical renderings of one revision disagree because of their envelopes.
_DIGEST_EXCLUDED_FIELDS = frozenset({"digest", "projection_id"})


def _encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


def projection_to_dict(record: Any) -> dict[str, Any]:
    """Encode a projection contract as a plain JSON-ready mapping."""

    if not is_dataclass(record) or isinstance(record, type):
        raise ScoreContractError("projection_to_dict requires a projection dataclass")
    encoded = _encode(record)
    if not isinstance(encoded, dict):
        raise ScoreContractError("projection encoding failed")
    return encoded


def projection_to_json(record: Any) -> str:
    """Serialize deterministically: declaration order, stable indentation."""

    return (
        json.dumps(projection_to_dict(record), indent=2, sort_keys=False, ensure_ascii=False)
        + "\n"
    )


def canonical_projection_digest(
    payload: TabProjectionV1 | NotationProjectionV1 | ProjectionRequestV1,
) -> str:
    """Digest one typed projection payload.

    Computed over the payload rather than the envelope, so the same rendering of
    the same revision digests identically however it happens to be wrapped.
    """

    if not isinstance(
        payload, (TabProjectionV1, NotationProjectionV1, ProjectionRequestV1)
    ):
        raise ScoreContractError("expected a typed projection payload")
    encoded = {
        key: value
        for key, value in projection_to_dict(payload).items()
        if key not in _DIGEST_EXCLUDED_FIELDS
    }
    serialized = json.dumps(encoded, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()
