"""MVP boundary rulings: soft unplayable vs lesson.pipeline hard-fail; tempo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from master_all_strings.lesson.errors import LessonValidationError
from master_all_strings.lesson.pipeline import run_mvp_lesson_pipeline
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.errors import ProjectionBuildError
from master_all_strings.mvp.orchestrator import MvpLessonOrchestrator
from master_all_strings.mvp.projection.models import ProjectedNoteStatus
from master_all_strings.mvp.projection.timeline import build_core_tempo_map


def test_lesson_pipeline_still_hard_fails_on_unplayable(instrument_catalog) -> None:
    path = Path("resources/mvp1/demo_lessons/assignments/unplayable_note.json")
    assignment = deserialize_lesson_assignment(path.read_text(encoding="utf-8"))
    with pytest.raises(LessonValidationError, match="no MSME candidates"):
        run_mvp_lesson_pipeline(assignment, instrument_profiles=instrument_catalog)


def test_mvp_orchestrator_soft_fails_unplayable(app: MvpApplication) -> None:
    response = app.run_demo("unplayable_note")
    assert any(note.status is ProjectedNoteStatus.UNPLAYABLE for note in response.projection.notes)
    assert any(note.status is ProjectedNoteStatus.SELECTED for note in response.projection.notes)


def test_missing_tempo_rejected(instrument_catalog) -> None:
    path = Path("resources/mvp1/demo_lessons/assignments/ascending_scale.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["musical_content"]["tempo_changes"] = []
    raw["playback"]["tempo_override"] = None
    orch = MvpLessonOrchestrator(instrument_catalog)
    with pytest.raises(ProjectionBuildError, match="tempo is required"):
        orch.load_assignment_json(raw)


def test_build_core_tempo_map_requires_source_or_override() -> None:
    with pytest.raises(ProjectionBuildError, match="refusing to assume"):
        build_core_tempo_map(tempo_override_bpm=None, source_tempo_changes=())


def test_tempo_override_wins() -> None:
    tempo = build_core_tempo_map(
        tempo_override_bpm=90.0,
        source_tempo_changes=((0, 120.0),),
    )
    assert len(tempo) == 1
    assert tempo[0].beats_per_minute == pytest.approx(90.0)


def test_build_core_tempo_map_is_input_order_independent() -> None:
    """Tick-0 coverage is decided by the earliest tick, never by input order."""

    ordered = build_core_tempo_map(
        tempo_override_bpm=None,
        source_tempo_changes=((0, 120.0), (480, 90.0), (960, 60.0)),
    )
    shuffled = build_core_tempo_map(
        tempo_override_bpm=None,
        source_tempo_changes=((960, 60.0), (0, 120.0), (480, 90.0)),
    )
    assert ordered == shuffled
    assert [change.tick for change in shuffled] == [0, 480, 960]


def test_build_core_tempo_map_does_not_duplicate_tick_zero() -> None:
    """An out-of-order tick-0 tempo must not get a synthetic duplicate prepended."""

    changes = build_core_tempo_map(
        tempo_override_bpm=None,
        source_tempo_changes=((480, 90.0), (0, 120.0)),
    )
    ticks = [change.tick for change in changes]
    assert ticks == [0, 480]
    assert ticks.count(0) == 1
    assert changes[0].beats_per_minute == pytest.approx(120.0)


def test_build_core_tempo_map_synthesizes_tick_zero_from_earliest() -> None:
    changes = build_core_tempo_map(
        tempo_override_bpm=None,
        source_tempo_changes=((960, 60.0), (480, 90.0)),
    )
    assert [change.tick for change in changes] == [0, 480, 960]
    # The synthetic leading tempo carries the earliest declared value, not the
    # first tuple in input order.
    assert changes[0].beats_per_minute == pytest.approx(90.0)


def test_build_core_tempo_map_rejects_negative_ticks() -> None:
    with pytest.raises(ProjectionBuildError, match="non-negative"):
        build_core_tempo_map(tempo_override_bpm=None, source_tempo_changes=((-1, 120.0),))
