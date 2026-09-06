"""DO-015 Stage 1: GuidedPracticeSessionV1 contract, schema, serialization."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from jsonschema import Draft202012Validator

from master_all_strings.education import (
    SESSION_POLICY_VERSION,
    SESSION_SCHEMA_VERSION,
    EducationContractError,
    GuidedPracticeActionDisposition,
    GuidedPracticeActionV1,
    GuidedPracticeAttemptV1,
    GuidedPracticeContextV1,
    GuidedPracticeExecutionStatus,
    GuidedPracticeSessionStatus,
    GuidedPracticeSessionV1,
    PracticeNextActionType,
    PracticeNextActionV1,
    append_attempt,
    compute_session_digest,
    serialize_guided_practice_session,
    session_with_digest,
    to_dict,
)

REPO = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO / "resources" / "education" / "schema" / "guided_practice_session_v1.schema.json"

EVAL_DIGEST = "sha256:" + ("a" * 64)
GUIDANCE_DIGEST = "sha256:" + ("b" * 64)
SESSION_ID = "11111111-1111-4111-8111-111111111111"
ATTEMPT_ID_0 = "22222222-2222-4222-8222-222222222222"
ATTEMPT_ID_1 = "33333333-3333-4333-8333-333333333333"
ASSIGNMENT_ID = "44444444-4444-4444-8444-444444444444"
CONTENT_ID = "55555555-5555-4555-8555-555555555555"
REVISION_ID = "66666666-6666-4666-8666-666666666666"
PERFORMANCE_0 = "77777777-7777-4777-8777-777777777777"
PERFORMANCE_1 = "88888888-8888-4888-8888-888888888888"


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


def _pending_action(recommended: PracticeNextActionV1 | None = None) -> GuidedPracticeActionV1:
    return GuidedPracticeActionV1(
        schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
        recommended_action=recommended or _slow_down(),
        action_disposition=GuidedPracticeActionDisposition.PENDING,
        execution_status=GuidedPracticeExecutionStatus.NOT_REQUESTED,
    )


def _context(
    *,
    playback_rate: float | None = 1.0,
    loop_start_tick: int | None = None,
    loop_end_tick: int | None = None,
) -> GuidedPracticeContextV1:
    return GuidedPracticeContextV1(
        schema_version=GuidedPracticeContextV1.SCHEMA_VERSION,
        playback_rate=playback_rate,
        loop_start_tick=loop_start_tick,
        loop_end_tick=loop_end_tick,
    )


def _attempt(
    *,
    attempt_id: str = ATTEMPT_ID_0,
    attempt_index: int = 0,
    assignment_id: str = ASSIGNMENT_ID,
    content_id: str = CONTENT_ID,
    canonical_revision_id: str = REVISION_ID,
    performance_session_id: str = PERFORMANCE_0,
    evaluation_digest: str = EVAL_DIGEST,
    guidance_digest: str = GUIDANCE_DIGEST,
    action: GuidedPracticeActionV1 | None = None,
    practice_context: GuidedPracticeContextV1 | None = None,
) -> GuidedPracticeAttemptV1:
    return GuidedPracticeAttemptV1(
        schema_version=GuidedPracticeAttemptV1.SCHEMA_VERSION,
        attempt_id=attempt_id,
        attempt_index=attempt_index,
        assignment_id=assignment_id,
        content_id=content_id,
        canonical_revision_id=canonical_revision_id,
        performance_session_id=performance_session_id,
        evaluation_digest=evaluation_digest,
        guidance_digest=guidance_digest,
        action=action or _pending_action(),
        practice_context=practice_context or _context(),
    )


def _session(
    attempts: tuple[GuidedPracticeAttemptV1, ...] = (),
    *,
    status: GuidedPracticeSessionStatus = GuidedPracticeSessionStatus.AWAITING_ATTEMPT,
    provenance: tuple[tuple[str, str], ...] = (("producer", "GuidedPracticeSessionV1"),),
    session_id: str = SESSION_ID,
    assignment_id: str = ASSIGNMENT_ID,
    content_id: str = CONTENT_ID,
    canonical_revision_id: str = REVISION_ID,
) -> GuidedPracticeSessionV1:
    draft = GuidedPracticeSessionV1(
        schema_version=GuidedPracticeSessionV1.SCHEMA_VERSION,
        policy_version=SESSION_POLICY_VERSION,
        session_id=session_id,
        assignment_id=assignment_id,
        content_id=content_id,
        canonical_revision_id=canonical_revision_id,
        status=status,
        attempts=attempts,
        current_attempt_index=None if not attempts else len(attempts) - 1,
        session_digest="sha256:" + ("0" * 64),
        provenance=provenance,
    )
    return session_with_digest(draft)


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


# --- contract construction ---------------------------------------------------


def test_schema_and_policy_versions_are_explicit() -> None:
    assert SESSION_SCHEMA_VERSION == "1.0.0"
    assert SESSION_POLICY_VERSION == "guided-practice-session-v1"
    assert GuidedPracticeSessionV1.SCHEMA_VERSION == SESSION_SCHEMA_VERSION


def test_empty_session_is_valid_and_satisfies_schema() -> None:
    session = _session()
    assert session.attempts == ()
    assert session.current_attempt_index is None
    assert session.status is GuidedPracticeSessionStatus.AWAITING_ATTEMPT
    jsonschema.validate(to_dict(session), _schema())


def test_session_uses_fixed_opaque_test_ids() -> None:
    session = _session((_attempt(),))
    assert session.session_id == SESSION_ID
    assert session.attempts[0].attempt_id == ATTEMPT_ID_0
    assert session.attempts[0].performance_session_id == PERFORMANCE_0
    serialized = serialize_guided_practice_session(session)
    assert SESSION_ID in serialized
    assert ATTEMPT_ID_0 in serialized
    assert "half_steps" not in serialized


def test_attempt_indexes_must_be_monotonic_from_zero() -> None:
    with pytest.raises(EducationContractError, match="monotonic"):
        _session((_attempt(attempt_index=1),))
    first = _attempt()
    second = _attempt(
        attempt_id=ATTEMPT_ID_1,
        attempt_index=2,
        performance_session_id=PERFORMANCE_1,
    )
    with pytest.raises(EducationContractError, match="monotonic"):
        _session((first, second))


def test_duplicate_attempt_ids_are_rejected() -> None:
    first = _attempt()
    second = _attempt(attempt_index=1, performance_session_id=PERFORMANCE_1)
    with pytest.raises(EducationContractError, match="attempt_id"):
        _session((first, second))


def test_attempts_must_match_session_identity() -> None:
    with pytest.raises(EducationContractError, match="assignment_id"):
        _session((_attempt(assignment_id="other-assignment"),))
    with pytest.raises(EducationContractError, match="content_id"):
        _session((_attempt(content_id="other-content"),))
    with pytest.raises(EducationContractError, match="canonical_revision_id"):
        _session((_attempt(canonical_revision_id="other-revision"),))


def test_recommendation_is_recorded_exactly() -> None:
    recommended = _slow_down(0.5)
    attempt = _attempt(action=_pending_action(recommended))
    session = _session((attempt,), status=GuidedPracticeSessionStatus.AWAITING_ACTION)
    recorded = session.attempts[0].recommended_action
    assert recorded == recommended
    assert recorded.action_type is PracticeNextActionType.SLOW_DOWN
    assert recorded.target_rate == 0.5
    payload = to_dict(session)
    assert payload["attempts"][0]["action"]["recommended_action"]["action_type"] == "slow_down"
    assert payload["attempts"][0]["action"]["recommended_action"]["target_rate"] == 0.5
    assert "secondary_actions" not in payload["attempts"][0]
    assert "secondary_actions" not in payload["attempts"][0]["action"]


def test_accepted_does_not_imply_succeeded() -> None:
    action = GuidedPracticeActionV1(
        schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
        recommended_action=_slow_down(),
        action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
        execution_status=GuidedPracticeExecutionStatus.NOT_REQUESTED,
    )
    assert action.action_disposition is GuidedPracticeActionDisposition.ACCEPTED
    assert action.execution_status is GuidedPracticeExecutionStatus.NOT_REQUESTED
    assert action.executed_action is None


def test_recommended_and_executed_may_differ() -> None:
    declined = GuidedPracticeActionV1(
        schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
        recommended_action=_slow_down(),
        action_disposition=GuidedPracticeActionDisposition.DECLINED,
        execution_status=GuidedPracticeExecutionStatus.NOT_REQUESTED,
    )
    failed = GuidedPracticeActionV1(
        schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
        recommended_action=_isolate(),
        action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
        execution_status=GuidedPracticeExecutionStatus.FAILED,
        executed_action=_isolate(),
    )
    unsupported = GuidedPracticeActionV1(
        schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
        recommended_action=_view_one_string(),
        action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
        execution_status=GuidedPracticeExecutionStatus.UNSUPPORTED,
    )
    assert declined.recommended_action.action_type is PracticeNextActionType.SLOW_DOWN
    assert declined.executed_action is None
    assert failed.execution_status is GuidedPracticeExecutionStatus.FAILED
    assert unsupported.execution_status is GuidedPracticeExecutionStatus.UNSUPPORTED
    assert unsupported.executed_action is None


def test_educational_view_actions_can_be_unsupported() -> None:
    for recommended in (_view_one_string(), _enable_zone_view()):
        action = GuidedPracticeActionV1(
            schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
            recommended_action=recommended,
            action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
            execution_status=GuidedPracticeExecutionStatus.UNSUPPORTED,
        )
        assert action.execution_status is GuidedPracticeExecutionStatus.UNSUPPORTED
        assert action.executed_action is None


def test_continue_is_never_serialized_as_mastery() -> None:
    action = GuidedPracticeActionV1(
        schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
        recommended_action=_continue(),
        action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
        execution_status=GuidedPracticeExecutionStatus.SUCCEEDED,
        executed_action=_continue(),
    )
    session = _session(
        (_attempt(action=action),),
        status=GuidedPracticeSessionStatus.CLOSED,
    )
    text = serialize_guided_practice_session(session).lower()
    for token in ("mastered", "perfect", "complete", "passed curriculum"):
        assert token not in text
    assert session.attempts[0].recommended_action.action_type is PracticeNextActionType.CONTINUE


def test_append_does_not_mutate_prior_attempts() -> None:
    first = _attempt()
    session = _session((first,), status=GuidedPracticeSessionStatus.AWAITING_ACTION)
    first_payload = copy.deepcopy(to_dict(session)["attempts"][0])
    second = _attempt(
        attempt_id=ATTEMPT_ID_1,
        attempt_index=1,
        performance_session_id=PERFORMANCE_1,
        action=_pending_action(_repeat()),
    )
    extended = append_attempt(session, second, status=GuidedPracticeSessionStatus.AWAITING_ACTION)
    assert to_dict(extended)["attempts"][0] == first_payload
    assert extended.attempts[0] is session.attempts[0]
    assert extended.attempts[0] is first
    assert len(extended.attempts) == 2
    assert extended.current_attempt_index == 1


def test_append_rejects_out_of_order_index() -> None:
    session = _session((_attempt(),))
    late = _attempt(
        attempt_id=ATTEMPT_ID_1,
        attempt_index=2,
        performance_session_id=PERFORMANCE_1,
    )
    with pytest.raises(EducationContractError, match="attempt_index"):
        append_attempt(session, late)


def test_empty_session_rejects_nonzero_current_index() -> None:
    with pytest.raises(EducationContractError, match="current_attempt_index"):
        GuidedPracticeSessionV1(
            schema_version=SESSION_SCHEMA_VERSION,
            policy_version=SESSION_POLICY_VERSION,
            session_id=SESSION_ID,
            assignment_id=ASSIGNMENT_ID,
            content_id=CONTENT_ID,
            canonical_revision_id=REVISION_ID,
            status=GuidedPracticeSessionStatus.AWAITING_ATTEMPT,
            attempts=(),
            current_attempt_index=0,
            session_digest="sha256:" + ("0" * 64),
        )


def test_disposition_execution_invariants() -> None:
    with pytest.raises(EducationContractError, match="PENDING disposition"):
        GuidedPracticeActionV1(
            schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
            recommended_action=_slow_down(),
            action_disposition=GuidedPracticeActionDisposition.PENDING,
            execution_status=GuidedPracticeExecutionStatus.PENDING,
        )
    with pytest.raises(EducationContractError, match="DECLINED"):
        GuidedPracticeActionV1(
            schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
            recommended_action=_slow_down(),
            action_disposition=GuidedPracticeActionDisposition.DECLINED,
            execution_status=GuidedPracticeExecutionStatus.FAILED,
        )
    with pytest.raises(EducationContractError, match="SUCCEEDED requires"):
        GuidedPracticeActionV1(
            schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
            recommended_action=_continue(),
            action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
            execution_status=GuidedPracticeExecutionStatus.SUCCEEDED,
        )
    with pytest.raises(EducationContractError, match="UNSUPPORTED"):
        GuidedPracticeActionV1(
            schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
            recommended_action=_view_one_string(),
            action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
            execution_status=GuidedPracticeExecutionStatus.UNSUPPORTED,
            executed_action=_view_one_string(),
        )


def test_context_requires_paired_loop_bounds() -> None:
    with pytest.raises(EducationContractError, match="loop bounds"):
        _context(loop_start_tick=0)
    with pytest.raises(EducationContractError, match="loop_end_tick"):
        _context(loop_start_tick=480, loop_end_tick=0)
    with pytest.raises(EducationContractError, match="playback_rate"):
        _context(playback_rate=1.25)


def test_malformed_nested_types_are_rejected() -> None:
    with pytest.raises(EducationContractError, match="GuidedPracticeActionV1"):
        GuidedPracticeAttemptV1(
            schema_version=SESSION_SCHEMA_VERSION,
            attempt_id=ATTEMPT_ID_0,
            attempt_index=0,
            assignment_id=ASSIGNMENT_ID,
            content_id=CONTENT_ID,
            canonical_revision_id=REVISION_ID,
            performance_session_id=PERFORMANCE_0,
            evaluation_digest=EVAL_DIGEST,
            guidance_digest=GUIDANCE_DIGEST,
            action="pending",  # type: ignore[arg-type]
            practice_context=_context(),
        )
    with pytest.raises(EducationContractError, match="status"):
        GuidedPracticeSessionV1(
            schema_version=SESSION_SCHEMA_VERSION,
            policy_version=SESSION_POLICY_VERSION,
            session_id=SESSION_ID,
            assignment_id=ASSIGNMENT_ID,
            content_id=CONTENT_ID,
            canonical_revision_id=REVISION_ID,
            status="ACTIVE",  # type: ignore[arg-type]
            attempts=(),
            current_attempt_index=None,
            session_digest="sha256:" + ("0" * 64),
        )


def test_attempt_requires_sha256_digests() -> None:
    with pytest.raises(EducationContractError, match="evaluation_digest"):
        _attempt(evaluation_digest="md5:abcd")
    with pytest.raises(EducationContractError, match="guidance_digest"):
        _attempt(guidance_digest="not-a-digest")


# --- serialization / digest --------------------------------------------------


def test_round_trip_is_semantically_equal() -> None:
    session = _session(
        (_attempt(),),
        status=GuidedPracticeSessionStatus.AWAITING_ACTION,
    )
    payload = json.loads(serialize_guided_practice_session(session))
    assert payload["schema_version"] == "1.0.0"
    assert payload["session_id"] == SESSION_ID
    assert payload["attempts"][0]["attempt_id"] == ATTEMPT_ID_0
    assert payload["session_digest"] == session.session_digest
    assert compute_session_digest(session) == session.session_digest


def test_digest_ignores_provenance() -> None:
    plain = _session(provenance=(("producer", "a"),))
    audited = _session(
        provenance=(("producer", "b"), ("assembled_at", "wall-clock")),
    )
    assert plain.session_digest == audited.session_digest


def test_digest_changes_when_attempt_content_changes() -> None:
    a = _session((_attempt(action=_pending_action(_slow_down())),))
    b = _session((_attempt(action=_pending_action(_repeat())),))
    assert a.session_digest != b.session_digest


def test_session_with_digest_is_idempotent() -> None:
    session = _session()
    assert session_with_digest(session) is session


def test_serialize_rejects_non_session() -> None:
    with pytest.raises(EducationContractError):
        serialize_guided_practice_session(_attempt())  # type: ignore[arg-type]
    with pytest.raises(EducationContractError):
        compute_session_digest(_attempt())  # type: ignore[arg-type]


def test_attempt_field_names_do_not_invent_aliases() -> None:
    names = {item.name for item in fields(GuidedPracticeAttemptV1)}
    assert names == {
        "schema_version",
        "attempt_id",
        "attempt_index",
        "assignment_id",
        "content_id",
        "canonical_revision_id",
        "performance_session_id",
        "evaluation_digest",
        "guidance_digest",
        "action",
        "practice_context",
    }


# --- schema ------------------------------------------------------------------


def test_session_schema_is_well_formed() -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == "1.0.0"
    assert schema["$id"].endswith("guided-practice-session-v1.schema.json")
    assert "UNSUPPORTED" in schema["$defs"]["executionStatus"]["enum"]


def test_valid_sessions_satisfy_schema() -> None:
    jsonschema.validate(to_dict(_session()), _schema())
    accepted = GuidedPracticeActionV1(
        schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
        recommended_action=_slow_down(),
        action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
        execution_status=GuidedPracticeExecutionStatus.SUCCEEDED,
        executed_action=_slow_down(),
    )
    populated = _session(
        (
            _attempt(
                action=accepted,
                practice_context=_context(playback_rate=0.75, loop_start_tick=0, loop_end_tick=480),
            ),
        ),
        status=GuidedPracticeSessionStatus.AWAITING_ATTEMPT,
    )
    jsonschema.validate(to_dict(populated), _schema())


Mutation = Callable[[dict[str, Any]], None]


def _drop(*path: str | int) -> Mutation:
    def mutate(payload: dict[str, Any]) -> None:
        target: Any = payload
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return mutate


def _set(*path: Any) -> Mutation:
    *keys, value = path

    def mutate(payload: dict[str, Any]) -> None:
        target: Any = payload
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value

    return mutate


REJECTIONS: tuple[tuple[str, Mutation], ...] = (
    ("missing schema version", _drop("schema_version")),
    ("missing session id", _drop("session_id")),
    ("unknown status", _set("status", "PAUSED")),
    ("malformed session digest", _set("session_digest", "md5:abcd")),
    ("unexpected object shape", _set("score_override", {"midi": 60})),
    ("malformed attempt id", _set("attempts", 0, "attempt_id", "")),
    ("unknown disposition", _set("attempts", 0, "action", "action_disposition", "IGNORED")),
    ("unknown execution status", _set("attempts", 0, "action", "execution_status", "SKIPPED")),
    (
        "invalid recommended action",
        _set("attempts", 0, "action", "recommended_action", "action_type", "mastered"),
    ),
    ("malformed evaluation digest", _set("attempts", 0, "evaluation_digest", "not-a-digest")),
)


@pytest.mark.parametrize("label,mutate", REJECTIONS, ids=[row[0] for row in REJECTIONS])
def test_schema_rejects_malformed_sessions(label: str, mutate: Mutation) -> None:
    payload = to_dict(_session((_attempt(),)))
    mutate(payload)
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(payload)


def test_schema_does_not_accept_a_mutated_copy_of_a_valid_payload() -> None:
    payload = copy.deepcopy(to_dict(_session((_attempt(),))))
    payload["attempts"][0]["action"]["recommended_action"]["action_type"] = "mastered"
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(payload)


def test_session_with_digest_is_a_declared_export() -> None:
    from master_all_strings.education import guided_session

    assert "session_with_digest" in guided_session.__all__
    assert "append_attempt" in guided_session.__all__


def test_action_enum_and_next_action_types_are_required() -> None:
    with pytest.raises(EducationContractError, match="action_disposition"):
        GuidedPracticeActionV1(
            schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
            recommended_action=_slow_down(),
            action_disposition="PENDING",  # type: ignore[arg-type]
            execution_status=GuidedPracticeExecutionStatus.NOT_REQUESTED,
        )
    with pytest.raises(EducationContractError, match="execution_status"):
        GuidedPracticeActionV1(
            schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
            recommended_action=_slow_down(),
            action_disposition=GuidedPracticeActionDisposition.PENDING,
            execution_status="NOT_REQUESTED",  # type: ignore[arg-type]
        )
    with pytest.raises(EducationContractError, match="recommended_action"):
        GuidedPracticeActionV1(
            schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
            recommended_action="slow_down",  # type: ignore[arg-type]
            action_disposition=GuidedPracticeActionDisposition.PENDING,
            execution_status=GuidedPracticeExecutionStatus.NOT_REQUESTED,
        )


def test_pending_and_declined_cannot_record_executed_action() -> None:
    with pytest.raises(EducationContractError, match="PENDING disposition"):
        GuidedPracticeActionV1(
            schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
            recommended_action=_slow_down(),
            action_disposition=GuidedPracticeActionDisposition.PENDING,
            execution_status=GuidedPracticeExecutionStatus.NOT_REQUESTED,
            executed_action=_slow_down(),
        )
    with pytest.raises(EducationContractError, match="DECLINED disposition"):
        GuidedPracticeActionV1(
            schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
            recommended_action=_slow_down(),
            action_disposition=GuidedPracticeActionDisposition.DECLINED,
            execution_status=GuidedPracticeExecutionStatus.NOT_REQUESTED,
            executed_action=_slow_down(),
        )


def test_accepted_pending_and_failed_execution_shapes() -> None:
    pending = GuidedPracticeActionV1(
        schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
        recommended_action=_slow_down(),
        action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
        execution_status=GuidedPracticeExecutionStatus.PENDING,
    )
    failed = GuidedPracticeActionV1(
        schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
        recommended_action=_slow_down(),
        action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
        execution_status=GuidedPracticeExecutionStatus.FAILED,
    )
    assert pending.executed_action is None
    assert failed.executed_action is None
    with pytest.raises(EducationContractError, match="PENDING execution"):
        GuidedPracticeActionV1(
            schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
            recommended_action=_slow_down(),
            action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
            execution_status=GuidedPracticeExecutionStatus.PENDING,
            executed_action=_slow_down(),
        )
    with pytest.raises(EducationContractError, match="NOT_REQUESTED"):
        GuidedPracticeActionV1(
            schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
            recommended_action=_slow_down(),
            action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
            execution_status=GuidedPracticeExecutionStatus.NOT_REQUESTED,
            executed_action=_slow_down(),
        )


def test_attempt_properties_expose_the_action_triad() -> None:
    action = GuidedPracticeActionV1(
        schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
        recommended_action=_repeat(),
        action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
        execution_status=GuidedPracticeExecutionStatus.SUCCEEDED,
        executed_action=_repeat(),
    )
    attempt = _attempt(action=action)
    assert attempt.recommended_action is action.recommended_action
    assert attempt.action_disposition is GuidedPracticeActionDisposition.ACCEPTED
    assert attempt.execution_status is GuidedPracticeExecutionStatus.SUCCEEDED
    assert attempt.executed_action is action.executed_action


def test_duplicate_performance_session_ids_are_rejected() -> None:
    with pytest.raises(EducationContractError, match="performance_session_id"):
        _session(
            (
                _attempt(),
                _attempt(attempt_id=ATTEMPT_ID_1, attempt_index=1),
            )
        )


def test_current_attempt_index_must_be_the_latest() -> None:
    first = _attempt()
    second = _attempt(
        attempt_id=ATTEMPT_ID_1,
        attempt_index=1,
        performance_session_id=PERFORMANCE_1,
    )
    with pytest.raises(EducationContractError, match="current_attempt_index"):
        GuidedPracticeSessionV1(
            schema_version=SESSION_SCHEMA_VERSION,
            policy_version=SESSION_POLICY_VERSION,
            session_id=SESSION_ID,
            assignment_id=ASSIGNMENT_ID,
            content_id=CONTENT_ID,
            canonical_revision_id=REVISION_ID,
            status=GuidedPracticeSessionStatus.ACTIVE,
            attempts=(first, second),
            current_attempt_index=0,
            session_digest="sha256:" + ("0" * 64),
        )


def test_append_attempt_type_checks_and_preserves_status() -> None:
    session = _session((_attempt(),), status=GuidedPracticeSessionStatus.AWAITING_ACTION)
    with pytest.raises(EducationContractError, match="GuidedPracticeSessionV1"):
        append_attempt(_attempt(), _attempt(attempt_index=1))  # type: ignore[arg-type]
    with pytest.raises(EducationContractError, match="GuidedPracticeAttemptV1"):
        append_attempt(session, "attempt")  # type: ignore[arg-type]
    second = _attempt(
        attempt_id=ATTEMPT_ID_1,
        attempt_index=1,
        performance_session_id=PERFORMANCE_1,
    )
    extended = append_attempt(session, second)
    assert extended.status is GuidedPracticeSessionStatus.AWAITING_ACTION


def test_executed_action_must_be_a_next_action() -> None:
    with pytest.raises(EducationContractError, match="executed_action"):
        GuidedPracticeActionV1(
            schema_version=GuidedPracticeActionV1.SCHEMA_VERSION,
            recommended_action=_continue(),
            action_disposition=GuidedPracticeActionDisposition.ACCEPTED,
            execution_status=GuidedPracticeExecutionStatus.SUCCEEDED,
            executed_action="continue",  # type: ignore[arg-type]
        )


def test_terminal_statuses_are_representable() -> None:
    transitioned = _session((_attempt(),), status=GuidedPracticeSessionStatus.TRANSITIONED)
    aborted = _session(status=GuidedPracticeSessionStatus.ABORTED)
    assert transitioned.status is GuidedPracticeSessionStatus.TRANSITIONED
    assert aborted.status is GuidedPracticeSessionStatus.ABORTED


def test_session_rejects_malformed_attempts_and_context() -> None:
    with pytest.raises(EducationContractError, match="GuidedPracticeAttemptV1"):
        GuidedPracticeSessionV1(
            schema_version=SESSION_SCHEMA_VERSION,
            policy_version=SESSION_POLICY_VERSION,
            session_id=SESSION_ID,
            assignment_id=ASSIGNMENT_ID,
            content_id=CONTENT_ID,
            canonical_revision_id=REVISION_ID,
            status=GuidedPracticeSessionStatus.AWAITING_ATTEMPT,
            attempts=("nope",),  # type: ignore[arg-type]
            current_attempt_index=0,
            session_digest="sha256:" + ("0" * 64),
        )
    with pytest.raises(EducationContractError, match="practice_context"):
        GuidedPracticeAttemptV1(
            schema_version=SESSION_SCHEMA_VERSION,
            attempt_id=ATTEMPT_ID_0,
            attempt_index=0,
            assignment_id=ASSIGNMENT_ID,
            content_id=CONTENT_ID,
            canonical_revision_id=REVISION_ID,
            performance_session_id=PERFORMANCE_0,
            evaluation_digest=EVAL_DIGEST,
            guidance_digest=GUIDANCE_DIGEST,
            action=_pending_action(),
            practice_context="context",  # type: ignore[arg-type]
        )
