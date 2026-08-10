"""Release-critical routing neutrality invariants."""

from __future__ import annotations

from master_all_strings.lesson.models import LessonAssignmentV1, LessonRoutingV1
from master_all_strings.lesson.pipeline import run_mvp_lesson_pipeline
from master_all_strings.lesson.resolver import resolve_lesson_assignment
from master_all_strings.lesson.serialization import compute_lesson_behavior_digest


def _with_routing(
    assignment: LessonAssignmentV1,
    routing: LessonRoutingV1 | None,
) -> LessonAssignmentV1:
    return LessonAssignmentV1(
        schema_id=assignment.schema_id,
        schema_version=assignment.schema_version,
        identity=assignment.identity,
        musical_content=assignment.musical_content,
        playback=assignment.playback,
        spatial_guidance=assignment.spatial_guidance,
        teacher_overrides=assignment.teacher_overrides,
        instruction=assignment.instruction,
        assessment=assignment.assessment,
        provenance=assignment.provenance,
        routing=routing,
    )


def _behavior_snapshot(result) -> tuple:
    return (
        result.resolved.events,
        tuple(item.candidates for item in result.selected_events),
        tuple(item.position for item in result.selected_events),
        result.projection_digest,
        tuple(
            (n.event_id, n.string_id, n.physical_fret_number, n.start_tick)
            for n in result.projection.notes
        ),
    )


def test_routing_absent_vs_populated_identical(
    minimal_assignment: LessonAssignmentV1,
    instrument_catalog: dict,
) -> None:
    a = _with_routing(minimal_assignment, None)
    b = _with_routing(
        minimal_assignment,
        LessonRoutingV1("sender", "recipient", "classroom"),
    )
    ra = run_mvp_lesson_pipeline(a, instrument_profiles=instrument_catalog)
    rb = run_mvp_lesson_pipeline(b, instrument_profiles=instrument_catalog)
    assert _behavior_snapshot(ra) == _behavior_snapshot(rb)
    assert compute_lesson_behavior_digest(a) == compute_lesson_behavior_digest(b)
    assert resolve_lesson_assignment(a).events == resolve_lesson_assignment(b).events


def test_change_only_recipient_identical(
    minimal_assignment: LessonAssignmentV1,
    instrument_catalog: dict,
) -> None:
    a = _with_routing(minimal_assignment, LessonRoutingV1("s", "r1", "c"))
    b = _with_routing(minimal_assignment, LessonRoutingV1("s", "r2", "c"))
    assert _behavior_snapshot(
        run_mvp_lesson_pipeline(a, instrument_profiles=instrument_catalog)
    ) == _behavior_snapshot(run_mvp_lesson_pipeline(b, instrument_profiles=instrument_catalog))


def test_remove_routing_identical(
    minimal_assignment: LessonAssignmentV1,
    instrument_catalog: dict,
) -> None:
    a = _with_routing(minimal_assignment, LessonRoutingV1("s", "r", "c"))
    b = _with_routing(minimal_assignment, None)
    assert _behavior_snapshot(
        run_mvp_lesson_pipeline(a, instrument_profiles=instrument_catalog)
    ) == _behavior_snapshot(run_mvp_lesson_pipeline(b, instrument_profiles=instrument_catalog))
