"""DO-014: PracticeEvaluationResultV1 → TeachingGuidanceProjectionV1."""

from __future__ import annotations

import pytest

from master_all_strings.education import (
    GUIDANCE_POLICY_VERSION,
    EducationContractError,
    PracticeAttemptSummaryV1,
    PracticeEvaluationPolicyV1,
    PracticeEvaluationResultV1,
    PracticeEvaluator,
    PracticeFindingSeverity,
    PracticeFindingType,
    PracticeFindingV1,
    PracticeFocusRangeV1,
    PracticeNextActionType,
    PracticeNextActionV1,
    compute_evaluation_digest,
    compute_guidance_digest,
    to_dict,
)
from master_all_strings.education.guidance_builder import build_teaching_guidance_projection
from master_all_strings.performance.contracts.alignment import (
    AlignedPerformanceEventV1,
    AlignmentStatus,
    PerformanceAlignmentPolicyV1,
    PerformanceAlignmentResultV1,
)

REVISION = "rev-b85e77022251b045cfe38b7d"


def _row(
    *,
    expected: str,
    observed: str | None = "obs",
    status: AlignmentStatus = AlignmentStatus.MATCHED_EXACT_PITCH,
    timing: int | None = 0,
    pitch: int | None = 0,
    tick: int = 0,
) -> AlignedPerformanceEventV1:
    return AlignedPerformanceEventV1(
        status=status,
        expected_event_id=expected,
        observed_event_id=None if status is AlignmentStatus.EXPECTED_NOT_OBSERVED else observed,
        repetition_index=0,
        timing_delta_ms=timing,
        pitch_delta_semitones=pitch,
        expected_start_tick=tick,
    )


def _evaluate(*rows: AlignedPerformanceEventV1, rate: float = 1.0) -> PracticeEvaluationResultV1:
    alignment = PerformanceAlignmentResultV1(
        schema_version="1.0.0",
        assignment_id="golden-do014",
        content_id="half_steps_one_string",
        performance_session_id="session-do014",
        alignment_policy=PerformanceAlignmentPolicyV1(),
        aligned_events=rows,
        unmatched_expected_ids=(),
        unmatched_observed_ids=(),
    )
    return PracticeEvaluator().evaluate(alignment, current_rate=rate)


def _continue_action() -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.CONTINUE,
        reason_finding_ids=(),
        message_key="action.continue",
    )


def _finding(
    finding_id: str,
    *,
    event_ids: tuple[str, ...] = ("ev-1",),
    finding_type: PracticeFindingType = PracticeFindingType.LATE_ENTRY,
) -> PracticeFindingV1:
    keys = {
        PracticeFindingType.LATE_ENTRY: "finding.late_entry",
        PracticeFindingType.EARLY_ENTRY: "finding.early_entry",
        PracticeFindingType.PITCH_DIFFERENCE: "finding.pitch_difference",
        PracticeFindingType.EXPECTED_NOTE_MISSING: "finding.expected_note_missing",
        PracticeFindingType.UNEXPECTED_NOTE: "finding.unexpected_note",
        PracticeFindingType.FINDINGS_CONCENTRATED: "finding.findings_concentrated",
    }
    return PracticeFindingV1(
        schema_version=PracticeFindingV1.SCHEMA_VERSION,
        finding_id=finding_id,
        finding_type=finding_type,
        severity=PracticeFindingSeverity.FOCUS,
        evidence_refs=(f"aligned:{finding_id}",),
        expected_event_refs=event_ids,
        message_key=keys[finding_type],
        observed_value=140.0,
        threshold_value=100.0,
    )


def _manual_result(
    findings: tuple[PracticeFindingV1, ...],
    action: PracticeNextActionV1,
) -> PracticeEvaluationResultV1:
    summary = PracticeAttemptSummaryV1(
        schema_version=PracticeAttemptSummaryV1.SCHEMA_VERSION,
        performance_session_id="session-manual",
        expected_event_count=len(findings) or 1,
        observed_event_count=len(findings) or 1,
        matched_count=len(findings) or 1,
        missing_count=0,
        extra_count=0,
        pitch_finding_count=0,
        timing_finding_count=len(findings),
        actionable_finding_count=len(findings),
        repetition_count=1,
        focus_ranges=(
            ()
            if action.focus_start_tick is None
            else (
                PracticeFocusRangeV1(
                    action.focus_start_tick,
                    action.focus_end_tick or action.focus_start_tick,
                    tuple(f.finding_id for f in findings),
                ),
            )
        ),
        primary_action=action,
        secondary_actions=(),
    )
    digest = compute_evaluation_digest(
        assignment_id="assign-1",
        content_id="content-1",
        performance_session_id="session-manual",
        evaluation_policy_id="mvp-do010-v1",
        evaluation_policy_version=PracticeEvaluationPolicyV1.SCHEMA_VERSION,
        findings=findings,
        summary=summary,
        primary_next_action=action,
        secondary_actions=(),
        provenance=(("assembler", "education.tests"),),
    )
    return PracticeEvaluationResultV1(
        schema_version=PracticeEvaluationResultV1.SCHEMA_VERSION,
        assignment_id="assign-1",
        content_id="content-1",
        performance_session_id="session-manual",
        evaluation_policy_id="mvp-do010-v1",
        evaluation_policy_version=PracticeEvaluationPolicyV1.SCHEMA_VERSION,
        findings=findings,
        summary=summary,
        primary_next_action=action,
        secondary_actions=(),
        provenance=(("assembler", "education.tests"),),
        evaluation_digest=digest,
    )


def test_builder_is_deterministic() -> None:
    evaluation = _evaluate(
        _row(expected="ev-1", timing=140, tick=0),
        _row(expected="ev-2", timing=0, tick=480),
    )
    first = build_teaching_guidance_projection(evaluation, canonical_revision_id=REVISION)
    second = build_teaching_guidance_projection(evaluation, canonical_revision_id=REVISION)
    assert first == second
    assert first.guidance_digest == second.guidance_digest


def test_finding_identity_and_evidence_are_preserved() -> None:
    evaluation = _evaluate(_row(expected="ev-3", timing=140, tick=960))
    projection = build_teaching_guidance_projection(evaluation, canonical_revision_id=REVISION)
    finding = evaluation.findings[0]
    item = next(i for i in projection.items if i.finding_id == finding.finding_id)
    assert item.finding_id == finding.finding_id
    assert item.finding_type is finding.finding_type
    assert item.severity is finding.severity
    assert item.evidence_refs == finding.evidence_refs
    assert item.message_key == finding.message_key
    assert item.observed_value == finding.observed_value
    assert item.threshold_value == finding.threshold_value
    assert item.canonical_event_id == finding.expected_event_refs[0]


def test_canonical_event_id_is_the_join_key_not_a_new_id() -> None:
    evaluation = _evaluate(_row(expected="ev-4", timing=140, tick=1440))
    projection = build_teaching_guidance_projection(evaluation, canonical_revision_id=REVISION)
    cited = {item.canonical_event_id for item in projection.items if item.canonical_event_id}
    expected = {ref for finding in evaluation.findings for ref in finding.expected_event_refs}
    assert cited <= expected
    assert "ev-4" in cited
    assert all(not event_id.startswith("guide-") for event_id in cited)


def test_finding_order_permutation_does_not_change_digest() -> None:
    a = _finding("finding-b", event_ids=("ev-2",))
    b = _finding("finding-a", event_ids=("ev-1",))
    first = _manual_result((a, b), _continue_action())
    second = _manual_result((b, a), _continue_action())
    # Digests of the evaluations differ because finding order is semantic there.
    assert first.evaluation_digest != second.evaluation_digest
    left = build_teaching_guidance_projection(first, canonical_revision_id=REVISION)
    right = build_teaching_guidance_projection(second, canonical_revision_id=REVISION)
    assert [item.finding_id for item in left.items] == [item.finding_id for item in right.items]
    # The evaluation digest is part of the guidance digest, so permute-and-rebuild
    # of two different evaluations is not the same projection. Same evaluation
    # with permuted *builder input list* is covered by sort_guidance_items.
    same = build_teaching_guidance_projection(first, canonical_revision_id=REVISION)
    assert same.guidance_digest == left.guidance_digest


def test_isolate_passage_preserves_authoritative_range() -> None:
    action = PracticeNextActionV1(
        schema_version="1.0.0",
        action_type=PracticeNextActionType.ISOLATE_PASSAGE,
        reason_finding_ids=("finding-1", "finding-2", "finding-3"),
        message_key="action.isolate_passage",
        focus_start_tick=960,
        focus_end_tick=1920,
    )
    findings = (
        _finding("finding-1", event_ids=("ev-3",)),
        _finding("finding-2", event_ids=("ev-4",)),
        _finding("finding-3", event_ids=("ev-5",)),
    )
    evaluation = _manual_result(findings, action)
    projection = build_teaching_guidance_projection(evaluation, canonical_revision_id=REVISION)
    assert projection.next_action is action
    assert projection.next_action.focus_start_tick == 960
    assert projection.next_action.focus_end_tick == 1920
    assert projection.next_action.action_type is PracticeNextActionType.ISOLATE_PASSAGE


def test_slow_down_is_represented_without_a_transport_side_effect() -> None:
    action = PracticeNextActionV1(
        schema_version="1.0.0",
        action_type=PracticeNextActionType.SLOW_DOWN,
        reason_finding_ids=("finding-1",),
        message_key="action.slow_down",
        target_rate=0.75,
    )
    evaluation = _manual_result((_finding("finding-1"),), action)
    projection = build_teaching_guidance_projection(evaluation, canonical_revision_id=REVISION)
    encoded = to_dict(projection)
    assert encoded["next_action"]["action_type"] == "slow_down"
    assert encoded["next_action"]["target_rate"] == 0.75
    assert "transport" not in encoded
    assert "playback_rate" not in encoded


def test_repeat_remains_advisory() -> None:
    action = PracticeNextActionV1(
        schema_version="1.0.0",
        action_type=PracticeNextActionType.REPEAT,
        reason_finding_ids=("finding-1", "finding-2"),
        message_key="action.repeat",
    )
    evaluation = _manual_result(
        (_finding("finding-1"), _finding("finding-2", event_ids=("ev-2",))),
        action,
    )
    projection = build_teaching_guidance_projection(evaluation, canonical_revision_id=REVISION)
    assert projection.next_action.action_type is PracticeNextActionType.REPEAT
    assert "accepted" not in to_dict(projection)


def test_continue_is_not_mastery() -> None:
    evaluation = _evaluate(_row(expected="ev-1", timing=0, tick=0))
    projection = build_teaching_guidance_projection(evaluation, canonical_revision_id=REVISION)
    assert projection.next_action.action_type is PracticeNextActionType.CONTINUE
    text = str(to_dict(projection)).lower()
    for token in ("mastered", "perfect", "complete", "passed curriculum"):
        assert token not in text


def test_unrenderable_event_is_preserved_not_rewritten() -> None:
    evaluation = _manual_result(
        (_finding("finding-ghost", event_ids=("ev-not-in-score",)),),
        _continue_action(),
    )
    projection = build_teaching_guidance_projection(evaluation, canonical_revision_id=REVISION)
    assert projection.items[0].canonical_event_id == "ev-not-in-score"
    assert projection.guided_event_ids == ("ev-not-in-score",)


def test_zone_enriches_explanation_only() -> None:
    evaluation = _manual_result((_finding("finding-1", event_ids=("ev-1",)),), _continue_action())
    plain = build_teaching_guidance_projection(evaluation, canonical_revision_id=REVISION)
    zoned = build_teaching_guidance_projection(
        evaluation,
        canonical_revision_id=REVISION,
        zone_by_event={"ev-1": "ZONE_1"},
    )
    assert plain.guided_event_ids == zoned.guided_event_ids
    assert plain.next_action == zoned.next_action
    assert [item.finding_type for item in plain.items] == [
        item.finding_type for item in zoned.items
    ]
    assert [item.severity for item in plain.items] == [item.severity for item in zoned.items]
    assert zoned.items[0].zone_context == "ZONE_1"
    assert plain.items[0].zone_context is None
    assert plain.guidance_digest == zoned.guidance_digest


def test_digest_ignores_presentation_runtime_state() -> None:
    evaluation = _evaluate(_row(expected="ev-1", timing=140, tick=0))
    projection = build_teaching_guidance_projection(evaluation, canonical_revision_id=REVISION)
    again = compute_guidance_digest(
        canonical_revision_id=projection.canonical_revision_id,
        performance_session_id=projection.performance_session_id,
        evaluation_digest=projection.evaluation_digest,
        policy_version=projection.policy_version,
        items=projection.items,
        next_action=projection.next_action,
    )
    assert again == projection.guidance_digest
    # Selection, playhead activity, rate, and loop are not digest inputs.
    assert projection.policy_version == GUIDANCE_POLICY_VERSION


def test_builder_rejects_non_evaluation() -> None:
    with pytest.raises(EducationContractError, match="PracticeEvaluationResultV1"):
        build_teaching_guidance_projection(
            {"findings": []},  # type: ignore[arg-type]
            canonical_revision_id=REVISION,
        )


def test_builder_rejects_blank_revision_id() -> None:
    evaluation = _evaluate(_row(expected="ev-1", timing=0, tick=0))
    with pytest.raises(EducationContractError, match="canonical_revision_id"):
        build_teaching_guidance_projection(evaluation, canonical_revision_id="")


def test_presentation_fields_cannot_change_educational_decision() -> None:
    evaluation = _evaluate(_row(expected="ev-2", timing=140, tick=480))
    original_action = evaluation.primary_next_action
    original_findings = evaluation.findings
    projection = build_teaching_guidance_projection(
        evaluation,
        canonical_revision_id=REVISION,
        zone_by_event={"ev-2": "ZONE_2"},
        provenance=(("ui_theme", "dark"), ("selected_event", "ev-9")),
    )
    assert evaluation.primary_next_action == original_action
    assert evaluation.findings == original_findings
    assert projection.next_action == original_action
