"""PracticeEvaluator — Educational interpretation of Performance evidence."""

from __future__ import annotations

from master_all_strings.education.contracts import (
    PracticeEvaluationPolicyV1,
    PracticeFindingV1,
)
from master_all_strings.education.errors import EducationContractError
from master_all_strings.education.findings import (
    evaluate_extra_observed,
    evaluate_missing_expected,
    evaluate_pitch_findings,
    evaluate_timing_findings,
)
from master_all_strings.performance.contracts.alignment import PerformanceAlignmentResultV1

__all__ = ["PracticeEvaluator", "evaluate_alignment_findings"]


def evaluate_alignment_findings(
    alignment: PerformanceAlignmentResultV1,
    policy: PracticeEvaluationPolicyV1,
) -> tuple[PracticeFindingV1, ...]:
    """Derive deterministic findings from structural alignment evidence."""

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


class PracticeEvaluator:
    """Educational evaluator. Does not mutate Performance evidence."""

    def __init__(self, policy: PracticeEvaluationPolicyV1 | None = None) -> None:
        self.policy = policy or PracticeEvaluationPolicyV1.mvp_defaults()

    def evaluate_findings(
        self,
        alignment: PerformanceAlignmentResultV1,
        *,
        policy: PracticeEvaluationPolicyV1 | None = None,
    ) -> tuple[PracticeFindingV1, ...]:
        return evaluate_alignment_findings(alignment, policy or self.policy)
