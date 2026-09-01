"""DO-014 authority boundaries: no re-evaluation, no musical mutation."""

from __future__ import annotations

from pathlib import Path

from master_all_strings.core.projections.serialization import canonical_projection_digest
from master_all_strings.core.projections.tab import build_tab_projection
from master_all_strings.education.evaluation import PracticeEvaluator
from master_all_strings.education.guidance_builder import build_teaching_guidance_projection
from master_all_strings.lesson.canonicalization import build_authored_lesson_revision
from master_all_strings.lesson.resolver import resolve_lesson_assignment
from master_all_strings.mvp.demo_library import load_demo_assignment
from master_all_strings.performance.contracts.alignment import (
    AlignedPerformanceEventV1,
    AlignmentStatus,
    PerformanceAlignmentPolicyV1,
    PerformanceAlignmentResultV1,
)

REPO = Path(__file__).resolve().parents[2]


def _late_evaluation():
    alignment = PerformanceAlignmentResultV1(
        schema_version="1.0.0",
        assignment_id="assign-1",
        content_id="content-1",
        performance_session_id="session-authority",
        alignment_policy=PerformanceAlignmentPolicyV1(),
        aligned_events=(
            AlignedPerformanceEventV1(
                status=AlignmentStatus.MATCHED_EXACT_PITCH,
                expected_event_id="ev-1",
                observed_event_id="obs-1",
                repetition_index=0,
                timing_delta_ms=140,
                pitch_delta_semitones=0,
                expected_start_tick=0,
            ),
        ),
        unmatched_expected_ids=(),
        unmatched_observed_ids=(),
    )
    return PracticeEvaluator().evaluate(alignment)


def test_core_projections_do_not_import_education() -> None:
    offenders: list[str] = []
    root = REPO / "src" / "master_all_strings" / "core" / "projections"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "master_all_strings.education" in text:
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == []


def test_guidance_builder_does_not_import_score_projection_builders() -> None:
    source = (
        REPO / "src" / "master_all_strings" / "education" / "guidance_builder.py"
    ).read_text(encoding="utf-8")
    assert "build_tab_projection" not in source
    assert "build_notation_projection" not in source
    assert "master_all_strings.core.projections" not in source


def test_guidance_does_not_change_tab_digest_of_the_same_revision() -> None:
    assignment = load_demo_assignment("half_steps_one_string")
    revision = build_authored_lesson_revision(
        resolve_lesson_assignment(assignment),
        created_at=assignment.provenance.created_at_utc,
    ).revision
    tab = build_tab_projection(revision, instrument_profile_id="guitar-standard-6", selected={})
    digest_before = canonical_projection_digest(tab)
    evaluation = _late_evaluation()
    projection = build_teaching_guidance_projection(
        evaluation, canonical_revision_id=revision.revision_id
    )
    digest_after = canonical_projection_digest(tab)
    assert digest_before == digest_after
    assert projection.canonical_revision_id == revision.revision_id
    assert projection.guidance_digest != digest_before


def test_guidance_source_does_not_mint_event_ids() -> None:
    source = (REPO / "src" / "master_all_strings" / "education" / "guidance_builder.py").read_text(
        encoding="utf-8"
    )
    assert "event_id=" not in source or "canonical_event_id" in source
    evaluation = _late_evaluation()
    cited_by_engine = {
        ref for finding in evaluation.findings for ref in finding.expected_event_refs
    }
    projection = build_teaching_guidance_projection(
        evaluation, canonical_revision_id="rev-b85e77022251b045cfe38b7d"
    )
    projected = {item.canonical_event_id for item in projection.items if item.canonical_event_id}
    assert projected <= cited_by_engine
    assert all(not event_id.startswith("guide-") for event_id in projected)
