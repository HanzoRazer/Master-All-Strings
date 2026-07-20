"""Serialization helpers for immutable spatial-mapping contracts."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from master_all_strings.instruments import InstrumentProfile, ReferenceMarker, StringProfile


def to_serializable_dict(value: Any) -> Any:
    """Convert dataclass values into JSON-serializable Python containers."""

    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {key: to_serializable_dict(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [to_serializable_dict(item) for item in value]
    if isinstance(value, list):
        return [to_serializable_dict(item) for item in value]
    return value


def instrument_profile_from_mapping(data: Mapping[str, Any]) -> InstrumentProfile:
    """Build an immutable instrument profile from a JSON-like mapping."""

    strings = tuple(StringProfile(**item) for item in data.get("strings", ()))
    markers = tuple(ReferenceMarker(**item) for item in data.get("reference_markers", ()))
    return InstrumentProfile(
        schema_version=data["schema_version"],
        instrument_id=data["instrument_id"],
        display_name=data["display_name"],
        family=data["family"],
        fingerboard_mode=data["fingerboard_mode"],
        strings=strings,
        scale_length_mm=data.get("scale_length_mm"),
        physical_fret_count=data.get("physical_fret_count"),
        reference_markers=markers,
        metadata=data.get("metadata", {}),
    )
