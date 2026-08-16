from __future__ import annotations

import json
from pathlib import Path

import pytest

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.spatial_mapping import instrument_profile_from_mapping
from master_all_strings.mvp.application import MvpApplication, load_default_instrument_catalog
from master_all_strings.mvp.errors import ProjectionBuildError
from master_all_strings.mvp.teaching_aids import (
    OneStringEventStatus,
    build_one_string_teaching_projection,
)

_GUITAR = Path("resources/instruments/examples/guitar-standard-6.json")


def _guitar():
    return instrument_profile_from_mapping(json.loads(_GUITAR.read_text(encoding="utf-8")))


def test_valid_passage_stays_entirely_on_requested_string() -> None:
    events = tuple(
        MusicalEvent(f"e-{note}", note, index * 480, 480)
        for index, note in enumerate((59, 60, 62))
    )

    result = build_one_string_teaching_projection(events, _guitar(), string_id="string-2")

    assert all(event.status is OneStringEventStatus.PLAYABLE for event in result.events)
    assert {event.requested_string_id for event in result.events} == {"string-2"}
    assert {event.display_order for event in result.events} == {4}


def test_impossible_note_is_explicit_and_never_jumps_strings() -> None:
    events = (MusicalEvent("too-low", 30, 0, 480), MusicalEvent("playable", 64, 480, 480))

    result = build_one_string_teaching_projection(events, _guitar(), string_id="string-1")

    assert result.events[0].status is OneStringEventStatus.UNPLAYABLE
    assert result.events[0].unresolved_reason == "unplayable_on_requested_string"
    assert result.events[0].physical_fret_number is None
    assert result.events[1].status is OneStringEventStatus.PLAYABLE
    assert result.events[1].requested_string_id == "string-1"


def test_unknown_requested_string_fails_explicitly() -> None:
    with pytest.raises(ProjectionBuildError, match="unknown one-string"):
        build_one_string_teaching_projection(
            (MusicalEvent("e", 60, 0, 480),), _guitar(), string_id="missing"
        )


def test_orchestration_preserves_normal_projection_and_exports_each_string() -> None:
    app = MvpApplication(instrument_profiles=load_default_instrument_catalog())
    response = app.run_demo("unplayable_note")

    assert len(response.one_string_teaching) == len(response.projection.instrument.lanes)
    assert response.projection.notes[0].string_id != "missing"
    assert any(
        event.status is OneStringEventStatus.UNPLAYABLE
        for teaching in response.one_string_teaching
        for event in teaching.events
    )
