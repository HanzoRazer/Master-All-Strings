"""Projection contract tests."""

from __future__ import annotations

import pytest

from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.errors import ProjectionBuildError
from master_all_strings.mvp.projection.models import FretboardProjectedNoteV1, ProjectedNoteStatus
from master_all_strings.mvp.projection.serialization import (
    compute_projection_digest,
    deserialize_fretboard_projection,
    serialize_fretboard_projection,
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
