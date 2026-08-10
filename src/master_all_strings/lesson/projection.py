"""Semantic scrolling-fretboard projection payload (zero-authority consumer data).

The renderer must choose nothing: it reads computed positions, timing, instrument
geometry references, and selection information from this payload.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from master_all_strings.core.spatial_mapping import SpatialPosition

from .resolver import ResolvedLessonV1

__all__ = [
    "ScrollingFretboardNoteV1",
    "ScrollingFretboardProjectionV1",
    "build_scrolling_fretboard_projection",
    "compute_projection_digest",
    "projection_to_renderer_view",
]


@dataclass(frozen=True)
class ScrollingFretboardNoteV1:
    """One display-ready note; no selection logic lives here."""

    event_id: str
    midi_note: int
    start_tick: int
    duration_ticks: int
    string_id: str
    physical_fret_number: int | None
    display_order: int
    is_open_string: bool
    selection_source: str  # "teacher_override" | "automatic"


@dataclass(frozen=True)
class ScrollingFretboardProjectionV1:
    """Semantic projection for the MVP scrolling fretboard."""

    schema_version: str
    assignment_id: str
    content_id: str
    title: str
    objective: str | None
    teacher_note: str | None
    instrument_profile_id: str
    tempo_bpm: float | None
    ticks_per_quarter: int
    notes: tuple[ScrollingFretboardNoteV1, ...]


def build_scrolling_fretboard_projection(
    resolved: ResolvedLessonV1,
    *,
    selected: dict[str, SpatialPosition],
    selection_sources: dict[str, str],
) -> ScrollingFretboardProjectionV1:
    """Assemble a display payload from resolved music + selected positions."""

    notes: list[ScrollingFretboardNoteV1] = []
    for event in resolved.events:
        position = selected[event.event_id]
        notes.append(
            ScrollingFretboardNoteV1(
                event_id=event.event_id,
                midi_note=event.midi_note,
                start_tick=event.start_tick,
                duration_ticks=event.duration_ticks,
                string_id=position.string_id,
                physical_fret_number=position.physical_fret_number,
                display_order=position.display_order,
                is_open_string=position.is_open_string,
                selection_source=selection_sources[event.event_id],
            )
        )
    return ScrollingFretboardProjectionV1(
        schema_version="1.0.0",
        assignment_id=resolved.assignment_id,
        content_id=resolved.content_id,
        title=resolved.title,
        objective=resolved.instruction_objective,
        teacher_note=resolved.teacher_note,
        instrument_profile_id=resolved.spatial.instrument_profile_id,
        tempo_bpm=resolved.playback.tempo_bpm,
        ticks_per_quarter=resolved.playback.ticks_per_quarter,
        notes=tuple(notes),
    )


def compute_projection_digest(projection: ScrollingFretboardProjectionV1) -> str:
    """Digest of musically displayed note geometry and timing (not display chrome)."""

    payload = {
        "content_id": projection.content_id,
        "instrument_profile_id": projection.instrument_profile_id,
        "ticks_per_quarter": projection.ticks_per_quarter,
        "tempo_bpm": projection.tempo_bpm,
        "notes": [
            {
                "event_id": note.event_id,
                "midi_note": note.midi_note,
                "start_tick": note.start_tick,
                "duration_ticks": note.duration_ticks,
                "string_id": note.string_id,
                "physical_fret_number": note.physical_fret_number,
                "display_order": note.display_order,
                "is_open_string": note.is_open_string,
                "selection_source": note.selection_source,
            }
            for note in projection.notes
        ],
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def projection_to_renderer_view(
    projection: ScrollingFretboardProjectionV1,
) -> dict[str, object]:
    """Pure data view for a zero-authority renderer. Includes display-only metadata."""

    def encode(value: object) -> object:
        if isinstance(value, Enum):
            return value.value
        if hasattr(value, "__dataclass_fields__"):
            fields = value.__dataclass_fields__
            return {name: encode(getattr(value, name)) for name in fields}
        if isinstance(value, tuple):
            return [encode(item) for item in value]
        return value

    encoded = encode(projection)
    if not isinstance(encoded, dict):
        raise TypeError("projection encoding must produce a dict")
    return encoded
