"""MVP orchestration and unplayable soft-fail tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from master_all_strings.lesson.models import LessonRoutingV1
from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.errors import UnknownInstrumentError
from master_all_strings.mvp.projection.models import ProjectedNoteStatus, SelectionOrigin


def test_demo_runs_to_projection(app: MvpApplication) -> None:
    response = app.run_demo("ascending_scale")
    assert response.projection.notes
    assert response.projection.projection_digest.startswith("sha256:")


def test_mixed_playable_unplayable(app: MvpApplication) -> None:
    response = app.run_demo("unplayable_note")
    statuses = [note.status for note in response.projection.notes]
    assert statuses == [
        ProjectedNoteStatus.SELECTED,
        ProjectedNoteStatus.UNPLAYABLE,
        ProjectedNoteStatus.SELECTED,
    ]
    unplayable = response.projection.notes[1]
    assert unplayable.string_id is None
    assert unplayable.fret_number is None
    assert unplayable.unresolved_reason


def test_unknown_instrument_rejected(app: MvpApplication) -> None:
    with pytest.raises(UnknownInstrumentError):
        app.run_demo("ascending_scale", instrument_profile_id="no-such-instrument")


def test_teacher_override_origin(app: MvpApplication) -> None:
    automatic = app.run_demo("multiple_candidates")
    override = app.run_demo("teacher_override")
    assert automatic.projection.notes[0].selection_origin is SelectionOrigin.AUTOMATIC
    assert override.projection.notes[0].selection_origin is SelectionOrigin.TEACHER_OVERRIDE
    assert override.projection.notes[0].string_id == "string-2"
    assert override.projection.notes[0].fret_number == 5


def test_routing_neutrality(app: MvpApplication, instrument_catalog) -> None:
    from master_all_strings.lesson.serialization import deserialize_lesson_assignment
    from master_all_strings.mvp.orchestrator import MvpLessonOrchestrator

    path = Path("resources/mvp1/demo_lessons/assignments/ascending_scale.json")
    base = deserialize_lesson_assignment(path.read_text(encoding="utf-8"))
    routed = deserialize_lesson_assignment(path.read_text(encoding="utf-8"))
    # Rebuild with routing via serialize path using model copy
    from master_all_strings.lesson.models import LessonAssignmentV1

    routed = LessonAssignmentV1(
        schema_id=base.schema_id,
        schema_version=base.schema_version,
        identity=base.identity,
        musical_content=base.musical_content,
        playback=base.playback,
        spatial_guidance=base.spatial_guidance,
        teacher_overrides=base.teacher_overrides,
        instruction=base.instruction,
        assessment=base.assessment,
        provenance=base.provenance,
        routing=LessonRoutingV1("sender", "recipient", "room"),
    )
    orch = MvpLessonOrchestrator(instrument_catalog)
    a = orch.load_assignment(base).projection.projection_digest
    b = orch.load_assignment(routed).projection.projection_digest
    assert a == b


def test_midi_import_path(app: MvpApplication) -> None:
    midi = Path("resources/mvp1/demo_lessons/midi/ascending_scale.mid").read_bytes()
    response = app.run_midi(
        midi,
        instrument_profile_id="guitar-standard-6",
        source_name="ascending_scale.mid",
    )
    assert len(response.projection.notes) == 8


def test_determinism(app: MvpApplication) -> None:
    a = app.run_demo("position_shift")
    b = app.run_demo("position_shift")
    assert a.projection.projection_digest == b.projection.projection_digest
    assert a.behavior_digest == b.behavior_digest
