"""Error mapping, JSON load, and serialization edge cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.demo_library import load_demo_assignment, load_demo_manifest
from master_all_strings.mvp.errors import (
    LessonLoadError,
    ProjectionBuildError,
    UnsupportedMidiError,
    UnsupportedProjectionVersionError,
    format_mvp_error,
)
from master_all_strings.mvp.orchestrator import MvpLessonOrchestrator
from master_all_strings.mvp.projection.models import (
    FretboardLaneV1,
    FretboardTimelineV1,
    FretProjectionV1,
    TempoChangeProjectionV1,
)
from master_all_strings.mvp.projection.serialization import (
    deserialize_fretboard_projection,
    serialize_fretboard_projection,
    to_dict,
    validate_projection,
)


def test_format_mvp_error_mapping() -> None:
    assert format_mvp_error(LessonLoadError("x")) == "x"
    assert "MIDI" in format_mvp_error(RuntimeError("bad midi tempo meta"))
    assert "instrument" in format_mvp_error(RuntimeError("unknown instrument id")).lower()
    assert format_mvp_error(RuntimeError("schema boom")) == "Invalid lesson"
    assert format_mvp_error(RuntimeError("projection failed")) == "Internal projection failure"
    assert (
        format_mvp_error(RuntimeError("no note content missing_content"))
        == "No usable musical events"
    )
    assert format_mvp_error(RuntimeError("something else")) == "Unable to load lesson"


def test_load_assignment_json_and_invalid(app: MvpApplication, instrument_catalog) -> None:
    path = Path("resources/mvp1/demo_lessons/assignments/open_strings.json")
    text = path.read_text(encoding="utf-8")
    response = app.run_assignment_json(text)
    assert response.projection.notes

    orch = MvpLessonOrchestrator(instrument_catalog)
    with pytest.raises(LessonLoadError):
        orch.load_assignment_json("{not-json")


def test_unsupported_midi(app: MvpApplication) -> None:
    with pytest.raises(UnsupportedMidiError):
        app.run_midi(b"not-a-midi-file", instrument_profile_id="guitar-standard-6")


def test_unknown_demo() -> None:
    with pytest.raises(LessonLoadError, match="Unknown demo"):
        load_demo_assignment("no-such-demo")


def test_deserialize_rejects_bad_version(app: MvpApplication) -> None:
    projection = app.run_demo("ascending_scale").projection
    data = json.loads(serialize_fretboard_projection(projection))
    data["projection_version"] = "9.9.9"
    with pytest.raises(UnsupportedProjectionVersionError):
        deserialize_fretboard_projection(data)
    with pytest.raises(ProjectionBuildError):
        to_dict("not-a-projection")  # type: ignore[arg-type]


def test_validate_projection_type_gate(app: MvpApplication) -> None:
    projection = app.run_demo("ascending_scale").projection
    validate_projection(projection)
    broken = json.loads(serialize_fretboard_projection(projection))
    broken["projection_type"] = "other"
    restored = deserialize_fretboard_projection(
        {**broken, "projection_type": "fretboard_scroll"}
    )
    # Force type mismatch after construction via object.__setattr__ not available;
    # exercise UnsupportedProjectionVersionError path through validate_projection helper.
    from dataclasses import replace

    with pytest.raises(UnsupportedProjectionVersionError):
        validate_projection(replace(restored, projection_type="not-fretboard"))


def test_model_validation_edges() -> None:
    with pytest.raises(ProjectionBuildError):
        TempoChangeProjectionV1(tick=0, tempo_bpm=100.0, microseconds_per_quarter=True)  # type: ignore[arg-type]
    with pytest.raises(ProjectionBuildError):
        FretboardTimelineV1(
            ticks_per_quarter=0,
            total_ticks=0,
            total_seconds=0.0,
            seconds_per_screen=4.0,
            play_line_fraction=0.2,
        )
    with pytest.raises(ProjectionBuildError):
        FretboardTimelineV1(
            ticks_per_quarter=480,
            total_ticks=0,
            total_seconds=0.0,
            seconds_per_screen=4.0,
            play_line_fraction=1.5,
        )
    lane = FretboardLaneV1(
        string_id="s1",
        display_label="E",
        display_order=0,
        open_midi_note=40,
        open_pitch_label="E2",
    )
    assert lane.string_id == "s1"
    fret = FretProjectionV1(fret_number=0, normalized_position=0.0, marker_label=None)
    assert fret.fret_number == 0


def test_manifest_has_ten_demos() -> None:
    assert len(load_demo_manifest()) == 10
