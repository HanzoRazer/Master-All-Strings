"""Build FretboardScrollProjectionV1 from authoritative upstream results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.core.spatial_mapping import SpatialPosition
from master_all_strings.core.spatial_mapping.geometry import normalized_position_for_semitones
from master_all_strings.core.spatial_mapping.pitch import midi_note_to_pitch_label
from master_all_strings.instruments import InstrumentProfile
from master_all_strings.mvp.errors import ProjectionBuildError
from master_all_strings.mvp.projection.models import (
    FRETBOARD_SCROLL_PROJECTION_TYPE,
    FRETBOARD_SCROLL_PROJECTION_VERSION,
    FretboardInstrumentProjectionV1,
    FretboardLaneV1,
    FretboardProjectedNoteV1,
    FretboardScrollProjectionV1,
    FretProjectionV1,
    ProjectedNoteStatus,
    SelectionOrigin,
    ZoneSemanticProjectionV1,
)
from master_all_strings.mvp.projection.serialization import (
    compute_projection_digest,
    validate_projection,
)
from master_all_strings.mvp.projection.timeline import (
    build_projected_timeline,
    event_time_bounds,
    project_tempo_changes,
)

__all__ = ["SelectedNoteInput", "build_fretboard_scroll_projection", "build_instrument_projection"]


class SelectedNoteInput:
    """One event's authoritative selection outcome for projection building."""

    __slots__ = ("event", "position", "selection_origin", "unresolved_reason")

    def __init__(
        self,
        event: MusicalEvent,
        *,
        position: SpatialPosition | None = None,
        selection_origin: SelectionOrigin | None = None,
        unresolved_reason: str | None = None,
    ) -> None:
        if position is None:
            if selection_origin is not None:
                raise ProjectionBuildError(
                    "unresolved selection must not carry a selection_origin"
                )
            if unresolved_reason is None or not str(unresolved_reason).strip():
                raise ProjectionBuildError("unresolved selection requires unresolved_reason")
        else:
            if unresolved_reason is not None:
                raise ProjectionBuildError("resolved selection must not carry unresolved_reason")
            if selection_origin is None:
                raise ProjectionBuildError("resolved selection requires a selection_origin")
        self.event = event
        self.position = position
        self.selection_origin = selection_origin
        self.unresolved_reason = unresolved_reason


def build_instrument_projection(instrument: InstrumentProfile) -> FretboardInstrumentProjectionV1:
    lanes = tuple(
        FretboardLaneV1(
            string_id=string.string_id,
            display_label=string.display_label,
            display_order=string.display_order,
            open_midi_note=string.open_midi_note,
            open_pitch_label=midi_note_to_pitch_label(string.open_midi_note),
        )
        for string in sorted(instrument.strings, key=lambda item: item.display_order)
    )
    # Lane identity/order must be unambiguous: the renderer places notes by
    # string_id and stacks lanes by display_order.
    if len({lane.string_id for lane in lanes}) != len(lanes):
        raise ProjectionBuildError("instrument lanes must have unique string_id values")
    if len({lane.display_order for lane in lanes}) != len(lanes):
        raise ProjectionBuildError("instrument lanes must have unique display_order values")
    fret_count = instrument.physical_fret_count or 0
    marker_by_fret = {
        int(marker.semitone_offset): marker.label
        for marker in instrument.reference_markers
        if abs(marker.semitone_offset - round(marker.semitone_offset)) < 1e-9
    }
    frets = tuple(
        FretProjectionV1(
            fret_number=fret,
            normalized_position=normalized_position_for_semitones(float(fret)),
            marker_label=marker_by_fret.get(fret),
        )
        for fret in range(0, fret_count + 1)
    )
    return FretboardInstrumentProjectionV1(
        instrument_id=instrument.instrument_id,
        display_name=instrument.display_name,
        fingerboard_mode=str(instrument.fingerboard_mode.value),
        scale_length_mm=instrument.scale_length_mm,
        lanes=lanes,
        frets=frets,
    )


def build_fretboard_scroll_projection(
    *,
    assignment_id: str,
    content_id: str,
    title: str,
    description: str | None,
    objective: str | None,
    teacher_note: str | None,
    ticks_per_quarter: int,
    tempo_map: Sequence[TempoChangeV1],
    instrument: InstrumentProfile,
    selection_policy: str,
    selected_notes: Sequence[SelectedNoteInput],
    warnings: Sequence[str] = (),
    unsupported_features: Sequence[str] = (),
    zone_semantics_by_event: Mapping[str, ZoneSemanticProjectionV1] | None = None,
) -> FretboardScrollProjectionV1:
    """Compose display projection. Performs no candidate ranking or selection."""

    if not selected_notes:
        raise ProjectionBuildError("projection requires at least one musical event")

    events = tuple(item.event for item in selected_notes)
    semantic_map = zone_semantics_by_event or {}
    event_ids = {event.event_id for event in events}
    unexpected_semantics = sorted(set(semantic_map) - event_ids)
    if unexpected_semantics:
        raise ProjectionBuildError(
            f"Zone semantics reference unknown projected events: {unexpected_semantics}"
        )
    timeline = build_projected_timeline(
        events,
        ticks_per_quarter=ticks_per_quarter,
        tempo_map=tempo_map,
    )
    bounds = event_time_bounds(
        events,
        ticks_per_quarter=ticks_per_quarter,
        tempo_map=tempo_map,
    )
    lane_ids = {lane.string_id for lane in instrument.strings}
    notes: list[FretboardProjectedNoteV1] = []
    for item, (onset_seconds, release_seconds) in zip(selected_notes, bounds, strict=True):
        event = item.event
        pitch_label = midi_note_to_pitch_label(event.midi_note, cents_offset=event.cents_offset)
        if item.position is None:
            notes.append(
                FretboardProjectedNoteV1(
                    event_id=event.event_id,
                    status=ProjectedNoteStatus.UNPLAYABLE,
                    midi_note=event.midi_note,
                    pitch_label=pitch_label,
                    onset_tick=event.start_tick,
                    duration_ticks=event.duration_ticks,
                    onset_seconds=onset_seconds,
                    release_seconds=release_seconds,
                    unresolved_reason=item.unresolved_reason or "no_playable_position",
                    zone_semantics=semantic_map.get(event.event_id),
                )
            )
            continue
        position = item.position
        if position.string_id not in lane_ids:
            raise ProjectionBuildError(
                f"selected string_id {position.string_id!r} is not on the instrument"
            )
        if position.physical_fret_number is None:
            raise ProjectionBuildError("selected fretted positions require physical_fret_number")
        notes.append(
            FretboardProjectedNoteV1(
                event_id=event.event_id,
                status=ProjectedNoteStatus.SELECTED,
                midi_note=event.midi_note,
                pitch_label=pitch_label,
                onset_tick=event.start_tick,
                duration_ticks=event.duration_ticks,
                onset_seconds=onset_seconds,
                release_seconds=release_seconds,
                lane_display_order=position.display_order,
                string_id=position.string_id,
                fret_number=position.physical_fret_number,
                relative_semitone_position=position.relative_semitone_position,
                normalized_position=position.normalized_position,
                is_open_string=position.is_open_string,
                selection_origin=item.selection_origin or SelectionOrigin.AUTOMATIC,
                zone_semantics=semantic_map.get(event.event_id),
            )
        )

    instrument_projection = build_instrument_projection(instrument)
    draft = FretboardScrollProjectionV1(
        schema_version="1.0.0",
        projection_type=FRETBOARD_SCROLL_PROJECTION_TYPE,
        projection_version=FRETBOARD_SCROLL_PROJECTION_VERSION,
        fidelity="selected_spatial_v1",
        projection_digest="pending",
        assignment_id=assignment_id,
        content_id=content_id,
        title=title,
        timeline=timeline,
        tempo_changes=project_tempo_changes(tempo_map),
        instrument=instrument_projection,
        selection_policy=selection_policy,
        notes=tuple(notes),
        warnings=tuple(warnings),
        unsupported_features=tuple(unsupported_features),
        description=description,
        objective=objective,
        teacher_note=teacher_note,
    )
    # The build path is held to the same relational contract as the delivery path.
    validate_projection(draft)
    digest = compute_projection_digest(draft)
    final = FretboardScrollProjectionV1(
        schema_version=draft.schema_version,
        projection_type=draft.projection_type,
        projection_version=draft.projection_version,
        fidelity=draft.fidelity,
        projection_digest=digest,
        assignment_id=draft.assignment_id,
        content_id=draft.content_id,
        title=draft.title,
        timeline=draft.timeline,
        tempo_changes=draft.tempo_changes,
        instrument=draft.instrument,
        selection_policy=draft.selection_policy,
        notes=draft.notes,
        warnings=draft.warnings,
        unsupported_features=draft.unsupported_features,
        description=draft.description,
        objective=draft.objective,
        teacher_note=draft.teacher_note,
    )
    return final
