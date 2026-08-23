"""Deterministic serialization for presentation contracts (DO-012).

The browser is the runtime producer of timeline, playhead, and health state.
Python owns the *normative shape*: these functions and the JSON Schemas beside
them define what a valid record is, and fixture vectors round-tripped here are
what the Node tests are checked against.
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, TypeVar

from master_all_strings.presentation.contracts import (
    MediaSyncMode,
    MediaTimelineBindingV1,
    SyncCorrection,
    SynchronizationHealthV1,
    SynchronizationStatus,
    TeachingPlayheadStateV1,
    TeachingTimelineStateV1,
    TimelineAnchorV1,
)
from master_all_strings.presentation.errors import PresentationContractError

__all__ = [
    "from_dict",
    "to_dict",
    "to_json",
]

_T = TypeVar("_T")

# Enum-typed fields, so deserialization restores the enum rather than the raw
# string and a round-trip is genuinely lossless.
_ENUM_FIELDS: dict[str, type[Enum]] = {
    "sync_mode": MediaSyncMode,
    "status": SynchronizationStatus,
    "last_correction": SyncCorrection,
}

_SUPPORTED = (
    TimelineAnchorV1,
    TeachingTimelineStateV1,
    TeachingPlayheadStateV1,
    MediaTimelineBindingV1,
    SynchronizationHealthV1,
)


def _encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


def to_dict(record: Any) -> dict[str, Any]:
    """Encode a presentation contract as a plain JSON-ready mapping."""

    if not isinstance(record, _SUPPORTED):
        raise PresentationContractError(
            "to_dict requires a presentation contract instance"
        )
    return {f.name: _encode(getattr(record, f.name)) for f in fields(record)}


def to_json(record: Any) -> str:
    """Serialize deterministically: declaration field order, stable indentation."""

    return json.dumps(to_dict(record), indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def from_dict(record_type: type[_T], payload: dict[str, Any]) -> _T:
    """Rebuild a presentation contract from its mapping form.

    Unknown keys are rejected rather than ignored: silently dropping a field
    would let a record from a newer schema round-trip as if it had validated.
    """

    if record_type not in _SUPPORTED:
        raise PresentationContractError(f"unsupported presentation contract: {record_type!r}")
    if not isinstance(payload, dict):
        raise PresentationContractError("payload must be a mapping")

    known = {f.name for f in fields(record_type)}  # type: ignore[arg-type]
    unknown = set(payload) - known
    if unknown:
        raise PresentationContractError(
            f"unknown field(s) for {record_type.__name__}: {sorted(unknown)}"
        )

    kwargs: dict[str, Any] = {}
    for field in fields(record_type):  # type: ignore[arg-type]
        if field.name not in payload:
            continue
        value = payload[field.name]
        enum_cls = _ENUM_FIELDS.get(field.name)
        if enum_cls is not None and value is not None:
            kwargs[field.name] = enum_cls(value)
        elif field.name == "active_event_ids" and value is not None:
            kwargs[field.name] = tuple(value)
        else:
            kwargs[field.name] = value
    return record_type(**kwargs)
