"""MVP-1E orchestration: assignment → resolve → MSME → select → project.

Downstream MSME generation is unchanged. Automatic selection uses the MVP
enumeration scaffold pending DO-004. Routing metadata is never consulted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.spatial_mapping import SpatialPosition, generate_candidates
from master_all_strings.instruments import InstrumentProfile

from .auto_select import select_automatic_position
from .errors import LessonValidationError
from .models import LessonAssignmentV1
from .overrides import apply_validated_overrides
from .projection import (
    ScrollingFretboardProjectionV1,
    build_scrolling_fretboard_projection,
    compute_projection_digest,
)
from .resolver import ResolvedLessonV1, resolve_lesson_assignment
from .validation import validate_assignment

__all__ = [
    "MvpLessonPipelineResultV1",
    "SelectedSpatialEventV1",
    "run_mvp_lesson_pipeline",
]


@dataclass(frozen=True)
class SelectedSpatialEventV1:
    """One event with its selected spatial position and selection source."""

    event: MusicalEvent
    position: SpatialPosition
    candidates: tuple[SpatialPosition, ...]
    selection_source: str


@dataclass(frozen=True)
class MvpLessonPipelineResultV1:
    """End-to-end MVP proof outputs for one assignment."""

    resolved: ResolvedLessonV1
    selected_events: tuple[SelectedSpatialEventV1, ...]
    projection: ScrollingFretboardProjectionV1
    projection_digest: str


def run_mvp_lesson_pipeline(
    assignment: LessonAssignmentV1,
    *,
    instrument_profiles: Mapping[str, InstrumentProfile],
) -> MvpLessonPipelineResultV1:
    """Run the MVP-1E vertical slice. Routing is never read."""

    _routing_ignored = assignment.routing  # noqa: F841
    validate_assignment(
        assignment,
        instrument_profiles=instrument_profiles,
        validate_overrides_physically=True,
    )
    resolved = resolve_lesson_assignment(assignment)
    profile = instrument_profiles[resolved.spatial.instrument_profile_id]

    override_positions = apply_validated_overrides(
        assignment.teacher_overrides,
        events=resolved.events,
        instrument=profile,
    )

    selected_events: list[SelectedSpatialEventV1] = []
    selected_map: dict[str, SpatialPosition] = {}
    sources: dict[str, str] = {}

    for event in resolved.events:
        candidates = generate_candidates(event, profile)
        if event.event_id in override_positions:
            position = override_positions[event.event_id]
            source = "teacher_override"
            if position not in candidates and not _position_in_candidates(position, candidates):
                raise LessonValidationError(
                    "validated override missing from MSME candidates",
                    code="override_impossible_position",
                )
        else:
            position = select_automatic_position(candidates, spatial=resolved.spatial)
            source = "automatic"
        selected_events.append(
            SelectedSpatialEventV1(
                event=event,
                position=position,
                candidates=candidates,
                selection_source=source,
            )
        )
        selected_map[event.event_id] = position
        sources[event.event_id] = source

    projection = build_scrolling_fretboard_projection(
        resolved,
        selected=selected_map,
        selection_sources=sources,
    )
    return MvpLessonPipelineResultV1(
        resolved=resolved,
        selected_events=tuple(selected_events),
        projection=projection,
        projection_digest=compute_projection_digest(projection),
    )


def _position_in_candidates(
    position: SpatialPosition,
    candidates: tuple[SpatialPosition, ...],
) -> bool:
    for candidate in candidates:
        if (
            candidate.string_id == position.string_id
            and candidate.physical_fret_number == position.physical_fret_number
            and candidate.sounding_midi_note == position.sounding_midi_note
        ):
            return True
    return False
