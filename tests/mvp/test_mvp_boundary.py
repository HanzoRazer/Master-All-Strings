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
