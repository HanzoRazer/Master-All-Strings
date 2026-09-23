"""Educational Engine — practice evaluation, guidance, and guided sessions.

Performance measures. Education interprets. Guided-session orchestration records
disposition and execution without rewriting measurement fields or choosing the
Educational next action.
"""

from __future__ import annotations

from master_all_strings.education.assignment_delivery import (
    LESSON_DELIVERY_SCHEMA_ID,
    LESSON_DELIVERY_SCHEMA_VERSION,
    LessonDeliveryEnvelopeV1,
    LessonDeliverySummaryV1,
    validate_delivery_integrity,
)
from master_all_strings.education.assignment_delivery_serialization import (
    deserialize_delivery,
    serialize_delivery,
)
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
from master_all_strings.education.guidance import (
    GUIDANCE_POLICY_VERSION,
    GUIDANCE_SCHEMA_VERSION,
    TeachingGuidanceItemV1,
    TeachingGuidanceProjectionV1,
    compute_guidance_digest,
    serialize_guidance_projection,
    sort_guidance_items,
)
from master_all_strings.education.guidance_builder import build_teaching_guidance_projection
from master_all_strings.education.guided_session import (
    SESSION_POLICY_VERSION,
    SESSION_SCHEMA_VERSION,
    GuidedPracticeActionDisposition,
    GuidedPracticeActionV1,
    GuidedPracticeAttemptV1,
    GuidedPracticeContextV1,
    GuidedPracticeExecutionStatus,
    GuidedPracticeSessionStatus,
    GuidedPracticeSessionV1,
    append_attempt,
    compute_session_digest,
    serialize_guided_practice_session,
    session_with_digest,
)
from master_all_strings.education.guided_session_service import (
    append_evaluated_attempt,
    create_from_first_evaluated_attempt,
    record_action_disposition,
    record_action_execution,
    transition_session,
)
from master_all_strings.education.messages import MESSAGE_CATALOG_V1
from master_all_strings.education.serialization import (
    compute_evaluation_digest,
    serialize_evaluation_result,
    to_dict,
)
from master_all_strings.education.session_history import PracticeSessionHistory

__all__ = [
    "GUIDANCE_POLICY_VERSION",
    "LESSON_DELIVERY_SCHEMA_ID",
    "LESSON_DELIVERY_SCHEMA_VERSION",
    "GUIDANCE_SCHEMA_VERSION",
    "MESSAGE_CATALOG_V1",
    "SESSION_POLICY_VERSION",
    "SESSION_SCHEMA_VERSION",
    "EducationContractError",
    "LessonDeliveryEnvelopeV1",
    "LessonDeliverySummaryV1",
    "GuidedPracticeActionDisposition",
    "GuidedPracticeActionV1",
    "GuidedPracticeAttemptV1",
    "GuidedPracticeContextV1",
    "GuidedPracticeExecutionStatus",
    "GuidedPracticeSessionStatus",
    "GuidedPracticeSessionV1",
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
    "TeachingGuidanceItemV1",
    "TeachingGuidanceProjectionV1",
    "append_attempt",
    "append_evaluated_attempt",
    "build_teaching_guidance_projection",
    "create_from_first_evaluated_attempt",
    "compute_evaluation_digest",
    "compute_guidance_digest",
    "compute_session_digest",
    "evaluate_alignment_findings",
    "evaluate_practice_attempt",
    "record_action_disposition",
    "record_action_execution",
    "serialize_evaluation_result",
    "serialize_guidance_projection",
    "serialize_guided_practice_session",
    "session_with_digest",
    "sort_guidance_items",
    "to_dict",
    "transition_session",
    "deserialize_delivery",
    "serialize_delivery",
    "validate_delivery_integrity",
]
