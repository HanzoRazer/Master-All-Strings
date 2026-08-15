"""PracticeEvaluator — Educational interpretation of Performance evidence.

Performance measures. Education interprets. This module never mutates
``PerformanceSessionEvidenceV1`` or alignment measurement fields.
"""

from __future__ import annotations

from collections.abc import Sequence

from master_all_strings.education.contracts import (
    PracticeAttemptSummaryV1,
    PracticeEvaluationPolicyV1,
    PracticeEvaluationResultV1,
    PracticeFindingType,
    PracticeFindingV1,
)
from master_all_strings.education.errors import EducationContractError
from master_all_strings.education.findings import (
    evaluate_extra_observed,
    evaluate_missing_expected,
    evaluate_pitch_findings,
    evaluate_timing_findings,
)
from master_all_strings.education.passage_focus import (
    cluster_findings_by_passage,
    concentrated_finding,
)
from master_all_strings.education.recommendations import build_next_actions
from master_all_strings.education.repetitions import compare_repetitions
from master_all_strings.education.serialization import compute_evaluation_digest
from master_all_strings.education.session_history import PracticeSessionHistory
from master_all_strings.performance.contracts.alignment import (
    AlignmentStatus,
    PerformanceAlignmentResultV1,
)
from master_all_strings.performance.contracts.session_evidence import PerformanceSessionEvidenceV1

__all__ = [
    "PracticeEvaluator",
    "evaluate_alignment_findings",
    "evaluate_practice_attempt",
]

_MATCHED = (
    AlignmentStatus.MATCHED_EXACT_PITCH,
    AlignmentStatus.MATCHED_PITCH_DIFFERENCE,
    AlignmentStatus.UNRESOLVED_CAPTURE,
)


def evaluate_alignment_findings(
    alignment: PerformanceAlignmentResultV1,
    policy: PracticeEvaluationPolicyV1,
) -> tuple[PracticeFindingV1, ...]:
    """Derive deterministic base findings from structural alignment evidence."""

    if not isinstance(alignment, PerformanceAlignmentResultV1):
        raise EducationContractError("alignment must be a PerformanceAlignmentResultV1")
    if not isinstance(policy, PracticeEvaluationPolicyV1):
        raise EducationContractError("policy must be a PracticeEvaluationPolicyV1")

    findings: list[PracticeFindingV1] = []
    findings.extend(evaluate_timing_findings(alignment.aligned_events, policy))
    findings.extend(evaluate_pitch_findings(alignment.aligned_events, policy))
    findings.extend(evaluate_missing_expected(alignment.aligned_events))
    findings.extend(evaluate_extra_observed(alignment.aligned_events))
    return tuple(findings)


def _count_expected(alignment: PerformanceAlignmentResultV1) -> int:
    return sum(1 for row in alignment.aligned_events if row.expected_event_id is not None)


def _count_observed(alignment: PerformanceAlignmentResultV1) -> int:
    return sum(1 for row in alignment.aligned_events if row.observed_event_id is not None)


def _count_matched(alignment: PerformanceAlignmentResultV1) -> int:
    return sum(1 for row in alignment.aligned_events if row.status in _MATCHED)


def _count_type(findings: Sequence[PracticeFindingV1], finding_type: PracticeFindingType) -> int:
    return sum(1 for finding in findings if finding.finding_type is finding_type)


def _count_timing(findings: Sequence[PracticeFindingV1]) -> int:
    return sum(
        1
        for finding in findings
        if finding.finding_type
        in {PracticeFindingType.EARLY_ENTRY, PracticeFindingType.LATE_ENTRY}
    )


def _repetition_count(findings: Sequence[PracticeFindingV1]) -> int:
    indices = {f.repetition_index for f in findings if f.repetition_index is not None}
    return len(indices)


def _default_provenance(
    alignment: PerformanceAlignmentResultV1,
    evidence: PerformanceSessionEvidenceV1 | None,
) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = [
        ("producer", "PracticeEvaluator/v1"),
        ("alignment_session", alignment.performance_session_id),
    ]
    if evidence is not None:
        items.extend(
            (
                ("evidence_digest", evidence.evidence_digest),
                ("raw_capture_ref", evidence.raw_capture_ref),
                ("observed_events_ref", evidence.observed_events_ref),
                ("alignment_ref", evidence.alignment_ref),
            )
        )
    return tuple(items)


class PracticeEvaluator:
    """Educational evaluator. Does not mutate Performance evidence."""

    def __init__(
        self,
        policy: PracticeEvaluationPolicyV1 | None = None,
        *,
        history: PracticeSessionHistory | None = None,
    ) -> None:
        self.policy = policy or PracticeEvaluationPolicyV1.mvp_defaults()
        self.history = history

    def evaluate_findings(
        self,
        alignment: PerformanceAlignmentResultV1,
        *,
        policy: PracticeEvaluationPolicyV1 | None = None,
    ) -> tuple[PracticeFindingV1, ...]:
        return evaluate_alignment_findings(alignment, policy or self.policy)

    def evaluate(
        self,
        alignment: PerformanceAlignmentResultV1,
        *,
        evidence: PerformanceSessionEvidenceV1 | None = None,
        policy: PracticeEvaluationPolicyV1 | None = None,
        current_rate: float = 1.0,
        provenance: Sequence[tuple[str, str]] | None = None,
    ) -> PracticeEvaluationResultV1:
        """Interpret one alignment attempt into PracticeEvaluationResultV1."""

        active_policy = policy or self.policy
        if evidence is not None:
            if evidence.performance_session_id != alignment.performance_session_id:
                raise EducationContractError("evidence/alignment performance_session_id mismatch")
            if evidence.assignment_id != alignment.assignment_id:
                raise EducationContractError("evidence/alignment assignment_id mismatch")
            if evidence.content_id != alignment.content_id:
                raise EducationContractError("evidence/alignment content_id mismatch")

        findings = list(self.evaluate_findings(alignment, policy=active_policy))
        expected_ticks = tuple(
            row.expected_start_tick
            for row in alignment.aligned_events
            if row.expected_event_id is not None and row.expected_start_tick is not None
        )
        ordered_ticks: list[int] = []
        seen_ticks: set[int] = set()
        for tick in expected_ticks:
            if tick in seen_ticks:
                continue
            seen_ticks.add(tick)
            ordered_ticks.append(tick)
        focus_ranges = cluster_findings_by_passage(
            findings,
            active_policy,
            expected_ticks=ordered_ticks,
        )
        concentrated = concentrated_finding(focus_ranges)
        if concentrated is not None:
            findings.append(concentrated)
        findings.extend(compare_repetitions(findings))

        primary, secondary = build_next_actions(
            findings,
            focus_ranges,
            active_policy,
            expected_event_count=_count_expected(alignment),
            current_rate=current_rate,
        )
        actionable = sum(1 for finding in findings if finding.is_actionable)
        summary = PracticeAttemptSummaryV1(
            schema_version=PracticeAttemptSummaryV1.SCHEMA_VERSION,
            performance_session_id=alignment.performance_session_id,
            expected_event_count=_count_expected(alignment),
            observed_event_count=_count_observed(alignment),
            matched_count=_count_matched(alignment),
            missing_count=_count_type(findings, PracticeFindingType.EXPECTED_NOTE_MISSING),
            extra_count=_count_type(findings, PracticeFindingType.UNEXPECTED_NOTE),
            pitch_finding_count=_count_type(findings, PracticeFindingType.PITCH_DIFFERENCE),
            timing_finding_count=_count_timing(findings),
            actionable_finding_count=actionable,
            repetition_count=_repetition_count(findings),
            focus_ranges=focus_ranges,
            primary_action=primary,
            secondary_actions=secondary,
        )
        provenance_tuple = (
            tuple(provenance)
            if provenance is not None
            else _default_provenance(alignment, evidence)
        )
        digest = compute_evaluation_digest(
            assignment_id=alignment.assignment_id,
            content_id=alignment.content_id,
            performance_session_id=alignment.performance_session_id,
            evaluation_policy_id=active_policy.policy_id,
            evaluation_policy_version=active_policy.schema_version,
            findings=tuple(findings),
            summary=summary,
            primary_next_action=primary,
            secondary_actions=secondary,
            provenance=provenance_tuple,
        )
        result = PracticeEvaluationResultV1(
            schema_version=PracticeEvaluationResultV1.SCHEMA_VERSION,
            assignment_id=alignment.assignment_id,
            content_id=alignment.content_id,
            performance_session_id=alignment.performance_session_id,
            evaluation_policy_id=active_policy.policy_id,
            evaluation_policy_version=active_policy.schema_version,
            findings=tuple(findings),
            summary=summary,
            primary_next_action=primary,
            secondary_actions=secondary,
            provenance=provenance_tuple,
            evaluation_digest=digest,
        )
        if self.history is not None:
            self.history.record(result)
        return result


def evaluate_practice_attempt(
    alignment: PerformanceAlignmentResultV1,
    *,
    evidence: PerformanceSessionEvidenceV1 | None = None,
    policy: PracticeEvaluationPolicyV1 | None = None,
    current_rate: float = 1.0,
    history: PracticeSessionHistory | None = None,
    provenance: Sequence[tuple[str, str]] | None = None,
) -> PracticeEvaluationResultV1:
    """Module-level convenience wrapper for one practice attempt."""

    return PracticeEvaluator(policy=policy, history=history).evaluate(
        alignment,
        evidence=evidence,
        current_rate=current_rate,
        provenance=provenance,
    )
