"""Projection contract tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.errors import ProjectionBuildError
from master_all_strings.mvp.projection.models import (
    FretboardProjectedNoteV1,
    ProjectedNoteStatus,
    SelectionOrigin,
)
from master_all_strings.mvp.projection.serialization import (
    compute_projection_digest,
    deserialize_fretboard_projection,
    serialize_fretboard_projection,
    validate_projection,
    verify_projection_digest,
)


def test_round_trip(app: MvpApplication) -> None:
    projection = app.run_demo("open_strings").projection
    restored = deserialize_fretboard_projection(serialize_fretboard_projection(projection))
    assert restored.projection_digest == projection.projection_digest
    assert compute_projection_digest(restored) == projection.projection_digest


def test_unplayable_rejects_spatial_fields() -> None:
    with pytest.raises(ProjectionBuildError):
        FretboardProjectedNoteV1(
            event_id="e",
            status=ProjectedNoteStatus.UNPLAYABLE,
            midi_note=30,
            pitch_label="F#1",
            onset_tick=0,
            duration_ticks=120,
            onset_seconds=0.0,
            release_seconds=0.5,
            string_id="string-1",
            unresolved_reason="no_playable_position",
        )


def test_release_before_onset_rejected() -> None:
    with pytest.raises(ProjectionBuildError, match="release_seconds"):
        FretboardProjectedNoteV1(
            event_id="e",
            status=ProjectedNoteStatus.UNPLAYABLE,
            midi_note=30,
            pitch_label="F#1",
            onset_tick=0,
            duration_ticks=120,
            onset_seconds=1.0,
            release_seconds=0.5,
            unresolved_reason="no_playable_position",
        )


def _selected_note(app, demo_id: str = "ascending_scale"):
    projection = app.run_demo(demo_id).projection
    note = next(n for n in projection.notes if n.status is ProjectedNoteStatus.SELECTED)
    return projection, note


def test_validate_rejects_lane_display_order_disagreement(app) -> None:
    projection, note = _selected_note(app)
    broken = replace(
        projection,
        notes=tuple(
            replace(n, lane_display_order=n.lane_display_order + 10)
            if n is note
            else n
            for n in projection.notes
        ),
    )
    with pytest.raises(ProjectionBuildError, match="disagrees with lane"):
        validate_projection(broken)


def test_validate_rejects_fret_not_on_instrument(app) -> None:
    projection, note = _selected_note(app)
    off_neck = max(fret.fret_number for fret in projection.instrument.frets) + 5
    broken = replace(
        projection,
        notes=tuple(
            replace(n, fret_number=off_neck, is_open_string=False) if n is note else n
            for n in projection.notes
        ),
    )
    with pytest.raises(ProjectionBuildError, match="is not on the instrument"):
        validate_projection(broken)


def test_validate_rejects_note_past_timeline_end(app) -> None:
    projection, note = _selected_note(app)
    broken = replace(
        projection,
        timeline=replace(projection.timeline, total_ticks=1, total_seconds=0.001),
    )
    with pytest.raises(ProjectionBuildError, match="beyond timeline total_ticks"):
        validate_projection(broken)


def test_validate_rejects_duplicate_event_ids(app) -> None:
    projection, _ = _selected_note(app)
    first = projection.notes[0]
    duplicate = replace(projection.notes[1], event_id=first.event_id)
    broken = replace(projection, notes=(first, duplicate))
    with pytest.raises(ProjectionBuildError, match="duplicate event_id"):
        validate_projection(broken)


def test_model_rejects_unsorted_or_duplicated_tempo_ticks(app) -> None:
    projection, _ = _selected_note(app)
    first = projection.tempo_changes[0]
    with pytest.raises(ProjectionBuildError, match="strictly increasing"):
        replace(projection, tempo_changes=(first, first))


def test_model_rejects_empty_notes(app) -> None:
    projection, _ = _selected_note(app)
    with pytest.raises(ProjectionBuildError, match="at least one note"):
        replace(projection, notes=())


def test_selected_note_input_rejects_invalid_states(app) -> None:
    from master_all_strings.mvp.projection.builder import SelectedNoteInput

    event = object()
    with pytest.raises(ProjectionBuildError, match="requires unresolved_reason"):
        SelectedNoteInput(event)  # type: ignore[arg-type]
    with pytest.raises(ProjectionBuildError, match="must not carry unresolved_reason"):
        SelectedNoteInput(
            event,  # type: ignore[arg-type]
            position=object(),  # type: ignore[arg-type]
            selection_origin=SelectionOrigin.AUTOMATIC,
            unresolved_reason="nope",
        )
    with pytest.raises(ProjectionBuildError, match="requires a selection_origin"):
        SelectedNoteInput(event, position=object())  # type: ignore[arg-type]
    with pytest.raises(ProjectionBuildError, match="must not carry a selection_origin"):
        SelectedNoteInput(
            event,  # type: ignore[arg-type]
            selection_origin=SelectionOrigin.AUTOMATIC,
            unresolved_reason="no_playable_position",
        )


def test_digest_verification_detects_tampering(app) -> None:
    projection = app.run_demo("ascending_scale").projection
    with pytest.raises(ProjectionBuildError, match="does not match projection content"):
        verify_projection_digest(replace(projection, selection_policy="tampered"))
