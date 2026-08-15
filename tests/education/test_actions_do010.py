"""DO-010 Commit 3–4: passage focus, repetition, next-action precedence."""

from __future__ import annotations

from master_all_strings.education.contracts import (
    PracticeEvaluationPolicyV1,
    PracticeFindingSeverity,
    PracticeFindingType,
    PracticeFindingV1,
    PracticeNextActionType,
)
from master_all_strings.education.evaluation import PracticeEvaluator
from master_all_strings.education.passage_focus import cluster_findings_by_passage
from master_all_strings.education.recommendations import (
    build_next_actions,
    choose_primary_next_action,
    supported_slower_rate,
)
from master_all_strings.education.repetitions import compare_repetitions
from master_all_strings.performance.contracts.alignment import (
    AlignedPerformanceEventV1,
    AlignmentStatus,
    PerformanceAlignmentPolicyV1,
    PerformanceAlignmentResultV1,
)


def _finding(
    finding_id: str,
    *,
    finding_type: PracticeFindingType = PracticeFindingType.LATE_ENTRY,
    severity: PracticeFindingSeverity = PracticeFindingSeverity.FOCUS,
    tick: int | None = 0,
    repetition_index: int | None = 0,
    message_key: str | None = None,
) -> PracticeFindingV1:
    keys = {
        PracticeFindingType.LATE_ENTRY: "finding.late_entry",
        PracticeFindingType.EARLY_ENTRY: "finding.early_entry",
        PracticeFindingType.PITCH_DIFFERENCE: "finding.pitch_difference",
        PracticeFindingType.EXPECTED_NOTE_MISSING: "finding.expected_note_missing",
        PracticeFindingType.UNEXPECTED_NOTE: "finding.unexpected_note",
    }
    return PracticeFindingV1(
        schema_version=PracticeFindingV1.SCHEMA_VERSION,
        finding_id=finding_id,
        finding_type=finding_type,
        severity=severity,
        evidence_refs=(f"aligned:{finding_id}",),
        expected_event_refs=(f"ev-{finding_id}",) if tick is not None else (),
        message_key=message_key or keys[finding_type],
        repetition_index=repetition_index,
        focus_start_tick=tick,
        focus_end_tick=tick,
        observed_value=120.0,
        threshold_value=100.0,
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


def test_supported_slower_rate_mapping() -> None:
    assert supported_slower_rate(1.5) == 1.0
    assert supported_slower_rate(1.0) == 0.75
    assert supported_slower_rate(0.75) == 0.5
    assert supported_slower_rate(0.5) == 0.5


def test_isolate_requires_three_in_four_expected_event_window() -> None:
    policy = PracticeEvaluationPolicyV1.mvp_defaults()
    # Two findings inside four ticks — no isolate.
    below = (
        _finding("f1", tick=0),
        _finding("f2", tick=100),
    )
    assert cluster_findings_by_passage(below, policy) == ()

    # Three findings across four expected ticks — isolate.
    at = (
        _finding("f1", tick=0),
        _finding("f2", tick=100),
        _finding("f3", tick=200),
        _finding("f4", finding_type=PracticeFindingType.PITCH_DIFFERENCE, tick=900),
    )
    # Only first three are within a contiguous 4-tick window of {0,100,200,900}?
    # Ordered ticks: 0,100,200,900. Window [0,100,200,900] contains 4 findings.
    ranges = cluster_findings_by_passage(at, policy)
    assert len(ranges) == 1
    assert len(ranges[0].finding_ids) >= 3

    action = choose_primary_next_action(
        at,
        ranges,
        policy,
        expected_event_count=10,
    )
    assert action.action_type is PracticeNextActionType.ISOLATE_PASSAGE


def test_slow_down_ratio_threshold_boundaries() -> None:
    policy = PracticeEvaluationPolicyV1.mvp_defaults()
    # 2 timing/pitch findings / 10 expected = 0.20 < 0.30 → not slow-down alone.
    low = (_finding("a"), _finding("b"))
    action_low = choose_primary_next_action(
        low, (), policy, expected_event_count=10
    )
    assert action_low.action_type is PracticeNextActionType.REPEAT

    # 3 / 10 = 0.30 → SLOW_DOWN
    at = (_finding("a"), _finding("b"), _finding("c"))
    action_at = choose_primary_next_action(at, (), policy, expected_event_count=10)
    assert action_at.action_type is PracticeNextActionType.SLOW_DOWN
    assert action_at.target_rate == 0.75

    # 4 / 10 = 0.40 → SLOW_DOWN
    above = (_finding("a"), _finding("b"), _finding("c"), _finding("d"))
    action_above = choose_primary_next_action(above, (), policy, expected_event_count=10)
    assert action_above.action_type is PracticeNextActionType.SLOW_DOWN


def test_continue_requires_at_most_one_actionable_and_no_significant() -> None:
    policy = PracticeEvaluationPolicyV1.mvp_defaults()
    none = choose_primary_next_action((), (), policy, expected_event_count=8)
    assert none.action_type is PracticeNextActionType.CONTINUE

    one = choose_primary_next_action(
        (_finding("only"),), (), policy, expected_event_count=8
    )
    assert one.action_type is PracticeNextActionType.CONTINUE

    significant = choose_primary_next_action(
        (
            _finding(
                "sig",
                severity=PracticeFindingSeverity.SIGNIFICANT,
            ),
        ),
        (),
        policy,
        expected_event_count=8,
    )
    assert significant.action_type is PracticeNextActionType.REPEAT


def test_isolate_precedes_slow_down() -> None:
    policy = PracticeEvaluationPolicyV1.mvp_defaults()
    findings = (
        _finding("f1", tick=0),
        _finding("f2", tick=100),
        _finding("f3", tick=200),
    )
    ranges = cluster_findings_by_passage(findings, policy)
    primary, _secondary = build_next_actions(
        findings, ranges, policy, expected_event_count=3
    )
    assert primary.action_type is PracticeNextActionType.ISOLATE_PASSAGE


def test_repetition_improved_and_regressed() -> None:
    improved = compare_repetitions(
        (
            _finding("r0a", repetition_index=0),
            _finding("r0b", repetition_index=0),
            _finding("r1a", repetition_index=1),
        )
    )
    assert improved[0].finding_type is PracticeFindingType.REPETITION_IMPROVED

    regressed = compare_repetitions(
        (
            _finding("r0a", repetition_index=0),
            _finding("r1a", repetition_index=1),
            _finding("r1b", repetition_index=1),
        )
    )
    assert regressed[0].finding_type is PracticeFindingType.REPETITION_REGRESSED


def test_full_evaluator_produces_digest_and_summary() -> None:
    alignment = _alignment(
        _row(AlignmentStatus.MATCHED_EXACT_PITCH, timing=140, tick=0),
        _row(
            AlignmentStatus.MATCHED_PITCH_DIFFERENCE,
            expected="ev-2",
            observed="obs-2",
            pitch=1,
            tick=100,
        ),
        _row(
            AlignmentStatus.EXPECTED_NOT_OBSERVED,
            expected="ev-3",
            observed=None,
            tick=200,
        ),
        _row(
            AlignmentStatus.MATCHED_EXACT_PITCH,
            expected="ev-4",
            observed="obs-4",
            timing=0,
            tick=300,
        ),
        _row(
            AlignmentStatus.OBSERVED_NOT_EXPECTED,
            expected=None,
            observed="obs-x",
            tick=None,
        ),
    )
    result = PracticeEvaluator().evaluate(alignment)
    assert result.evaluation_digest.startswith("sha256:")
    assert result.primary_next_action.action_type is PracticeNextActionType.ISOLATE_PASSAGE
    assert result.summary.extra_count == 1
    assert any(f.finding_type is PracticeFindingType.UNEXPECTED_NOTE for f in result.findings)
    assert any(
        f.finding_type is PracticeFindingType.FINDINGS_CONCENTRATED for f in result.findings
    )
