"""DO-015 Stage 2: guided-session lifecycle service state machine."""

from __future__ import annotations

import copy
import inspect
import json
from dataclasses import replace

import pytest

from master_all_strings.education import (
    SESSION_POLICY_VERSION,
    EducationContractError,
    GuidedPracticeActionDisposition,
    GuidedPracticeExecutionStatus,
    GuidedPracticeSessionStatus,
    GuidedPracticeSessionV1,
    PracticeAttemptSummaryV1,
    PracticeEvaluationPolicyV1,
    PracticeEvaluationResultV1,
    PracticeFindingSeverity,
    PracticeFindingType,
    PracticeFindingV1,
    PracticeNextActionType,
    PracticeNextActionV1,
    TeachingGuidanceProjectionV1,
    append_evaluated_attempt,
    compute_evaluation_digest,
    compute_guidance_digest,
    create_from_first_evaluated_attempt,
    guided_session_service,
    record_action_disposition,
    record_action_execution,
    session_with_digest,
    to_dict,
    transition_session,
)
from master_all_strings.education.guidance_builder import build_teaching_guidance_projection

SESSION_ID = "11111111-1111-4111-8111-111111111111"
ATTEMPT_0 = "22222222-2222-4222-8222-222222222222"
ATTEMPT_1 = "33333333-3333-4333-8333-333333333333"
ASSIGNMENT = "44444444-4444-4444-8444-444444444444"
CONTENT = "55555555-5555-4555-8555-555555555555"
REVISION = "66666666-6666-4666-8666-666666666666"
PERF_0 = "77777777-7777-4777-8777-777777777777"
PERF_1 = "88888888-8888-4888-8888-888888888888"
OTHER_ASSIGNMENT = "99999999-9999-4999-8999-999999999999"
OTHER_CONTENT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_REVISION = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _continue() -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.CONTINUE,
        reason_finding_ids=(),
        message_key="action.continue",
    )


def _slow_down(rate: float = 0.75) -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.SLOW_DOWN,
        reason_finding_ids=("finding-1",),
        message_key="action.slow_down",
        target_rate=rate,
    )


def _isolate() -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.ISOLATE_PASSAGE,
        reason_finding_ids=("finding-1",),
        message_key="action.isolate_passage",
        focus_start_tick=0,
        focus_end_tick=480,
    )


def _repeat() -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.REPEAT,
        reason_finding_ids=("finding-1",),
        message_key="action.repeat",
    )


def _view_one_string() -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.VIEW_ONE_STRING,
        reason_finding_ids=("finding-1",),
        message_key="action.view_one_string",
        teaching_aid="one_string",
    )


def _enable_zone_view() -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.ENABLE_ZONE_VIEW,
        reason_finding_ids=("finding-1",),
        message_key="action.enable_zone_view",
        teaching_aid="zone_view",
    )


def _finding() -> PracticeFindingV1:
    return PracticeFindingV1(
        schema_version=PracticeFindingV1.SCHEMA_VERSION,
        finding_id="finding-1",
        finding_type=PracticeFindingType.LATE_ENTRY,
        severity=PracticeFindingSeverity.FOCUS,
        evidence_refs=("aligned-event-1",),
        expected_event_refs=("ev-1",),
        message_key="finding.late_entry",
        observed_value=140.0,
        threshold_value=100.0,
    )


def _evaluation(
    action: PracticeNextActionV1,
    *,
    assignment_id: str = ASSIGNMENT,
    content_id: str = CONTENT,
    performance_session_id: str = PERF_0,
) -> PracticeEvaluationResultV1:
    findings = (_finding(),)
    summary = PracticeAttemptSummaryV1(
        schema_version=PracticeAttemptSummaryV1.SCHEMA_VERSION,
        performance_session_id=performance_session_id,
        expected_event_count=1,
        observed_event_count=1,
        matched_count=1,
        missing_count=0,
        extra_count=0,
        pitch_finding_count=0,
        timing_finding_count=1,
        actionable_finding_count=1,
        repetition_count=1,
        focus_ranges=(),
        primary_action=action,
        secondary_actions=(),
    )
    provenance = (("assembler", "education.tests"),)
    digest = compute_evaluation_digest(
        assignment_id=assignment_id,
        content_id=content_id,
        performance_session_id=performance_session_id,
        evaluation_policy_id="mvp-do010-v1",
        evaluation_policy_version=PracticeEvaluationPolicyV1.SCHEMA_VERSION,
        findings=findings,
        summary=summary,
        primary_next_action=action,
        secondary_actions=(),
        provenance=provenance,
    )
    return PracticeEvaluationResultV1(
        schema_version=PracticeEvaluationResultV1.SCHEMA_VERSION,
        assignment_id=assignment_id,
        content_id=content_id,
        performance_session_id=performance_session_id,
        evaluation_policy_id="mvp-do010-v1",
        evaluation_policy_version=PracticeEvaluationPolicyV1.SCHEMA_VERSION,
        findings=findings,
        summary=summary,
        primary_next_action=action,
        secondary_actions=(),
        provenance=provenance,
        evaluation_digest=digest,
    )


def _guidance(
    evaluation: PracticeEvaluationResultV1,
    *,
    canonical_revision_id: str = REVISION,
) -> TeachingGuidanceProjectionV1:
    return build_teaching_guidance_projection(
        evaluation,
        canonical_revision_id=canonical_revision_id,
    )


def _evidence(
    action: PracticeNextActionV1 | None = None,
    *,
    assignment_id: str = ASSIGNMENT,
    content_id: str = CONTENT,
    canonical_revision_id: str = REVISION,
    performance_session_id: str = PERF_0,
) -> tuple[PracticeEvaluationResultV1, TeachingGuidanceProjectionV1]:
    evaluation = _evaluation(
        action or _slow_down(),
        assignment_id=assignment_id,
        content_id=content_id,
        performance_session_id=performance_session_id,
    )
    return evaluation, _guidance(evaluation, canonical_revision_id=canonical_revision_id)


def _create(
    action: PracticeNextActionV1 | None = None,
    *,
    session_id: str = SESSION_ID,
    attempt_id: str = ATTEMPT_0,
    performance_session_id: str = PERF_0,
) -> GuidedPracticeSessionV1:
    evaluation, guidance = _evidence(action, performance_session_id=performance_session_id)
    return create_from_first_evaluated_attempt(
        evaluation,
        guidance,
        session_id=session_id,
        attempt_id=attempt_id,
    )


def _accepted(session: GuidedPracticeSessionV1) -> GuidedPracticeSessionV1:
    return record_action_disposition(session, GuidedPracticeActionDisposition.ACCEPTED)


def _declined(session: GuidedPracticeSessionV1) -> GuidedPracticeSessionV1:
    return record_action_disposition(session, GuidedPracticeActionDisposition.DECLINED)


def _succeeded(session: GuidedPracticeSessionV1) -> GuidedPracticeSessionV1:
    return record_action_execution(session, GuidedPracticeExecutionStatus.SUCCEEDED)


def _empty_session() -> GuidedPracticeSessionV1:
    draft = GuidedPracticeSessionV1(
        schema_version=GuidedPracticeSessionV1.SCHEMA_VERSION,
        policy_version=SESSION_POLICY_VERSION,
        session_id=SESSION_ID,
        assignment_id=ASSIGNMENT,
        content_id=CONTENT,
        canonical_revision_id=REVISION,
        status=GuidedPracticeSessionStatus.AWAITING_ACTION,
        attempts=(),
        current_attempt_index=None,
        session_digest="sha256:" + ("0" * 64),
    )
    return session_with_digest(draft)


# --- happy paths -------------------------------------------------------------


def test_create_from_first_evaluated_attempt_is_awaiting_action() -> None:
    evaluation, guidance = _evidence()
    session = create_from_first_evaluated_attempt(
        evaluation,
        guidance,
        session_id=SESSION_ID,
        attempt_id=ATTEMPT_0,
    )
    assert session.session_id == SESSION_ID
    assert session.attempts != ()
    assert session.current_attempt_index == 0
    assert session.attempts[0].attempt_id == ATTEMPT_0
    assert session.attempts[0].attempt_index == 0
    assert session.attempts[0].action_disposition is GuidedPracticeActionDisposition.PENDING
    assert session.attempts[0].execution_status is GuidedPracticeExecutionStatus.NOT_REQUESTED
    assert session.status is GuidedPracticeSessionStatus.AWAITING_ACTION
    assert session.attempts[0].recommended_action.action_type is PracticeNextActionType.SLOW_DOWN
    assert session.attempts[0].recommended_action.target_rate == 0.75
    assert evaluation.performance_session_id == guidance.performance_session_id
    assert evaluation.evaluation_digest == guidance.evaluation_digest
    assert session.attempts[0].guidance_digest == guidance.guidance_digest


def test_service_does_not_create_an_empty_session() -> None:
    session = _create()
    assert len(session.attempts) == 1


def test_accept_does_not_claim_success() -> None:
    session = _accepted(_create())
    assert session.attempts[0].action_disposition is GuidedPracticeActionDisposition.ACCEPTED
    assert session.attempts[0].execution_status is GuidedPracticeExecutionStatus.PENDING
    assert session.attempts[0].executed_action is None
    assert session.status is GuidedPracticeSessionStatus.AWAITING_ACTION
    assert session.status is not GuidedPracticeSessionStatus.CLOSED


def test_decline_does_not_execute_and_awaits_next_attempt() -> None:
    session = _declined(_create())
    assert session.attempts[0].action_disposition is GuidedPracticeActionDisposition.DECLINED
    assert session.attempts[0].execution_status is GuidedPracticeExecutionStatus.NOT_REQUESTED
    assert session.attempts[0].executed_action is None
    assert session.status is GuidedPracticeSessionStatus.AWAITING_ATTEMPT


@pytest.mark.parametrize(
    "action_factory",
    [_slow_down, _isolate, _repeat],
    ids=["slow_down", "isolate_passage", "repeat"],
)
def test_successful_keep_open_actions_await_next_attempt(
    action_factory: object,
) -> None:
    session = _succeeded(_accepted(_create(action_factory())))  # type: ignore[operator]
    assert session.status is GuidedPracticeSessionStatus.AWAITING_ATTEMPT
    assert session.attempts[0].execution_status is GuidedPracticeExecutionStatus.SUCCEEDED
    assert session.attempts[0].executed_action == session.attempts[0].recommended_action


def test_successful_continue_closes_the_session() -> None:
    session = _succeeded(_accepted(_create(_continue())))
    assert session.status is GuidedPracticeSessionStatus.CLOSED
    assert session.attempts[0].recommended_action.action_type is PracticeNextActionType.CONTINUE
    assert session.attempts[0].action_disposition is GuidedPracticeActionDisposition.ACCEPTED
    assert session.attempts[0].execution_status is GuidedPracticeExecutionStatus.SUCCEEDED
    assert session.attempts[0].executed_action == session.attempts[0].recommended_action


def test_unsupported_view_actions_are_recoverable_not_continue() -> None:
    for factory in (_view_one_string, _enable_zone_view):
        session = record_action_execution(
            _accepted(_create(factory())),
            GuidedPracticeExecutionStatus.UNSUPPORTED,
        )
        assert session.attempts[0].action_disposition is GuidedPracticeActionDisposition.ACCEPTED
        assert session.attempts[0].execution_status is GuidedPracticeExecutionStatus.UNSUPPORTED
        assert session.attempts[0].executed_action is None
        assert session.status is GuidedPracticeSessionStatus.AWAITING_ATTEMPT
        assert session.status is not GuidedPracticeSessionStatus.CLOSED


def test_failed_execution_awaits_next_attempt() -> None:
    session = record_action_execution(
        _accepted(_create()),
        GuidedPracticeExecutionStatus.FAILED,
    )
    assert session.status is GuidedPracticeSessionStatus.AWAITING_ATTEMPT
    assert session.attempts[0].execution_status is GuidedPracticeExecutionStatus.FAILED
    assert session.attempts[0].executed_action == session.attempts[0].recommended_action


def test_append_after_keep_open_preserves_identity_and_prior_attempt() -> None:
    session = _succeeded(_accepted(_create()))
    first_payload = copy.deepcopy(to_dict(session.attempts[0]))
    first_serialized = json.dumps(first_payload, sort_keys=True, separators=(",", ":"))
    evaluation, guidance = _evidence(_repeat(), performance_session_id=PERF_1)
    extended = append_evaluated_attempt(
        session,
        evaluation,
        guidance,
        attempt_id=ATTEMPT_1,
    )
    assert extended.status is GuidedPracticeSessionStatus.AWAITING_ACTION
    assert extended.assignment_id == ASSIGNMENT
    assert extended.content_id == CONTENT
    assert extended.canonical_revision_id == REVISION
    assert extended.attempts[1].attempt_index == 1
    assert extended.attempts[1].attempt_id == ATTEMPT_1
    assert extended.attempts[1].performance_session_id == PERF_1
    assert extended.attempts[1].evaluation_digest != session.attempts[0].evaluation_digest
    assert extended.attempts[1].guidance_digest != session.attempts[0].guidance_digest
    assert extended.attempts[0] is session.attempts[0]
    assert to_dict(extended.attempts[0]) == first_payload
    assert json.dumps(to_dict(extended.attempts[0]), sort_keys=True, separators=(",", ":")) == (
        first_serialized
    )


def test_append_after_decline_uses_new_evidence_ids() -> None:
    session = _declined(_create())
    evaluation, guidance = _evidence(performance_session_id=PERF_1)
    extended = append_evaluated_attempt(session, evaluation, guidance, attempt_id=ATTEMPT_1)
    assert session.status is GuidedPracticeSessionStatus.AWAITING_ATTEMPT
    assert extended.attempts[1].action_disposition is GuidedPracticeActionDisposition.PENDING
    assert extended.attempts[1].attempt_id == ATTEMPT_1
    assert extended.attempts[1].guidance_digest == guidance.guidance_digest
    assert extended.status is GuidedPracticeSessionStatus.AWAITING_ACTION


def test_transition_records_lesson_change_and_does_not_create_next_session() -> None:
    session = _create()
    transitioned = transition_session(
        session,
        next_assignment_id=OTHER_ASSIGNMENT,
        next_content_id=OTHER_CONTENT,
    )
    assert transitioned.status is GuidedPracticeSessionStatus.TRANSITIONED
    provenance = dict(transitioned.provenance)
    assert provenance["transition_reason"] == "lesson_content_change"
    assert provenance["next_assignment_id"] == OTHER_ASSIGNMENT
    assert provenance["next_content_id"] == OTHER_CONTENT
    assert len(transitioned.attempts) == 1
    assert transitioned.assignment_id == ASSIGNMENT
    assert transitioned.content_id == CONTENT


# --- invalid transitions -----------------------------------------------------


def test_create_rejects_incomplete_evidence_chain() -> None:
    evaluation, guidance = _evidence()
    with pytest.raises(EducationContractError, match="evidence chain"):
        create_from_first_evaluated_attempt(
            "evaluation",  # type: ignore[arg-type]
            guidance,
            session_id=SESSION_ID,
            attempt_id=ATTEMPT_0,
        )
    with pytest.raises(EducationContractError, match="evidence chain"):
        create_from_first_evaluated_attempt(
            evaluation,
            "guidance",  # type: ignore[arg-type]
            session_id=SESSION_ID,
            attempt_id=ATTEMPT_0,
        )
    mismatched_session = replace(
        guidance,
        performance_session_id=PERF_1,
        guidance_digest=compute_guidance_digest(
            canonical_revision_id=guidance.canonical_revision_id,
            performance_session_id=PERF_1,
            evaluation_digest=guidance.evaluation_digest,
            policy_version=guidance.policy_version,
            items=guidance.items,
            next_action=guidance.next_action,
        ),
    )
    with pytest.raises(EducationContractError, match="performance_session_id"):
        create_from_first_evaluated_attempt(
            evaluation,
            mismatched_session,
            session_id=SESSION_ID,
            attempt_id=ATTEMPT_0,
        )
    mismatched_digest = replace(
        guidance,
        evaluation_digest="sha256:" + ("c" * 64),
        guidance_digest=compute_guidance_digest(
            canonical_revision_id=guidance.canonical_revision_id,
            performance_session_id=guidance.performance_session_id,
            evaluation_digest="sha256:" + ("c" * 64),
            policy_version=guidance.policy_version,
            items=guidance.items,
            next_action=guidance.next_action,
        ),
    )
    with pytest.raises(EducationContractError, match="evaluation_digest"):
        create_from_first_evaluated_attempt(
            evaluation,
            mismatched_digest,
            session_id=SESSION_ID,
            attempt_id=ATTEMPT_0,
        )
    other_action = _repeat()
    mismatched_action = replace(
        guidance,
        next_action=other_action,
        guidance_digest=compute_guidance_digest(
            canonical_revision_id=guidance.canonical_revision_id,
            performance_session_id=guidance.performance_session_id,
            evaluation_digest=guidance.evaluation_digest,
            policy_version=guidance.policy_version,
            items=guidance.items,
            next_action=other_action,
        ),
    )
    with pytest.raises(EducationContractError, match="next_action"):
        create_from_first_evaluated_attempt(
            evaluation,
            mismatched_action,
            session_id=SESSION_ID,
            attempt_id=ATTEMPT_0,
        )


def test_append_rejects_awaiting_action_closed_and_transitioned() -> None:
    awaiting = _create()
    evaluation, guidance = _evidence(performance_session_id=PERF_1)
    with pytest.raises(EducationContractError, match="AWAITING_ATTEMPT"):
        append_evaluated_attempt(awaiting, evaluation, guidance, attempt_id=ATTEMPT_1)
    closed = _succeeded(_accepted(_create(_continue())))
    with pytest.raises(EducationContractError, match="AWAITING_ATTEMPT"):
        append_evaluated_attempt(closed, evaluation, guidance, attempt_id=ATTEMPT_1)
    transitioned = transition_session(
        awaiting,
        next_assignment_id=OTHER_ASSIGNMENT,
        next_content_id=OTHER_CONTENT,
    )
    with pytest.raises(EducationContractError, match="AWAITING_ATTEMPT"):
        append_evaluated_attempt(transitioned, evaluation, guidance, attempt_id=ATTEMPT_1)


def test_append_rejects_wrong_assignment_content_and_revision() -> None:
    session = _declined(_create())
    wrong_assignment, guidance = _evidence(
        assignment_id=OTHER_ASSIGNMENT,
        performance_session_id=PERF_1,
    )
    with pytest.raises(EducationContractError, match="assignment_id"):
        append_evaluated_attempt(session, wrong_assignment, guidance, attempt_id=ATTEMPT_1)
    evaluation, _ = _evidence(performance_session_id=PERF_1)
    wrong_content = _evaluation(
        _slow_down(),
        content_id=OTHER_CONTENT,
        performance_session_id=PERF_1,
    )
    with pytest.raises(EducationContractError, match="content_id"):
        append_evaluated_attempt(
            session,
            wrong_content,
            _guidance(wrong_content),
            attempt_id=ATTEMPT_1,
        )
    wrong_revision = _guidance(evaluation, canonical_revision_id=OTHER_REVISION)
    with pytest.raises(EducationContractError, match="canonical_revision_id"):
        append_evaluated_attempt(session, evaluation, wrong_revision, attempt_id=ATTEMPT_1)


def test_append_rejects_duplicate_attempt_id_and_index() -> None:
    session = _declined(_create())
    evaluation, guidance = _evidence(performance_session_id=PERF_1)
    with pytest.raises(EducationContractError, match="duplicate attempt_id"):
        append_evaluated_attempt(session, evaluation, guidance, attempt_id=ATTEMPT_0)
    with pytest.raises(EducationContractError, match="duplicate attempt_index"):
        append_evaluated_attempt(
            session,
            evaluation,
            guidance,
            attempt_id=ATTEMPT_1,
            attempt_index=0,
        )


def test_disposition_without_recommendation_is_rejected() -> None:
    with pytest.raises(EducationContractError, match="recommended_action"):
        record_action_disposition(_empty_session(), GuidedPracticeActionDisposition.ACCEPTED)


def test_second_disposition_is_rejected() -> None:
    accepted = _accepted(_create())
    with pytest.raises(EducationContractError, match="already resolved"):
        record_action_disposition(accepted, GuidedPracticeActionDisposition.DECLINED)
    declined = _declined(_create())
    with pytest.raises(EducationContractError, match="AWAITING_ACTION"):
        record_action_disposition(declined, GuidedPracticeActionDisposition.ACCEPTED)


def test_execution_before_acceptance_is_rejected() -> None:
    with pytest.raises(EducationContractError, match="before acceptance"):
        record_action_execution(_create(), GuidedPracticeExecutionStatus.SUCCEEDED)


def test_execution_after_decline_is_rejected() -> None:
    declined = _declined(_create())
    with pytest.raises(EducationContractError, match="declined"):
        record_action_execution(declined, GuidedPracticeExecutionStatus.SUCCEEDED)


def test_succeeded_is_rejected_for_unsupported_actions() -> None:
    session = _accepted(_create(_view_one_string()))
    with pytest.raises(EducationContractError, match="unsupported"):
        record_action_execution(session, GuidedPracticeExecutionStatus.SUCCEEDED)
    zone = _accepted(_create(_enable_zone_view()))
    with pytest.raises(EducationContractError, match="unsupported"):
        record_action_execution(zone, GuidedPracticeExecutionStatus.SUCCEEDED)


def test_continue_cannot_close_before_successful_execution() -> None:
    pending = _create(_continue())
    assert pending.status is GuidedPracticeSessionStatus.AWAITING_ACTION
    accepted = _accepted(pending)
    assert accepted.status is GuidedPracticeSessionStatus.AWAITING_ACTION
    failed = record_action_execution(accepted, GuidedPracticeExecutionStatus.FAILED)
    assert failed.status is GuidedPracticeSessionStatus.AWAITING_ATTEMPT
    assert failed.status is not GuidedPracticeSessionStatus.CLOSED


def test_continue_unsupported_is_rejected() -> None:
    with pytest.raises(EducationContractError, match="UNSUPPORTED"):
        record_action_execution(
            _accepted(_create(_continue())),
            GuidedPracticeExecutionStatus.UNSUPPORTED,
        )


@pytest.mark.parametrize(
    "action_factory",
    [_slow_down, _isolate, _repeat],
    ids=["slow_down", "isolate_passage", "repeat"],
)
def test_supported_keep_open_actions_reject_unsupported(action_factory: object) -> None:
    with pytest.raises(EducationContractError, match="UNSUPPORTED"):
        record_action_execution(
            _accepted(_create(action_factory())),  # type: ignore[operator]
            GuidedPracticeExecutionStatus.UNSUPPORTED,
        )


def test_transition_rejects_terminal_sessions_and_same_lesson() -> None:
    closed = _succeeded(_accepted(_create(_continue())))
    with pytest.raises(EducationContractError, match="terminal"):
        transition_session(
            closed,
            next_assignment_id=OTHER_ASSIGNMENT,
            next_content_id=OTHER_CONTENT,
        )
    transitioned = transition_session(
        _create(),
        next_assignment_id=OTHER_ASSIGNMENT,
        next_content_id=OTHER_CONTENT,
    )
    with pytest.raises(EducationContractError, match="terminal"):
        transition_session(
            transitioned,
            next_assignment_id=OTHER_ASSIGNMENT,
            next_content_id=CONTENT,
        )
    with pytest.raises(EducationContractError, match="assignment or content"):
        transition_session(_create(), next_assignment_id=ASSIGNMENT, next_content_id=CONTENT)


def test_service_types_are_required() -> None:
    evaluation, guidance = _evidence()
    with pytest.raises(EducationContractError, match="GuidedPracticeSessionV1"):
        append_evaluated_attempt(
            "session",  # type: ignore[arg-type]
            evaluation,
            guidance,
            attempt_id=ATTEMPT_1,
        )
    with pytest.raises(EducationContractError, match="GuidedPracticeSessionV1"):
        record_action_disposition("session", GuidedPracticeActionDisposition.ACCEPTED)  # type: ignore[arg-type]


def test_service_does_not_choose_or_drive_external_authorities() -> None:
    source = inspect.getsource(guided_session_service)
    if source.startswith('"""'):
        source = source.split('"""', 2)[2]
    for token in (
        "choose_primary_next_action",
        "education.recommendations",
        "education.evaluation",
        "education.guidance_builder",
        "master_all_strings.mvp",
        "master_all_strings.performance",
        "PracticeEvaluator",
        "uuid4",
        "uuid.uuid4",
    ):
        assert token not in source


def test_create_requires_caller_supplied_opaque_ids() -> None:
    evaluation, guidance = _evidence()
    with pytest.raises(TypeError, match="session_id"):
        create_from_first_evaluated_attempt(evaluation, guidance)
    with pytest.raises(EducationContractError, match="session_id"):
        create_from_first_evaluated_attempt(
            evaluation,
            guidance,
            session_id="",
            attempt_id=ATTEMPT_0,
        )
    with pytest.raises(EducationContractError, match="attempt_id"):
        create_from_first_evaluated_attempt(
            evaluation,
            guidance,
            session_id=SESSION_ID,
            attempt_id=" ",
        )


def test_append_requires_caller_supplied_attempt_id() -> None:
    session = _declined(_create())
    evaluation, guidance = _evidence(performance_session_id=PERF_1)
    with pytest.raises(TypeError, match="attempt_id"):
        append_evaluated_attempt(session, evaluation, guidance)
    with pytest.raises(EducationContractError, match="attempt_id"):
        append_evaluated_attempt(session, evaluation, guidance, attempt_id="")


def test_pending_disposition_and_invalid_execution_status_are_rejected() -> None:
    session = _create()
    with pytest.raises(EducationContractError, match="ACCEPTED or DECLINED"):
        record_action_disposition(session, GuidedPracticeActionDisposition.PENDING)
    accepted = _accepted(session)
    with pytest.raises(EducationContractError, match="SUCCEEDED, FAILED, or UNSUPPORTED"):
        record_action_execution(accepted, GuidedPracticeExecutionStatus.NOT_REQUESTED)


def test_append_rejects_duplicate_performance_session_id() -> None:
    session = _declined(_create())
    evaluation, guidance = _evidence(performance_session_id=PERF_0)
    with pytest.raises(EducationContractError, match="performance_session_id"):
        append_evaluated_attempt(session, evaluation, guidance, attempt_id=ATTEMPT_1)


def test_public_lifecycle_api_excludes_close_and_begin_next() -> None:
    from master_all_strings import education

    for name in ("close_session", "begin_next_attempt"):
        assert name not in education.__all__
        assert name not in guided_session_service.__all__
        assert not hasattr(education, name)
        assert not hasattr(guided_session_service, name)
    for name in (
        "create_from_first_evaluated_attempt",
        "append_evaluated_attempt",
        "record_action_disposition",
        "record_action_execution",
        "transition_session",
    ):
        assert name in education.__all__
        assert name in guided_session_service.__all__


def test_transition_accepts_assignment_only_change() -> None:
    session = _declined(_create())
    transitioned = transition_session(
        session,
        next_assignment_id=OTHER_ASSIGNMENT,
        next_content_id=CONTENT,
    )
    assert transitioned.status is GuidedPracticeSessionStatus.TRANSITIONED


def test_omitted_executed_action_records_the_recommendation() -> None:
    session = _succeeded(_accepted(_create()))
    recorded = session.attempts[0].executed_action
    recommended = session.attempts[0].recommended_action
    assert recorded is recommended
    assert recorded == recommended


def test_executed_action_cannot_hide_a_different_action_type() -> None:
    accepted = _accepted(_create(_slow_down()))
    with pytest.raises(EducationContractError, match="action_type"):
        record_action_execution(
            accepted,
            GuidedPracticeExecutionStatus.SUCCEEDED,
            executed_action=_continue(),
        )
    with pytest.raises(EducationContractError, match="action_type"):
        record_action_execution(
            accepted,
            GuidedPracticeExecutionStatus.FAILED,
            executed_action=_repeat(),
        )
    continue_accepted = _accepted(_create(_continue()))
    with pytest.raises(EducationContractError, match="action_type"):
        record_action_execution(
            continue_accepted,
            GuidedPracticeExecutionStatus.SUCCEEDED,
            executed_action=_slow_down(),
        )
    assert continue_accepted.status is GuidedPracticeSessionStatus.AWAITING_ACTION


def test_unsupported_rejects_a_supplied_executed_action() -> None:
    with pytest.raises(EducationContractError, match="executed_action"):
        record_action_execution(
            _accepted(_create(_view_one_string())),
            GuidedPracticeExecutionStatus.UNSUPPORTED,
            executed_action=_view_one_string(),
        )


def test_execution_records_an_explicit_executed_action() -> None:
    session = record_action_execution(
        _accepted(_create()),
        GuidedPracticeExecutionStatus.SUCCEEDED,
        executed_action=_slow_down(0.5),
    )
    assert session.attempts[0].executed_action is not None
    assert session.attempts[0].executed_action.action_type is PracticeNextActionType.SLOW_DOWN
    assert session.attempts[0].executed_action.target_rate == 0.5
    assert session.attempts[0].recommended_action.target_rate == 0.75


def test_execution_rejects_stale_status_and_already_resolved_facts() -> None:
    accepted = _accepted(_create())
    awaiting_attempt = session_with_digest(
        replace(
            accepted,
            status=GuidedPracticeSessionStatus.AWAITING_ATTEMPT,
            session_digest="sha256:" + ("0" * 64),
        )
    )
    with pytest.raises(EducationContractError, match="AWAITING_ACTION"):
        record_action_execution(awaiting_attempt, GuidedPracticeExecutionStatus.SUCCEEDED)
    finished = session_with_digest(
        replace(
            _succeeded(accepted),
            status=GuidedPracticeSessionStatus.AWAITING_ACTION,
            session_digest="sha256:" + ("0" * 64),
        )
    )
    with pytest.raises(EducationContractError, match="already resolved"):
        record_action_execution(finished, GuidedPracticeExecutionStatus.FAILED)


def test_empty_session_cannot_execute() -> None:
    empty = _empty_session()
    with pytest.raises(EducationContractError, match="no current attempt"):
        record_action_execution(empty, GuidedPracticeExecutionStatus.SUCCEEDED)


def test_unknown_disposition_value_is_rejected() -> None:
    with pytest.raises(EducationContractError, match="ACCEPTED or DECLINED"):
        record_action_disposition(_create(), "FOO")  # type: ignore[arg-type]


def test_recommendation_is_copied_not_recomputed() -> None:
    evaluation, guidance = _evidence(_isolate())
    session = create_from_first_evaluated_attempt(
        evaluation,
        guidance,
        session_id=SESSION_ID,
        attempt_id=ATTEMPT_0,
    )
    assert session.attempts[0].recommended_action == guidance.next_action
    assert session.attempts[0].recommended_action == evaluation.primary_next_action
    assert session.attempts[0].recommended_action.focus_start_tick == 0
    assert session.attempts[0].recommended_action.focus_end_tick == 480
