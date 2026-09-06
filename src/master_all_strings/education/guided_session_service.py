"""Guided practice session lifecycle (DO-015 Stage 2).

Records create / append / disposition / execution / close / transition facts.
Does not choose Educational next actions, derive Transport parameters, score a
performance, or mutate completed attempt records in place.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

from master_all_strings.education.contracts import (
    PracticeEvaluationResultV1,
    PracticeNextActionType,
    PracticeNextActionV1,
)
from master_all_strings.education.errors import EducationContractError, require_identifier
from master_all_strings.education.guidance import TeachingGuidanceProjectionV1
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
    session_with_digest,
)

__all__ = [
    "append_evaluated_attempt",
    "begin_next_attempt",
    "close_session",
    "create_from_first_evaluated_attempt",
    "record_action_disposition",
    "record_action_execution",
    "transition_session",
]

_PRODUCER = "GuidedPracticeSessionV1/v1"
_SOURCE = "education.guided_session_service"
_PLACEHOLDER_DIGEST = "sha256:" + ("0" * 64)
_TRANSITION_REASON = "lesson_content_change"

_UNSUPPORTED_ACTIONS = frozenset(
    {
        PracticeNextActionType.VIEW_ONE_STRING,
        PracticeNextActionType.ENABLE_ZONE_VIEW,
    }
)
_OPEN_STATUSES = frozenset(
    {
        GuidedPracticeSessionStatus.ACTIVE,
        GuidedPracticeSessionStatus.AWAITING_ACTION,
        GuidedPracticeSessionStatus.AWAITING_ATTEMPT,
    }
)
_TERMINAL_STATUSES = frozenset(
    {
        GuidedPracticeSessionStatus.CLOSED,
        GuidedPracticeSessionStatus.TRANSITIONED,
        GuidedPracticeSessionStatus.ABORTED,
    }
)


def _opaque_id(provided: str | None, field_name: str) -> str:
    if provided is None:
        return str(uuid.uuid4())
    require_identifier(provided, field_name)
    return provided


def _default_context() -> GuidedPracticeContextV1:
    return GuidedPracticeContextV1(schema_version=SESSION_SCHEMA_VERSION)


def _default_provenance() -> tuple[tuple[str, str], ...]:
    return (
        ("policy_version", SESSION_POLICY_VERSION),
        ("producer", _PRODUCER),
        ("schema_version", SESSION_SCHEMA_VERSION),
        ("source", _SOURCE),
    )


def _provenance_with(
    existing: tuple[tuple[str, str], ...],
    **updates: str,
) -> tuple[tuple[str, str], ...]:
    mapping = dict(existing)
    mapping.update(updates)
    return tuple(sorted(mapping.items()))


def _require_session(session: object) -> GuidedPracticeSessionV1:
    if not isinstance(session, GuidedPracticeSessionV1):
        raise EducationContractError("expected a GuidedPracticeSessionV1")
    return session


def _require_evidence_chain(
    evaluation: object,
    guidance: object,
) -> tuple[PracticeEvaluationResultV1, TeachingGuidanceProjectionV1]:
    if not isinstance(evaluation, PracticeEvaluationResultV1):
        raise EducationContractError(
            "creation requires a complete evaluated evidence chain: evaluation"
        )
    if not isinstance(guidance, TeachingGuidanceProjectionV1):
        raise EducationContractError(
            "creation requires a complete evaluated evidence chain: guidance"
        )
    if evaluation.performance_session_id != guidance.performance_session_id:
        raise EducationContractError(
            "attempt.performance_session_id must equal guidance.performance_session_id"
        )
    if evaluation.evaluation_digest != guidance.evaluation_digest:
        raise EducationContractError(
            "attempt.evaluation_digest must equal guidance.evaluation_digest"
        )
    if evaluation.primary_next_action != guidance.next_action:
        raise EducationContractError(
            "guidance.next_action must equal evaluation.primary_next_action"
        )
    if not isinstance(guidance.next_action, PracticeNextActionV1):
        raise EducationContractError("primary next_action is required")
    return evaluation, guidance


def _current_attempt(session: GuidedPracticeSessionV1) -> GuidedPracticeAttemptV1:
    if not session.attempts or session.current_attempt_index is None:
        raise EducationContractError("guided session has no current attempt")
    return session.attempts[session.current_attempt_index]


def _replace_current_attempt(
    session: GuidedPracticeSessionV1,
    attempt: GuidedPracticeAttemptV1,
    *,
    status: GuidedPracticeSessionStatus,
    provenance: tuple[tuple[str, str], ...] | None = None,
) -> GuidedPracticeSessionV1:
    current = _current_attempt(session)
    if attempt.attempt_id != current.attempt_id or attempt.attempt_index != current.attempt_index:
        raise EducationContractError("current attempt identity must be preserved")
    prior = session.attempts[:-1]
    return session_with_digest(
        replace(
            session,
            attempts=prior + (attempt,),
            status=status,
            provenance=session.provenance if provenance is None else provenance,
            session_digest=_PLACEHOLDER_DIGEST,
        )
    )


def _attempt_from_evidence(
    evaluation: PracticeEvaluationResultV1,
    guidance: TeachingGuidanceProjectionV1,
    *,
    attempt_id: str,
    attempt_index: int,
    practice_context: GuidedPracticeContextV1,
) -> GuidedPracticeAttemptV1:
    return GuidedPracticeAttemptV1(
        schema_version=SESSION_SCHEMA_VERSION,
        attempt_id=attempt_id,
        attempt_index=attempt_index,
        assignment_id=evaluation.assignment_id,
        content_id=evaluation.content_id,
        canonical_revision_id=guidance.canonical_revision_id,
        performance_session_id=evaluation.performance_session_id,
        evaluation_digest=evaluation.evaluation_digest,
        guidance_digest=guidance.guidance_digest,
        action=GuidedPracticeActionV1(
            schema_version=SESSION_SCHEMA_VERSION,
            recommended_action=guidance.next_action,
            action_disposition=GuidedPracticeActionDisposition.PENDING,
            execution_status=GuidedPracticeExecutionStatus.NOT_REQUESTED,
        ),
        practice_context=practice_context,
    )


def create_from_first_evaluated_attempt(
    evaluation: PracticeEvaluationResultV1,
    guidance: TeachingGuidanceProjectionV1,
    *,
    session_id: str | None = None,
    attempt_id: str | None = None,
    practice_context: GuidedPracticeContextV1 | None = None,
) -> GuidedPracticeSessionV1:
    """Create a session from the first complete evaluated evidence chain."""

    evaluation, guidance = _require_evidence_chain(evaluation, guidance)
    attempt = _attempt_from_evidence(
        evaluation,
        guidance,
        attempt_id=_opaque_id(attempt_id, "attempt_id"),
        attempt_index=0,
        practice_context=practice_context or _default_context(),
    )
    draft = GuidedPracticeSessionV1(
        schema_version=SESSION_SCHEMA_VERSION,
        policy_version=SESSION_POLICY_VERSION,
        session_id=_opaque_id(session_id, "session_id"),
        assignment_id=evaluation.assignment_id,
        content_id=evaluation.content_id,
        canonical_revision_id=guidance.canonical_revision_id,
        status=GuidedPracticeSessionStatus.AWAITING_ACTION,
        attempts=(attempt,),
        current_attempt_index=0,
        session_digest=_PLACEHOLDER_DIGEST,
        provenance=_default_provenance(),
    )
    return session_with_digest(draft)


def append_evaluated_attempt(
    session: GuidedPracticeSessionV1,
    evaluation: PracticeEvaluationResultV1,
    guidance: TeachingGuidanceProjectionV1,
    *,
    attempt_id: str | None = None,
    attempt_index: int | None = None,
    practice_context: GuidedPracticeContextV1 | None = None,
) -> GuidedPracticeSessionV1:
    """Append the next evaluated attempt. Prior attempts are unchanged."""

    session = _require_session(session)
    evaluation, guidance = _require_evidence_chain(evaluation, guidance)
    if session.status is not GuidedPracticeSessionStatus.AWAITING_ATTEMPT:
        raise EducationContractError("append requires session.status AWAITING_ATTEMPT")
    if evaluation.assignment_id != session.assignment_id:
        raise EducationContractError("append assignment_id does not match session")
    if evaluation.content_id != session.content_id:
        raise EducationContractError("append content_id does not match session")
    if guidance.canonical_revision_id != session.canonical_revision_id:
        raise EducationContractError("append canonical_revision_id does not match session")
    expected_index = len(session.attempts)
    if attempt_index is not None and attempt_index != expected_index:
        raise EducationContractError("duplicate attempt_index")
    next_attempt_id = _opaque_id(attempt_id, "attempt_id")
    if any(item.attempt_id == next_attempt_id for item in session.attempts):
        raise EducationContractError("duplicate attempt_id")
    if any(
        item.performance_session_id == evaluation.performance_session_id
        for item in session.attempts
    ):
        raise EducationContractError("performance_session_id must be unique per attempt")
    attempt = _attempt_from_evidence(
        evaluation,
        guidance,
        attempt_id=next_attempt_id,
        attempt_index=expected_index,
        practice_context=practice_context or _default_context(),
    )
    return append_attempt(
        session,
        attempt,
        status=GuidedPracticeSessionStatus.AWAITING_ACTION,
    )


def record_action_disposition(
    session: GuidedPracticeSessionV1,
    disposition: GuidedPracticeActionDisposition,
) -> GuidedPracticeSessionV1:
    """Record learner accept/decline of the primary recommended action."""

    session = _require_session(session)
    if session.status is not GuidedPracticeSessionStatus.AWAITING_ACTION:
        raise EducationContractError("disposition requires session.status AWAITING_ACTION")
    if not session.attempts:
        raise EducationContractError("disposition requires a recorded recommended_action")
    current = _current_attempt(session)
    if current.action_disposition is not GuidedPracticeActionDisposition.PENDING:
        raise EducationContractError("action_disposition is already resolved")
    if disposition is GuidedPracticeActionDisposition.PENDING:
        raise EducationContractError("disposition must be ACCEPTED or DECLINED")
    if disposition is GuidedPracticeActionDisposition.DECLINED:
        updated = replace(
            current,
            action=replace(
                current.action,
                action_disposition=GuidedPracticeActionDisposition.DECLINED,
                execution_status=GuidedPracticeExecutionStatus.NOT_REQUESTED,
                executed_action=None,
            ),
        )
        return _replace_current_attempt(
            session,
            updated,
            status=GuidedPracticeSessionStatus.AWAITING_ATTEMPT,
        )
    if disposition is not GuidedPracticeActionDisposition.ACCEPTED:
        raise EducationContractError("disposition must be ACCEPTED or DECLINED")
    updated = replace(
        current,
        action=replace(
            current.action,
            action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
            execution_status=GuidedPracticeExecutionStatus.PENDING,
            executed_action=None,
        ),
    )
    return _replace_current_attempt(
        session,
        updated,
        status=GuidedPracticeSessionStatus.AWAITING_ACTION,
    )


def record_action_execution(
    session: GuidedPracticeSessionV1,
    execution_status: GuidedPracticeExecutionStatus,
    *,
    executed_action: PracticeNextActionV1 | None = None,
) -> GuidedPracticeSessionV1:
    """Record an external execution fact. Does not perform the action."""

    session = _require_session(session)
    current = _current_attempt(session)
    if current.action_disposition is GuidedPracticeActionDisposition.DECLINED:
        raise EducationContractError("execution cannot be recorded for a declined action")
    if current.action_disposition is not GuidedPracticeActionDisposition.ACCEPTED:
        raise EducationContractError("execution cannot be recorded before acceptance")
    if session.status is not GuidedPracticeSessionStatus.AWAITING_ACTION:
        raise EducationContractError("execution requires session.status AWAITING_ACTION")
    if current.execution_status is not GuidedPracticeExecutionStatus.PENDING:
        raise EducationContractError("execution_status is already resolved")
    if execution_status not in {
        GuidedPracticeExecutionStatus.SUCCEEDED,
        GuidedPracticeExecutionStatus.FAILED,
        GuidedPracticeExecutionStatus.UNSUPPORTED,
    }:
        raise EducationContractError("execution_status must be SUCCEEDED, FAILED, or UNSUPPORTED")
    action_type = current.recommended_action.action_type
    if (
        execution_status is GuidedPracticeExecutionStatus.SUCCEEDED
        and action_type in _UNSUPPORTED_ACTIONS
    ):
        raise EducationContractError("SUCCEEDED is not valid for unsupported Educational actions")
    recorded_executed: PracticeNextActionV1 | None
    if execution_status is GuidedPracticeExecutionStatus.UNSUPPORTED:
        recorded_executed = None
    elif executed_action is not None:
        recorded_executed = executed_action
    else:
        recorded_executed = current.recommended_action
    updated = replace(
        current,
        action=replace(
            current.action,
            execution_status=execution_status,
            executed_action=recorded_executed,
        ),
    )
    if (
        execution_status is GuidedPracticeExecutionStatus.SUCCEEDED
        and action_type is PracticeNextActionType.CONTINUE
    ):
        next_status = GuidedPracticeSessionStatus.CLOSED
    else:
        next_status = GuidedPracticeSessionStatus.AWAITING_ATTEMPT
    return _replace_current_attempt(session, updated, status=next_status)


def begin_next_attempt(session: GuidedPracticeSessionV1) -> GuidedPracticeSessionV1:
    """Mark an open session ready for the next evaluated attempt."""

    session = _require_session(session)
    if session.status in _TERMINAL_STATUSES:
        raise EducationContractError("begin_next_attempt is not valid for a terminal session")
    current = _current_attempt(session)
    if current.action_disposition is GuidedPracticeActionDisposition.PENDING:
        raise EducationContractError("begin_next_attempt requires a resolved disposition")
    if (
        current.action_disposition is GuidedPracticeActionDisposition.ACCEPTED
        and current.execution_status is GuidedPracticeExecutionStatus.PENDING
    ):
        raise EducationContractError("begin_next_attempt requires a recorded execution fact")
    if (
        current.recommended_action.action_type is PracticeNextActionType.CONTINUE
        and current.action_disposition is GuidedPracticeActionDisposition.ACCEPTED
        and current.execution_status is GuidedPracticeExecutionStatus.SUCCEEDED
    ):
        raise EducationContractError("successful CONTINUE must close rather than begin next")
    if session.status is GuidedPracticeSessionStatus.AWAITING_ATTEMPT:
        return session
    return session_with_digest(
        replace(
            session,
            status=GuidedPracticeSessionStatus.AWAITING_ATTEMPT,
            session_digest=_PLACEHOLDER_DIGEST,
        )
    )


def close_session(session: GuidedPracticeSessionV1) -> GuidedPracticeSessionV1:
    """Close after accepted-and-successfully-executed CONTINUE."""

    session = _require_session(session)
    current = _current_attempt(session)
    if not (
        current.recommended_action.action_type is PracticeNextActionType.CONTINUE
        and current.action_disposition is GuidedPracticeActionDisposition.ACCEPTED
        and current.execution_status is GuidedPracticeExecutionStatus.SUCCEEDED
    ):
        raise EducationContractError("CONTINUE closure requires successful execution")
    if session.status is GuidedPracticeSessionStatus.CLOSED:
        return session
    if session.status in _TERMINAL_STATUSES:
        raise EducationContractError("close_session is not valid for a terminal session")
    return session_with_digest(
        replace(
            session,
            status=GuidedPracticeSessionStatus.CLOSED,
            session_digest=_PLACEHOLDER_DIGEST,
        )
    )


def transition_session(
    session: GuidedPracticeSessionV1,
    *,
    next_assignment_id: str,
    next_content_id: str,
    reason: str = _TRANSITION_REASON,
) -> GuidedPracticeSessionV1:
    """Transition an open session on lesson/content change. Does not create the next session."""

    session = _require_session(session)
    require_identifier(next_assignment_id, "next_assignment_id")
    require_identifier(next_content_id, "next_content_id")
    require_identifier(reason, "reason")
    if session.status in _TERMINAL_STATUSES:
        raise EducationContractError("transition is not valid for a terminal session")
    if session.status not in _OPEN_STATUSES:
        raise EducationContractError("transition requires an open session")
    if (
        next_assignment_id == session.assignment_id
        and next_content_id == session.content_id
    ):
        raise EducationContractError("transition requires an assignment or content change")
    return session_with_digest(
        replace(
            session,
            status=GuidedPracticeSessionStatus.TRANSITIONED,
            provenance=_provenance_with(
                session.provenance,
                transition_reason=reason,
                next_assignment_id=next_assignment_id,
                next_content_id=next_content_id,
            ),
            session_digest=_PLACEHOLDER_DIGEST,
        )
    )
