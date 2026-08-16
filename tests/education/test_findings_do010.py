"""DO-010 Commit 2: deterministic pitch/timing/missing/extra findings."""

from __future__ import annotations

from master_all_strings.education.contracts import (
    PracticeEvaluationPolicyV1,
    PracticeFindingSeverity,
    PracticeFindingType,
)
from master_all_strings.education.evaluation import PracticeEvaluator
from master_all_strings.education.findings import (
    evaluate_extra_observed,
    evaluate_missing_expected,
    evaluate_pitch_findings,
    evaluate_timing_findings,
)
from master_all_strings.performance.contracts.alignment import (
    AlignedPerformanceEventV1,
    AlignmentStatus,
    PerformanceAlignmentPolicyV1,
    PerformanceAlignmentResultV1,
)


def _row(
    status: AlignmentStatus,
    *,
    expected: str | None = "ev-1",
    observed: str | None = "obs-1",
    rep: int = 0,
    timing: int | None = None,
    pitch: int | None = None,
    tick: int | None = 0,
) -> AlignedPerformanceEventV1:
    return AlignedPerformanceEventV1(
        status=status,
        expected_event_id=expected,
        observed_event_id=observed,
        repetition_index=rep,
        timing_delta_ms=timing,
        pitch_delta_semitones=pitch,
        expected_start_tick=tick,
    )


def _alignment(*rows: AlignedPerformanceEventV1) -> PerformanceAlignmentResultV1:
    return PerformanceAlignmentResultV1(
        schema_version="1.0.0",
        assignment_id="a1",
        content_id="c1",
        performance_session_id="p1",
        alignment_policy=PerformanceAlignmentPolicyV1(),
        aligned_events=rows,
        unmatched_expected_ids=(),
        unmatched_observed_ids=(),
    )


def test_late_and_early_threshold_boundaries() -> None:
    policy = PracticeEvaluationPolicyV1.mvp_defaults()
    late_below = evaluate_timing_findings(
        (_row(AlignmentStatus.MATCHED_EXACT_PITCH, timing=99),),
        policy,
    )
    late_at = evaluate_timing_findings(
        (_row(AlignmentStatus.MATCHED_EXACT_PITCH, timing=100),),
        policy,
    )
    late_above = evaluate_timing_findings(
        (_row(AlignmentStatus.MATCHED_EXACT_PITCH, timing=101),),
        policy,
    )
    assert late_below == ()
    assert late_at[0].finding_type is PracticeFindingType.LATE_ENTRY
    assert late_at[0].observed_value == 100.0
    assert late_above[0].observed_value == 101.0

    early_below = evaluate_timing_findings(
        (_row(AlignmentStatus.MATCHED_EXACT_PITCH, timing=-99),),
        policy,
    )
    early_at = evaluate_timing_findings(
        (_row(AlignmentStatus.MATCHED_EXACT_PITCH, timing=-100),),
        policy,
    )
    assert early_below == ()
    assert early_at[0].finding_type is PracticeFindingType.EARLY_ENTRY


def test_alignment_window_independence_late_finding() -> None:
    """A row may align under a 250ms window and still produce LATE_ENTRY at 100ms."""

    policy = PracticeEvaluationPolicyV1.mvp_defaults()
    findings = evaluate_timing_findings(
        (_row(AlignmentStatus.MATCHED_EXACT_PITCH, timing=142),),
        policy,
    )
    assert len(findings) == 1
    assert findings[0].finding_type is PracticeFindingType.LATE_ENTRY
    assert findings[0].threshold_value == 100.0
    assert findings[0].evidence_refs[0].startswith("aligned:")


def test_pitch_threshold_boundaries() -> None:
    policy = PracticeEvaluationPolicyV1.mvp_defaults()
    none = evaluate_pitch_findings(
        (_row(AlignmentStatus.MATCHED_EXACT_PITCH, pitch=0),),
        policy,
    )
    at = evaluate_pitch_findings(
        (_row(AlignmentStatus.MATCHED_PITCH_DIFFERENCE, pitch=1),),
        policy,
    )
    above = evaluate_pitch_findings(
        (_row(AlignmentStatus.MATCHED_PITCH_DIFFERENCE, pitch=2),),
        policy,
    )
    assert none == ()
    assert at[0].finding_type is PracticeFindingType.PITCH_DIFFERENCE
    assert above[0].severity is PracticeFindingSeverity.SIGNIFICANT


def test_missing_and_extra_always_traceable() -> None:
    missing = evaluate_missing_expected(
        (_row(AlignmentStatus.EXPECTED_NOT_OBSERVED, observed=None),)
    )
    assert missing[0].finding_type is PracticeFindingType.EXPECTED_NOTE_MISSING
    extras = evaluate_extra_observed(
        (
            _row(AlignmentStatus.OBSERVED_NOT_EXPECTED, expected=None, observed="obs-a"),
            _row(AlignmentStatus.OBSERVED_NOT_EXPECTED, expected=None, observed="obs-b"),
            _row(AlignmentStatus.OBSERVED_NOT_EXPECTED, expected=None, observed="obs-c"),
        )
    )
    assert len(extras) == 3
    assert all(f.finding_type is PracticeFindingType.UNEXPECTED_NOTE for f in extras)
    assert extras[0].severity is PracticeFindingSeverity.SIGNIFICANT


def test_isolated_extra_note_is_info() -> None:
    extras = evaluate_extra_observed(
        (_row(AlignmentStatus.OBSERVED_NOT_EXPECTED, expected=None, observed="obs-a"),)
    )
    assert extras[0].severity is PracticeFindingSeverity.INFO
    assert extras[0].is_actionable is False


def test_practice_evaluator_aggregates_all_dimensions() -> None:
    alignment = _alignment(
        _row(AlignmentStatus.MATCHED_EXACT_PITCH, timing=140),
        _row(AlignmentStatus.MATCHED_PITCH_DIFFERENCE, expected="ev-2", observed="obs-2", pitch=1),
        _row(AlignmentStatus.EXPECTED_NOT_OBSERVED, expected="ev-3", observed=None),
        _row(AlignmentStatus.OBSERVED_NOT_EXPECTED, expected=None, observed="obs-x"),
    )
    findings = PracticeEvaluator().evaluate_findings(alignment)
    types = {f.finding_type for f in findings}
    assert PracticeFindingType.LATE_ENTRY in types
    assert PracticeFindingType.PITCH_DIFFERENCE in types
    assert PracticeFindingType.EXPECTED_NOTE_MISSING in types
    assert PracticeFindingType.UNEXPECTED_NOTE in types
