"""DO-015 Stage 8 gap-fill: hostile transitions the Stage 2 suite does not own.

Stage 2 already rejects the common illegal transitions one at a time. These
cases are the combinations and the append-time evidence-chain checks that
suite left implicit, plus the proof that a later disposition cannot rewrite an
earlier attempt.
"""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path

from master_all_strings.education import (
    EducationContractError,
    GuidedPracticeActionDisposition,
    GuidedPracticeExecutionStatus,
    GuidedPracticeSessionStatus,
    append_evaluated_attempt,
    compute_guidance_digest,
    record_action_disposition,
    session_with_digest,
    to_dict,
)

_STAGE2_PATH = Path(__file__).with_name("test_guided_session_service_do015.py")


def _stage2():
    spec = importlib.util.spec_from_file_location("do015_stage2_helpers", _STAGE2_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _open_for_append():
    stage2 = _stage2()
    return stage2._declined(stage2._create()), stage2


def test_append_rejects_evidence_chain_disagreements_without_mutation() -> None:
    session, stage2 = _open_for_append()
    before = to_dict(session)
    evaluation, guidance = stage2._evidence(performance_session_id=stage2.PERF_1)

    mismatched_performance = replace(
        guidance,
        performance_session_id=stage2.PERF_0,
        guidance_digest=compute_guidance_digest(
            canonical_revision_id=guidance.canonical_revision_id,
            performance_session_id=stage2.PERF_0,
            evaluation_digest=guidance.evaluation_digest,
            policy_version=guidance.policy_version,
            items=guidance.items,
            next_action=guidance.next_action,
        ),
    )
    try:
        append_evaluated_attempt(
            session,
            evaluation,
            mismatched_performance,
            attempt_id=stage2.ATTEMPT_1,
        )
    except EducationContractError as exc:
        assert "performance_session_id" in str(exc)
    else:
        raise AssertionError("mismatched performance identity was appended")

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
    try:
        append_evaluated_attempt(
            session,
            evaluation,
            mismatched_digest,
            attempt_id=stage2.ATTEMPT_1,
        )
    except EducationContractError as exc:
        assert "evaluation_digest" in str(exc)
    else:
        raise AssertionError("mismatched evaluation digest was appended")

    other_action = stage2._repeat()
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
    try:
        append_evaluated_attempt(
            session,
            evaluation,
            mismatched_action,
            attempt_id=stage2.ATTEMPT_1,
        )
    except EducationContractError as exc:
        assert "next_action" in str(exc)
    else:
        raise AssertionError("mismatched recommendation was appended")

    assert to_dict(session) == before


def test_append_rejects_every_pin_at_once_without_mutation() -> None:
    session, stage2 = _open_for_append()
    before = to_dict(session)
    evaluation = stage2._evaluation(
        stage2._repeat(),
        assignment_id=stage2.OTHER_ASSIGNMENT,
        content_id=stage2.OTHER_CONTENT,
        performance_session_id=stage2.PERF_1,
    )
    guidance = stage2._guidance(evaluation, canonical_revision_id=stage2.OTHER_REVISION)
    try:
        append_evaluated_attempt(session, evaluation, guidance, attempt_id=stage2.ATTEMPT_1)
    except EducationContractError as exc:
        assert "assignment_id" in str(exc)
    else:
        raise AssertionError("cross-lesson evidence was appended")
    assert to_dict(session) == before
    assert len(session.attempts) == 1


def test_disposition_does_not_rewrite_the_historical_attempt() -> None:
    stage2 = _stage2()
    first = stage2._declined(stage2._create())
    historical = first.attempts[0]
    evaluation, guidance = stage2._evidence(performance_session_id=stage2.PERF_1)
    session = append_evaluated_attempt(
        first,
        evaluation,
        guidance,
        attempt_id=stage2.ATTEMPT_1,
    )
    updated = record_action_disposition(session, GuidedPracticeActionDisposition.ACCEPTED)
    assert updated.attempts[0] == historical
    assert updated.attempts[0].action_disposition is GuidedPracticeActionDisposition.DECLINED
    assert updated.attempts[1].action_disposition is GuidedPracticeActionDisposition.ACCEPTED
    assert updated.current_attempt_index == 1
    assert len(updated.attempts) == 2


def test_aborted_session_rejects_append_and_disposition() -> None:
    session, stage2 = _open_for_append()
    aborted = session_with_digest(
        replace(
            session,
            status=GuidedPracticeSessionStatus.ABORTED,
            session_digest="sha256:" + ("0" * 64),
        )
    )
    before = to_dict(aborted)
    evaluation, guidance = stage2._evidence(performance_session_id=stage2.PERF_1)
    try:
        append_evaluated_attempt(aborted, evaluation, guidance, attempt_id=stage2.ATTEMPT_1)
    except EducationContractError as exc:
        assert "AWAITING_ATTEMPT" in str(exc)
    else:
        raise AssertionError("an aborted session accepted an append")
    try:
        record_action_disposition(aborted, GuidedPracticeActionDisposition.ACCEPTED)
    except EducationContractError as exc:
        assert "AWAITING_ACTION" in str(exc)
    else:
        raise AssertionError("an aborted session accepted a disposition")
    assert to_dict(aborted) == before


def test_second_execution_does_not_change_a_resolved_attempt() -> None:
    stage2 = _stage2()
    finished = stage2._succeeded(stage2._accepted(stage2._create()))
    before = to_dict(finished)
    try:
        stage2.record_action_execution(finished, GuidedPracticeExecutionStatus.FAILED)
    except EducationContractError as exc:
        assert "AWAITING_ACTION" in str(exc)
    else:
        raise AssertionError("a second execution was recorded")
    assert to_dict(finished) == before
