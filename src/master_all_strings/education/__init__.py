"""Educational Engine — practice evaluation and feedback (DO-010).

Performance measures. Education interprets. This package must never rewrite
``PerformanceSessionEvidenceV1`` or invent substitute measurement fields.
"""

from __future__ import annotations

from master_all_strings.education.contracts import (
    PracticeAttemptSummaryV1,
    PracticeEvaluationPolicyV1,
    PracticeEvaluationResultV1,
    PracticeFindingSeverity,
    PracticeFindingType,
    PracticeFindingV1,
    PracticeFocusRangeV1,
    PracticeNextActionType,
    PracticeNextActionV1,
)
from master_all_strings.education.errors import EducationContractError
from master_all_strings.education.evaluation import (
    PracticeEvaluator,
    evaluate_alignment_findings,
    evaluate_practice_attempt,
)
from master_all_strings.education.messages import MESSAGE_CATALOG_V1
from master_all_strings.education.serialization import (
    compute_evaluation_digest,
    serialize_evaluation_result,
    to_dict,
)
from master_all_strings.education.session_history import PracticeSessionHistory

__all__ = [
    "MESSAGE_CATALOG_V1",
    "EducationContractError",
    "PracticeAttemptSummaryV1",
    "PracticeEvaluationPolicyV1",
    "PracticeEvaluationResultV1",
    "PracticeEvaluator",
    "PracticeFindingSeverity",
    "PracticeFindingType",
    "PracticeFindingV1",
    "PracticeFocusRangeV1",
    "PracticeNextActionType",
    "PracticeNextActionV1",
    "PracticeSessionHistory",
    "compute_evaluation_digest",
    "evaluate_alignment_findings",
    "evaluate_practice_attempt",
    "serialize_evaluation_result",
    "to_dict",
]
