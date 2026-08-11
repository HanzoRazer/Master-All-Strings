"""Deterministic serialization and digests for fretboard projections."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from master_all_strings.mvp.errors import ProjectionBuildError, UnsupportedProjectionVersionError
from master_all_strings.mvp.projection.models import (
    FRETBOARD_SCROLL_PROJECTION_TYPE,
    FRETBOARD_SCROLL_PROJECTION_VERSION,
    FretboardInstrumentProjectionV1,
    FretboardLaneV1,
    FretboardProjectedNoteV1,
    FretboardScrollProjectionV1,
    FretboardTimelineV1,
    FretProjectionV1,
    ProjectedNoteStatus,
    SelectionOrigin,
    TempoChangeProjectionV1,
)

__all__ = [
    "compute_projection_digest",
    "deserialize_fretboard_projection",
    "serialize_fretboard_projection",
    "to_dict",
    "validate_projection",
]


def _encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if isinstance(value, float):
        # Stable JSON number rendering for digests/round-trips.
        return value
    return value


def to_dict(projection: FretboardScrollProjectionV1) -> dict[str, Any]:
    if not isinstance(projection, FretboardScrollProjectionV1):
        raise ProjectionBuildError("expected FretboardScrollProjectionV1")
    encoded = _encode(projection)
    if not isinstance(encoded, dict):
        raise ProjectionBuildError("projection encoding failed")
    return encoded


def serialize_fretboard_projection(projection: FretboardScrollProjectionV1) -> str:
    return json.dumps(to_dict(projection), indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def _behavior_dict(projection: FretboardScrollProjectionV1) -> dict[str, Any]:
    data = to_dict(projection)
    data.pop("projection_digest", None)
    # Presentation chrome that must not affect musical/display digest identity.
    data.pop("description", None)
    data.pop("objective", None)
    data.pop("teacher_note", None)
    return data


def compute_projection_digest(projection: FretboardScrollProjectionV1) -> str:
    """Digest of musically/spatially behavioral projection data."""

    payload = json.dumps(
        _behavior_dict(projection),
        separators=(",", ":"),
        ensure_ascii=True,
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def validate_projection(projection: FretboardScrollProjectionV1) -> None:
    """Validate invariants already enforced by models; re-check version gate."""

    if projection.projection_type != FRETBOARD_SCROLL_PROJECTION_TYPE:
        raise UnsupportedProjectionVersionError(
            f"unsupported projection_type: {projection.projection_type!r}"
        )
    if projection.projection_version != FRETBOARD_SCROLL_PROJECTION_VERSION:
        raise UnsupportedProjectionVersionError(
            f"unsupported projection_version: {projection.projection_version!r}"
        )
    lane_ids = {lane.string_id for lane in projection.instrument.lanes}
    for note in projection.notes:
        if note.status is ProjectedNoteStatus.SELECTED:
            assert note.string_id is not None
            if note.string_id not in lane_ids:
                raise ProjectionBuildError(
                    f"note {note.event_id!r} references unknown string {note.string_id!r}"
                )


def deserialize_fretboard_projection(
    text: str | bytes | dict[str, Any],
) -> FretboardScrollProjectionV1:
    if isinstance(text, dict):
        data = text
    else:
        if isinstance(text, bytes):
            text = text.decode("utf-8")
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ProjectionBuildError("projection must be an object")

    version = data.get("projection_version")
    if version != FRETBOARD_SCROLL_PROJECTION_VERSION:
        raise UnsupportedProjectionVersionError(
            f"unsupported projection_version: {version!r}"
        )

    timeline = data["timeline"]
    instrument = data["instrument"]
    notes = []
    for item in data["notes"]:
        origin = item.get("selection_origin")
        notes.append(
            FretboardProjectedNoteV1(
                event_id=item["event_id"],
                status=item["status"],
                midi_note=item["midi_note"],
                pitch_label=item["pitch_label"],
                onset_tick=item["onset_tick"],
                duration_ticks=item["duration_ticks"],
                onset_seconds=item["onset_seconds"],
                release_seconds=item["release_seconds"],
                lane_display_order=item.get("lane_display_order"),
                string_id=item.get("string_id"),
                fret_number=item.get("fret_number"),
                relative_semitone_position=item.get("relative_semitone_position"),
                normalized_position=item.get("normalized_position"),
                is_open_string=item.get("is_open_string"),
                selection_origin=SelectionOrigin(origin) if origin is not None else None,
                unresolved_reason=item.get("unresolved_reason"),
            )
        )

    projection = FretboardScrollProjectionV1(
        schema_version=data["schema_version"],
        projection_type=data["projection_type"],
        projection_version=data["projection_version"],
        fidelity=data["fidelity"],
        projection_digest=data["projection_digest"],
        assignment_id=data["assignment_id"],
        content_id=data["content_id"],
        title=data["title"],
        timeline=FretboardTimelineV1(**timeline),
        tempo_changes=tuple(TempoChangeProjectionV1(**item) for item in data["tempo_changes"]),
        instrument=FretboardInstrumentProjectionV1(
            instrument_id=instrument["instrument_id"],
            display_name=instrument["display_name"],
            fingerboard_mode=instrument["fingerboard_mode"],
            scale_length_mm=instrument.get("scale_length_mm"),
            lanes=tuple(FretboardLaneV1(**lane) for lane in instrument["lanes"]),
            frets=tuple(FretProjectionV1(**fret) for fret in instrument["frets"]),
        ),
        selection_policy=data["selection_policy"],
        notes=tuple(notes),
        warnings=tuple(data.get("warnings") or ()),
        unsupported_features=tuple(data.get("unsupported_features") or ()),
        description=data.get("description"),
        objective=data.get("objective"),
        teacher_note=data.get("teacher_note"),
    )
    validate_projection(projection)
    return projection
