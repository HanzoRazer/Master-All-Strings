"""DO-015 Stage 3: deterministic guided-session fixtures, schema, drift, semantics."""

from __future__ import annotations

import copy
import functools
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator

from master_all_strings.education import (
    EducationContractError,
    GuidedPracticeExecutionStatus,
    GuidedPracticeSessionStatus,
    append_evaluated_attempt,
    compute_session_digest,
    record_action_execution,
    to_dict,
)

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "resources" / "education" / "examples" / "guided_sessions"
SCHEMA = REPO / "resources" / "education" / "schema" / "guided_practice_session_v1.schema.json"
GENERATOR = REPO / "scripts" / "build_guided_session_fixtures.py"

FIXTURE_STEMS = (
    "slow_down_accepted",
    "slow_down_declined",
    "isolate_passage_accepted",
    "repeat_accepted",
    "continue_accepted_closed",
    "continue_declined",
    "execution_failed",
    "view_one_string_unsupported",
    "lesson_transition",
    "three_attempt_progression",
)


@functools.lru_cache(maxsize=1)
def _generator():
    name = "build_guided_session_fixtures"
    spec = importlib.util.spec_from_file_location(name, GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _fixture(stem: str) -> dict:
    return json.loads((EXAMPLES / f"{stem}.json").read_text(encoding="utf-8"))


def _action(payload: dict) -> dict:
    return payload["attempts"][payload["current_attempt_index"]]["action"]


@pytest.mark.parametrize("stem", FIXTURE_STEMS)
def test_every_required_fixture_exists(stem: str) -> None:
    assert (EXAMPLES / f"{stem}.json").is_file()


@pytest.mark.parametrize("stem", FIXTURE_STEMS)
def test_fixture_validates_against_schema(stem: str) -> None:
    Draft202012Validator.check_schema(_schema())
    jsonschema.validate(_fixture(stem), _schema())


@pytest.mark.parametrize("stem", FIXTURE_STEMS)
def test_fixture_digest_matches_the_built_session(stem: str) -> None:
    session = _generator().build_sessions()[stem]
    payload = _fixture(stem)
    assert payload["session_digest"] == session.session_digest
    assert compute_session_digest(session) == session.session_digest


def test_fixtures_have_no_drift() -> None:
    assert _generator().check_fixtures() == 0
    assert _generator().main(["--check"]) == 0


def test_regeneration_is_byte_identical() -> None:
    first = _generator().render_fixtures()
    second = _generator().render_fixtures()
    assert first == second
    for stem, text in first.items():
        assert (EXAMPLES / f"{stem}.json").read_text(encoding="utf-8") == text


def test_generator_uses_the_public_lifecycle_and_is_deterministic() -> None:
    source = inspect.getsource(_generator())
    if source.startswith('"""'):
        source = source.split('"""', 2)[2]
    for token in (
        "create_from_first_evaluated_attempt",
        "append_evaluated_attempt",
        "record_action_disposition",
        "record_action_execution",
        "transition_session",
        "serialize_guided_practice_session",
    ):
        assert token in source
    for token in (
        "uuid4",
        "uuid.uuid4",
        "datetime.now",
        "time.time",
        "close_session",
        "begin_next_attempt",
    ):
        assert token not in source


def test_tampered_fixture_is_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = _generator()
    dest = tmp_path / "guided_sessions"
    dest.mkdir()
    for stem, text in generator.render_fixtures().items():
        (dest / f"{stem}.json").write_text(text, encoding="utf-8")
    monkeypatch.setattr(generator, "EXAMPLES", dest)
    assert generator.check_fixtures() == 0
    target = dest / "slow_down_accepted.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["status"] = "CLOSED"
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    assert generator.check_fixtures() == 1
    assert (EXAMPLES / "slow_down_accepted.json").read_text(encoding="utf-8") != target.read_text(
        encoding="utf-8"
    )


def test_slow_down_accepted_fixture() -> None:
    payload = _fixture("slow_down_accepted")
    action = _action(payload)
    assert action["recommended_action"]["action_type"] == "slow_down"
    assert action["recommended_action"]["target_rate"] == 0.75
    assert action["action_disposition"] == "ACCEPTED"
    assert action["execution_status"] == "SUCCEEDED"
    assert payload["status"] == "AWAITING_ATTEMPT"
    assert payload["attempts"][0]["practice_context"]["playback_rate"] is None


def test_slow_down_declined_fixture() -> None:
    payload = _fixture("slow_down_declined")
    action = _action(payload)
    assert action["recommended_action"]["action_type"] == "slow_down"
    assert action["action_disposition"] == "DECLINED"
    assert action["execution_status"] == "NOT_REQUESTED"
    assert action["executed_action"] is None
    assert payload["status"] == "AWAITING_ATTEMPT"


def test_isolate_passage_accepted_fixture() -> None:
    payload = _fixture("isolate_passage_accepted")
    action = _action(payload)
    recommended = action["recommended_action"]
    assert recommended["action_type"] == "isolate_passage"
    assert recommended["focus_start_tick"] == 960
    assert recommended["focus_end_tick"] == 1920
    assert action["action_disposition"] == "ACCEPTED"
    assert action["execution_status"] == "SUCCEEDED"
    assert payload["status"] == "AWAITING_ATTEMPT"
    assert payload["attempts"][0]["practice_context"]["loop_start_tick"] is None
    assert payload["attempts"][0]["practice_context"]["loop_end_tick"] is None


def test_repeat_accepted_fixture() -> None:
    payload = _fixture("repeat_accepted")
    action = _action(payload)
    assert action["recommended_action"]["action_type"] == "repeat"
    assert action["action_disposition"] == "ACCEPTED"
    assert action["execution_status"] == "SUCCEEDED"
    assert payload["status"] == "AWAITING_ATTEMPT"
    assert action["recommended_action"]["target_rate"] is None
    assert payload["attempts"][0]["practice_context"]["playback_rate"] is None


def test_continue_accepted_closes_and_is_not_mastery() -> None:
    payload = _fixture("continue_accepted_closed")
    action = _action(payload)
    assert action["recommended_action"]["action_type"] == "continue"
    assert action["action_disposition"] == "ACCEPTED"
    assert action["execution_status"] == "SUCCEEDED"
    assert payload["status"] == "CLOSED"
    blob = json.dumps(payload).lower()
    for token in ("mastered", "perfect", "complete", "passed curriculum"):
        assert token not in blob


def test_continue_declined_does_not_close() -> None:
    payload = _fixture("continue_declined")
    action = _action(payload)
    assert action["recommended_action"]["action_type"] == "continue"
    assert action["action_disposition"] == "DECLINED"
    assert action["execution_status"] == "NOT_REQUESTED"
    assert action["executed_action"] is None
    assert payload["status"] == "AWAITING_ATTEMPT"


def test_execution_failed_preserves_acceptance() -> None:
    payload = _fixture("execution_failed")
    action = _action(payload)
    assert action["recommended_action"]["action_type"] == "slow_down"
    assert action["action_disposition"] == "ACCEPTED"
    assert action["execution_status"] == "FAILED"
    assert payload["status"] == "AWAITING_ATTEMPT"


def test_view_one_string_unsupported_fixture() -> None:
    payload = _fixture("view_one_string_unsupported")
    action = _action(payload)
    assert action["recommended_action"]["action_type"] == "view_one_string"
    assert action["action_disposition"] == "ACCEPTED"
    assert action["execution_status"] == "UNSUPPORTED"
    assert action["executed_action"] is None
    assert payload["status"] == "AWAITING_ATTEMPT"
    assert action["recommended_action"]["teaching_aid"] == "one_string"


def test_lesson_transition_keeps_historical_lesson_ids() -> None:
    payload = _fixture("lesson_transition")
    assert payload["status"] == "TRANSITIONED"
    assert payload["assignment_id"] == "assignment-do015-001"
    assert payload["content_id"] == "content-do015-001"
    assert payload["canonical_revision_id"] == "revision-do015-001"
    assert len(payload["attempts"]) == 1
    provenance = payload["provenance"]
    assert provenance["transition_reason"] == "lesson_content_change"
    assert provenance["next_assignment_id"] == "assignment-do015-002"
    assert provenance["next_content_id"] == "content-do015-002"


def test_three_attempt_progression_fixture() -> None:
    payload = _fixture("three_attempt_progression")
    assert payload["status"] == "CLOSED"
    indexes = [attempt["attempt_index"] for attempt in payload["attempts"]]
    assert indexes == [0, 1, 2]
    types = [
        attempt["action"]["recommended_action"]["action_type"] for attempt in payload["attempts"]
    ]
    assert types == ["slow_down", "isolate_passage", "continue"]
    attempt_ids = [attempt["attempt_id"] for attempt in payload["attempts"]]
    performance_ids = [attempt["performance_session_id"] for attempt in payload["attempts"]]
    evaluation_digests = [attempt["evaluation_digest"] for attempt in payload["attempts"]]
    guidance_digests = [attempt["guidance_digest"] for attempt in payload["attempts"]]
    assert len(set(attempt_ids)) == 3
    assert len(set(performance_ids)) == 3
    assert len(set(evaluation_digests)) == 3
    assert len(set(guidance_digests)) == 3
    for attempt in payload["attempts"]:
        assert attempt["action"]["action_disposition"] == "ACCEPTED"
        assert attempt["action"]["execution_status"] == "SUCCEEDED"


def test_earlier_attempts_remain_immutable_after_appends() -> None:
    after_0, after_1, after_2 = _generator().build_three_attempt_steps()
    frozen_0 = copy.deepcopy(to_dict(after_0.attempts[0]))
    frozen_0_bytes = json.dumps(frozen_0, sort_keys=True, separators=(",", ":"))
    assert to_dict(after_1.attempts[0]) == frozen_0
    assert json.dumps(to_dict(after_1.attempts[0]), sort_keys=True, separators=(",", ":")) == (
        frozen_0_bytes
    )
    frozen_1 = copy.deepcopy(to_dict(after_1.attempts[1]))
    frozen_1_bytes = json.dumps(frozen_1, sort_keys=True, separators=(",", ":"))
    assert to_dict(after_2.attempts[0]) == frozen_0
    assert to_dict(after_2.attempts[1]) == frozen_1
    assert json.dumps(to_dict(after_2.attempts[0]), sort_keys=True, separators=(",", ":")) == (
        frozen_0_bytes
    )
    assert json.dumps(to_dict(after_2.attempts[1]), sort_keys=True, separators=(",", ":")) == (
        frozen_1_bytes
    )
    golden = _fixture("three_attempt_progression")
    assert to_dict(after_2) == golden


def test_failed_continue_does_not_close() -> None:
    session = _generator().build_continue_failed()
    assert session.status is GuidedPracticeSessionStatus.AWAITING_ATTEMPT
    assert session.attempts[0].recommended_action.action_type.value == "continue"
    assert session.attempts[0].action_disposition.value == "ACCEPTED"
    assert session.attempts[0].execution_status is GuidedPracticeExecutionStatus.FAILED


def test_unsupported_view_cannot_be_recorded_as_succeeded() -> None:
    generator = _generator()
    session = generator._accept(
        generator._create(generator._view_one_string(), stem="view_succeeded_reject")
    )
    with pytest.raises(EducationContractError, match="unsupported"):
        record_action_execution(session, GuidedPracticeExecutionStatus.SUCCEEDED)


def test_continue_cannot_be_unsupported() -> None:
    generator = _generator()
    session = generator._accept(
        generator._create(generator._continue(), stem="continue_unsupported")
    )
    with pytest.raises(EducationContractError, match="UNSUPPORTED"):
        record_action_execution(session, GuidedPracticeExecutionStatus.UNSUPPORTED)


def test_revision_mismatch_is_rejected_not_transitioned() -> None:
    generator = _generator()
    session = generator._declined_session(generator._slow_down(), stem="revision_mismatch")
    evaluation = generator._evaluation(
        generator._repeat(),
        performance_session_id=generator._performance_session_id("revision_mismatch", 1),
    )
    with pytest.raises(EducationContractError, match="canonical_revision_id"):
        append_evaluated_attempt(
            session,
            evaluation,
            generator._guidance(
                evaluation,
                canonical_revision_id=generator.OTHER_REVISION,
            ),
            attempt_id=generator._attempt_id("revision_mismatch", 1),
        )
    assert session.status is GuidedPracticeSessionStatus.AWAITING_ATTEMPT
    assert session.canonical_revision_id == generator.REVISION


def test_duplicate_attempt_and_performance_ids_are_rejected() -> None:
    generator = _generator()
    session = generator._declined_session(generator._slow_down(), stem="duplicate_identity")
    evaluation = generator._evaluation(
        generator._repeat(),
        performance_session_id=generator._performance_session_id("duplicate_identity", 1),
    )
    guidance = generator._guidance(evaluation)
    with pytest.raises(EducationContractError, match="duplicate attempt_id"):
        append_evaluated_attempt(
            session,
            evaluation,
            guidance,
            attempt_id=generator._attempt_id("duplicate_identity", 0),
        )
    colliding = generator._evaluation(
        generator._repeat(),
        performance_session_id=generator._performance_session_id("duplicate_identity", 0),
    )
    with pytest.raises(EducationContractError, match="performance_session_id"):
        append_evaluated_attempt(
            session,
            colliding,
            generator._guidance(colliding),
            attempt_id=generator._attempt_id("duplicate_identity", 1),
        )
