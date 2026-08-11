"""MVP orchestration and unplayable soft-fail tests."""

from __future__ import annotations

from dataclasses import replace
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
    assert response.playback_plan.playback_digest.startswith("sha256:")
    assert response.practice_policy.assignment_id == response.projection.assignment_id


def test_practice_outputs_share_source_identity_and_canonical_events(
    app: MvpApplication,
) -> None:
    response = app.run_demo("ascending_scale")

    assert response.projection.assignment_id == response.playback_plan.assignment_id
    assert response.projection.content_id == response.playback_plan.content_id
    projected = {note.event_id: note for note in response.projection.notes}
    for event in response.playback_plan.events:
        assert projected[event.event_id].midi_note == event.midi_note
        assert projected[event.event_id].onset_seconds == event.onset_seconds


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
    assert response.playback_plan.events[1].midi_note == unplayable.midi_note


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


def test_teacher_override_changes_spatial_output_not_playback() -> None:
    from master_all_strings.mvp.application import load_default_instrument_catalog
    from master_all_strings.mvp.demo_library import load_demo_assignment
    from master_all_strings.mvp.orchestrator import MvpLessonOrchestrator

    overridden = load_demo_assignment("teacher_override")
    automatic = replace(overridden, teacher_overrides=())
    orchestrator = MvpLessonOrchestrator(load_default_instrument_catalog())

    automatic_result = orchestrator.load_assignment(automatic)
    override_result = orchestrator.load_assignment(overridden)
    assert automatic_result.projection.projection_digest != (
        override_result.projection.projection_digest
    )
    assert automatic_result.playback_plan.playback_digest == (
        override_result.playback_plan.playback_digest
    )


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


def test_boundary_errors_are_not_flattened(instrument_catalog) -> None:
    """MVP errors raised inside ``_run`` keep their type through ``load_assignment``."""

    import json

    from master_all_strings.mvp.errors import ProjectionBuildError
    from master_all_strings.mvp.orchestrator import MvpLessonOrchestrator

    path = Path("resources/mvp1/demo_lessons/assignments/ascending_scale.json")
    raw = json.loads(path.read_text(encoding="utf-8"))

    # Missing tempo surfaces the projection-build error verbatim, not a generic wrap.
    no_tempo = json.loads(json.dumps(raw))
    no_tempo["musical_content"]["tempo_changes"] = []
    no_tempo["playback"]["tempo_override"] = None
    orch = MvpLessonOrchestrator(instrument_catalog)
    with pytest.raises(ProjectionBuildError, match="tempo is required"):
        orch.load_assignment_json(no_tempo)

    # An unknown instrument stays an UnknownInstrumentError, not a load/build error.
    with pytest.raises(UnknownInstrumentError):
        orch.load_assignment_json(raw, instrument_profile_id="no-such-instrument")


def test_no_usable_events_stays_a_lesson_load_error(app: MvpApplication, monkeypatch) -> None:
    """``LessonLoadError`` from ``_run`` must not be rewritten as a build failure."""

    from master_all_strings.lesson.resolver import ResolvedLessonV1
    from master_all_strings.mvp import orchestrator as orchestrator_module
    from master_all_strings.mvp.errors import LessonLoadError

    real_resolve = orchestrator_module.resolve_lesson_assignment

    def _empty(assignment):
        resolved: ResolvedLessonV1 = real_resolve(assignment)
        return ResolvedLessonV1(
            **{
                **{f: getattr(resolved, f) for f in resolved.__dataclass_fields__},
                "events": (),
            }
        )

    monkeypatch.setattr(orchestrator_module, "resolve_lesson_assignment", _empty)
    with pytest.raises(LessonLoadError, match="No usable musical events"):
        app.run_demo("ascending_scale")
