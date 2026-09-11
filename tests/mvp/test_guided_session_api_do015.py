"""DO-015 Stage 4: additive guided-session API over the Stage 2 service."""

from __future__ import annotations

import functools
import importlib.util
import inspect
import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import jsonschema
import pytest
from jsonschema import Draft202012Validator

from master_all_strings.education.serialization import to_dict
from master_all_strings.mvp import guided_session_api
from master_all_strings.mvp.guided_session_api import (
    GUIDED_SESSION_API_PREFIX,
    LocalGuidedPracticeSessionApi,
)
from master_all_strings.mvp.local_server import serve_mvp_directory

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "resources" / "education" / "schema" / "guided_practice_session_v1.schema.json"
GENERATOR = REPO / "scripts" / "build_guided_session_fixtures.py"
FIXTURE_CHECK = REPO / "scripts" / "build_guided_session_fixtures.py"


@functools.lru_cache(maxsize=1)
def _generator():
    name = "build_guided_session_fixtures_for_api"
    spec = importlib.util.spec_from_file_location(name, GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _validate(payload: dict) -> None:
    Draft202012Validator.check_schema(_schema())
    jsonschema.validate(payload, _schema())


def _create_body(stem: str, action: object | None = None) -> dict:
    gen = _generator()
    chosen = action or gen._slow_down()
    evaluation = gen._evaluation(
        chosen,
        performance_session_id=gen._performance_session_id(stem, 0),
    )
    return {
        "session_id": gen._session_id(stem),
        "attempt_id": gen._attempt_id(stem, 0),
        "evaluation": to_dict(evaluation),
        "guidance": to_dict(gen._guidance(evaluation)),
    }


def _append_body(stem: str, action: object, index: int) -> dict:
    gen = _generator()
    evaluation = gen._evaluation(
        action,
        performance_session_id=gen._performance_session_id(stem, index),
    )
    return {
        "attempt_id": gen._attempt_id(stem, index),
        "evaluation": to_dict(evaluation),
        "guidance": to_dict(gen._guidance(evaluation)),
    }


def _create(api: LocalGuidedPracticeSessionApi, stem: str, action: object | None = None) -> dict:
    status, payload = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, _create_body(stem, action))
    assert status == 201, payload
    _validate(payload)
    return payload


def test_create_returns_awaiting_action_and_preserves_ids() -> None:
    api = LocalGuidedPracticeSessionApi()
    payload = _create(api, "create-valid")
    assert payload["status"] == "AWAITING_ACTION"
    assert payload["session_id"] == "session-do015-create-valid"
    assert payload["attempts"][0]["attempt_id"] == "attempt-do015-create-valid-0"
    assert payload["attempts"][0]["attempt_index"] == 0
    assert payload["attempts"][0]["action"]["action_disposition"] == "PENDING"
    assert payload["attempts"][0]["action"]["execution_status"] == "NOT_REQUESTED"
    body = _create_body("create-pairs")
    body["evaluation"]["provenance"] = [
        ["assembler", "scripts.build_guided_session_fixtures"],
    ]
    status, payload = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, body)
    assert status == 201
    _validate(payload)
    assert payload["session_id"] == "session-do015-create-pairs"


def test_create_without_evidence_stores_nothing() -> None:
    api = LocalGuidedPracticeSessionApi()
    status, body = api.handle_http(
        "POST",
        GUIDED_SESSION_API_PREFIX,
        {"session_id": "session-do015-empty", "attempt_id": "attempt-do015-empty-0"},
    )
    assert status == 400
    assert api.store.get("session-do015-empty") is None
    assert "error" in body


def test_get_round_trips_the_stored_session() -> None:
    api = LocalGuidedPracticeSessionApi()
    created = _create(api, "get-round-trip")
    status, fetched = api.handle_http(
        "GET",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-get-round-trip",
    )
    assert status == 200
    assert fetched == created
    assert fetched == to_dict(api.store.get("session-do015-get-round-trip"))


def test_unknown_session_is_404() -> None:
    api = LocalGuidedPracticeSessionApi()
    status, body = api.handle_http("GET", f"{GUIDED_SESSION_API_PREFIX}/missing")
    assert status == 404
    assert "error" in body


def test_accept_does_not_claim_success() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "accept")
    status, payload = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-accept/disposition",
        {"disposition": "ACCEPTED"},
    )
    assert status == 200
    _validate(payload)
    action = payload["attempts"][0]["action"]
    assert action["action_disposition"] == "ACCEPTED"
    assert action["execution_status"] == "PENDING"
    assert action["executed_action"] is None
    assert payload["status"] == "AWAITING_ACTION"


def test_decline_awaits_next_attempt() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "decline")
    status, payload = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-decline/disposition",
        {"disposition": "DECLINED"},
    )
    assert status == 200
    action = payload["attempts"][0]["action"]
    assert action["action_disposition"] == "DECLINED"
    assert action["execution_status"] == "NOT_REQUESTED"
    assert action["executed_action"] is None
    assert payload["status"] == "AWAITING_ATTEMPT"


def test_double_disposition_is_409_and_does_not_mutate() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "double-disposition")
    api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-double-disposition/disposition",
        {"disposition": "ACCEPTED"},
    )
    before = to_dict(api.get("session-do015-double-disposition"))
    status, _ = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-double-disposition/disposition",
        {"disposition": "DECLINED"},
    )
    assert status == 409
    assert to_dict(api.get("session-do015-double-disposition")) == before


def test_execution_before_acceptance_is_409() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "exec-early")
    before = to_dict(api.get("session-do015-exec-early"))
    status, _ = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-exec-early/execution",
        {"execution_status": "SUCCEEDED"},
    )
    assert status == 409
    assert to_dict(api.get("session-do015-exec-early")) == before


def test_execution_after_decline_is_409() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "exec-declined")
    api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-exec-declined/disposition",
        {"disposition": "DECLINED"},
    )
    before = to_dict(api.get("session-do015-exec-declined"))
    status, _ = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-exec-declined/execution",
        {"execution_status": "SUCCEEDED"},
    )
    assert status == 409
    assert to_dict(api.get("session-do015-exec-declined")) == before


def _accept(api: LocalGuidedPracticeSessionApi, stem: str) -> None:
    session_id = _generator()._session_id(stem)
    status, _ = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/{session_id}/disposition",
        {"disposition": "ACCEPTED"},
    )
    assert status == 200


def test_supported_action_succeeds_without_transport() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "slow-success")
    _accept(api, "slow-success")
    status, payload = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-slow-success/execution",
        {"execution_status": "SUCCEEDED"},
    )
    assert status == 200
    _validate(payload)
    action = payload["attempts"][0]["action"]
    assert action["action_disposition"] == "ACCEPTED"
    assert action["execution_status"] == "SUCCEEDED"
    assert payload["status"] == "AWAITING_ATTEMPT"
    assert payload["attempts"][0]["practice_context"]["playback_rate"] is None


def test_execution_failed_preserves_acceptance() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "exec-fail")
    _accept(api, "exec-fail")
    status, payload = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-exec-fail/execution",
        {"execution_status": "FAILED"},
    )
    assert status == 200
    action = payload["attempts"][0]["action"]
    assert action["action_disposition"] == "ACCEPTED"
    assert action["execution_status"] == "FAILED"
    assert payload["status"] == "AWAITING_ATTEMPT"


def test_view_one_string_unsupported() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "view-unsupported", _generator()._view_one_string())
    _accept(api, "view-unsupported")
    status, payload = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-view-unsupported/execution",
        {"execution_status": "UNSUPPORTED"},
    )
    assert status == 200
    action = payload["attempts"][0]["action"]
    assert action["execution_status"] == "UNSUPPORTED"
    assert action["executed_action"] is None
    assert payload["status"] == "AWAITING_ATTEMPT"


@pytest.mark.parametrize(
    ("stem", "action_factory"),
    (
        ("continue-unsupported", "_continue"),
        ("slow-unsupported", "_slow_down"),
        ("isolate-unsupported", "_isolate"),
        ("repeat-unsupported", "_repeat"),
    ),
)
def test_invalid_unsupported_execution_is_409(stem: str, action_factory: str) -> None:
    api = LocalGuidedPracticeSessionApi()
    action = getattr(_generator(), action_factory)()
    _create(api, stem, action)
    _accept(api, stem)
    session_id = _generator()._session_id(stem)
    before = to_dict(api.get(session_id))
    status, _ = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/{session_id}/execution",
        {"execution_status": "UNSUPPORTED"},
    )
    assert status == 409
    assert to_dict(api.get(session_id)) == before


def test_successful_continue_closes_without_a_close_endpoint() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "continue-close", _generator()._continue())
    _accept(api, "continue-close")
    status, payload = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-continue-close/execution",
        {"execution_status": "SUCCEEDED"},
    )
    assert status == 200
    assert payload["status"] == "CLOSED"
    close_status, _ = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-continue-close/close",
        {},
    )
    assert close_status == 400


def test_failed_continue_stays_open() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "continue-fail", _generator()._continue())
    _accept(api, "continue-fail")
    status, payload = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-continue-fail/execution",
        {"execution_status": "FAILED"},
    )
    assert status == 200
    assert payload["status"] == "AWAITING_ATTEMPT"


def test_append_from_awaiting_attempt() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "append-ok")
    api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-append-ok/disposition",
        {"disposition": "DECLINED"},
    )
    status, payload = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-append-ok/attempts",
        _append_body("append-ok", _generator()._repeat(), 1),
    )
    assert status == 200
    _validate(payload)
    assert payload["status"] == "AWAITING_ACTION"
    assert payload["attempts"][1]["attempt_index"] == 1
    assert payload["attempts"][1]["attempt_id"] == "attempt-do015-append-ok-1"


def test_append_too_early_is_409() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "append-early")
    before = to_dict(api.get("session-do015-append-early"))
    status, _ = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-append-early/attempts",
        _append_body("append-early", _generator()._repeat(), 1),
    )
    assert status == 409
    assert to_dict(api.get("session-do015-append-early")) == before


def test_duplicate_attempt_and_performance_ids_are_409() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "dup-ids")
    api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-dup-ids/disposition",
        {"disposition": "DECLINED"},
    )
    before = to_dict(api.get("session-do015-dup-ids"))
    body = _append_body("dup-ids", _generator()._repeat(), 1)
    body["attempt_id"] = "attempt-do015-dup-ids-0"
    status, _ = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-dup-ids/attempts",
        body,
    )
    assert status == 409
    colliding = _append_body("dup-ids", _generator()._repeat(), 1)
    colliding["evaluation"]["performance_session_id"] = "performance-session-do015-dup-ids-0"
    colliding["evaluation"]["summary"]["performance_session_id"] = (
        "performance-session-do015-dup-ids-0"
    )
    colliding["guidance"]["performance_session_id"] = "performance-session-do015-dup-ids-0"
    status, _ = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-dup-ids/attempts",
        colliding,
    )
    assert status == 409
    assert to_dict(api.get("session-do015-dup-ids")) == before


def test_wrong_assignment_content_and_revision_are_409() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "pinning")
    api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-pinning/disposition",
        {"disposition": "DECLINED"},
    )
    before = to_dict(api.get("session-do015-pinning"))
    for field, value in (
        ("assignment_id", "assignment-do015-other"),
        ("content_id", "content-do015-other"),
    ):
        body = _append_body("pinning", _generator()._repeat(), 1)
        body["evaluation"][field] = value
        status, _ = api.handle_http(
            "POST",
            f"{GUIDED_SESSION_API_PREFIX}/session-do015-pinning/attempts",
            body,
        )
        assert status == 409
    body = _append_body("pinning", _generator()._repeat(), 1)
    body["guidance"]["canonical_revision_id"] = "revision-do015-other"
    status, _ = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-pinning/attempts",
        body,
    )
    assert status == 409
    assert to_dict(api.get("session-do015-pinning")) == before
    assert api.get("session-do015-pinning").status.value == "AWAITING_ATTEMPT"


def test_lesson_transition_does_not_create_the_next_session() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "transition")
    status, payload = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-transition/transition",
        {
            "next_assignment_id": "assignment-do015-002",
            "next_content_id": "content-do015-002",
        },
    )
    assert status == 200
    _validate(payload)
    assert payload["status"] == "TRANSITIONED"
    assert payload["assignment_id"] == "assignment-do015-001"
    assert payload["content_id"] == "content-do015-001"
    assert payload["canonical_revision_id"] == "revision-do015-001"
    assert len(payload["attempts"]) == 1
    assert len(api.store._sessions) == 1


@pytest.mark.parametrize("stem", ("terminal-closed", "terminal-transitioned"))
def test_terminal_sessions_reject_mutations(stem: str) -> None:
    api = LocalGuidedPracticeSessionApi()
    if stem == "terminal-closed":
        _create(api, stem, _generator()._continue())
        _accept(api, stem)
        api.handle_http(
            "POST",
            f"{GUIDED_SESSION_API_PREFIX}/session-do015-{stem}/execution",
            {"execution_status": "SUCCEEDED"},
        )
    else:
        _create(api, stem)
        api.handle_http(
            "POST",
            f"{GUIDED_SESSION_API_PREFIX}/session-do015-{stem}/transition",
            {
                "next_assignment_id": "assignment-do015-002",
                "next_content_id": "content-do015-002",
            },
        )
    before = to_dict(api.get(f"session-do015-{stem}"))
    for suffix, body in (
        ("disposition", {"disposition": "ACCEPTED"}),
        ("execution", {"execution_status": "FAILED"}),
        ("attempts", _append_body(stem, _generator()._repeat(), 1)),
    ):
        status, _ = api.handle_http(
            "POST",
            f"{GUIDED_SESSION_API_PREFIX}/session-do015-{stem}/{suffix}",
            body,
        )
        assert status == 409
    assert to_dict(api.get(f"session-do015-{stem}")) == before


def test_duplicate_create_is_409() -> None:
    api = LocalGuidedPracticeSessionApi()
    first = _create(api, "dup-create")
    status, _ = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, _create_body("dup-create"))
    assert status == 409
    assert to_dict(api.get("session-do015-dup-create")) == first


def test_close_and_begin_next_routes_do_not_exist() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "no-escape")
    for suffix in ("close", "begin-next", "close_session", "begin_next_attempt"):
        status, _ = api.handle_http(
            "POST",
            f"{GUIDED_SESSION_API_PREFIX}/session-do015-no-escape/{suffix}",
            {},
        )
        assert status == 400


def test_malformed_disposition_is_400() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "bad-disposition")
    before = to_dict(api.get("session-do015-bad-disposition"))
    status, _ = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-bad-disposition/disposition",
        {"disposition": "MAYBE"},
    )
    assert status == 400
    assert to_dict(api.get("session-do015-bad-disposition")) == before


def test_malformed_and_incomplete_requests_are_400() -> None:
    api = LocalGuidedPracticeSessionApi()
    _create(api, "bad-shape")
    before = to_dict(api.get("session-do015-bad-shape"))
    cases = (
        ("POST", GUIDED_SESSION_API_PREFIX, {"session_id": " ", "attempt_id": "attempt-1"}),
        (
            "POST",
            GUIDED_SESSION_API_PREFIX,
            {"session_id": "session-do015-bad-shape-2", "attempt_id": " "},
        ),
        (
            "POST",
            f"{GUIDED_SESSION_API_PREFIX}/session-do015-bad-shape/execution",
            {"execution_status": "MAYBE"},
        ),
        (
            "POST",
            f"{GUIDED_SESSION_API_PREFIX}/session-do015-bad-shape/transition",
            {"next_assignment_id": "assignment-do015-002"},
        ),
        ("GET", GUIDED_SESSION_API_PREFIX, None),
        ("POST", "/api/other/guided-sessions", {"session_id": "x", "attempt_id": "y"}),
        ("PUT", f"{GUIDED_SESSION_API_PREFIX}/session-do015-bad-shape", None),
    )
    for method, path, body in cases:
        status, payload = api.handle_http(method, path, body)
        assert status == 400, (method, path, payload)
        assert "error" in payload
    assert to_dict(api.get("session-do015-bad-shape")) == before
    body = _create_body("bad-eval")
    body["evaluation"]["evaluation_digest"] = "not-a-digest"
    status, _ = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, body)
    assert status == 400
    assert api.store.get("session-do015-bad-eval") is None
    body = _create_body("bad-guidance")
    del body["guidance"]["next_action"]
    status, _ = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, body)
    assert status == 400
    assert api.store.get("session-do015-bad-guidance") is None
    body = _create_body("bad-pairs")
    body["evaluation"]["provenance"] = "not-pairs"
    status, _ = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, body)
    assert status == 400
    body = _create_body("bad-pair-item")
    body["evaluation"]["provenance"] = [["only-one"]]
    status, _ = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, body)
    assert status == 400
    body = _create_body("bad-action-shape")
    body["evaluation"]["primary_next_action"]["target_rate"] = True
    body["evaluation"]["summary"]["primary_action"]["target_rate"] = True
    status, _ = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, body)
    assert status == 400
    body = _create_body("bad-focus")
    body["evaluation"]["primary_next_action"]["focus_start_tick"] = "late"
    body["evaluation"]["summary"]["primary_action"]["focus_start_tick"] = "late"
    status, _ = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, body)
    assert status == 400
    body = _create_body("bad-reasons")
    body["evaluation"]["primary_next_action"]["reason_finding_ids"] = "finding-1"
    body["evaluation"]["summary"]["primary_action"]["reason_finding_ids"] = "finding-1"
    status, _ = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, body)
    assert status == 400
    body = _create_body("none-reasons")
    body["evaluation"]["primary_next_action"]["reason_finding_ids"] = None
    body["evaluation"]["summary"]["primary_action"]["reason_finding_ids"] = None
    body["guidance"]["next_action"]["reason_finding_ids"] = None
    status, payload = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, body)
    assert status == 201, payload
    body = _create_body("missing-action-type")
    del body["evaluation"]["primary_next_action"]["action_type"]
    status, _ = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, body)
    assert status == 400
    body = _create_body("missing-assignment")
    del body["evaluation"]["assignment_id"]
    status, _ = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, body)
    assert status == 400
    body = _create_body("bad-guidance-digest")
    body["guidance"]["guidance_digest"] = "not-a-digest"
    status, _ = api.handle_http("POST", GUIDED_SESSION_API_PREFIX, body)
    assert status == 400


def test_execution_may_echo_executed_action_and_transition_may_carry_reason() -> None:
    api = LocalGuidedPracticeSessionApi()
    created = _create(api, "echo-action")
    recommended = created["attempts"][0]["action"]["recommended_action"]
    _accept(api, "echo-action")
    status, payload = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-echo-action/execution",
        {"execution_status": "SUCCEEDED", "executed_action": recommended},
    )
    assert status == 200
    _validate(payload)
    assert payload["attempts"][0]["action"]["executed_action"]["action_type"] == "slow_down"
    status, payload = api.handle_http(
        "POST",
        f"{GUIDED_SESSION_API_PREFIX}/session-do015-echo-action/transition",
        {
            "next_assignment_id": "assignment-do015-002",
            "next_content_id": "content-do015-002",
            "reason": "manual_lesson_change",
        },
    )
    assert status == 200
    assert payload["status"] == "TRANSITIONED"
    assert payload["provenance"]["transition_reason"] == "manual_lesson_change"


def test_api_does_not_own_lifecycle_or_external_authorities() -> None:
    source = inspect.getsource(guided_session_api)
    if source.startswith('"""'):
        source = source.split('"""', 2)[2]
    for token in (
        "create_from_first_evaluated_attempt",
        "append_evaluated_attempt",
        "record_action_disposition",
        "record_action_execution",
        "transition_session",
    ):
        assert token in source
    for token in (
        "uuid4",
        "datetime.now",
        "time.time",
        "PracticeEvaluator",
        "choose_primary_next_action",
        "master_all_strings.performance",
        "web.mvp1",
        "playback_rate =",
        "loop_start",
        "def close_session",
        "def begin_next_attempt",
        "close_session(",
        "begin_next_attempt(",
    ):
        assert token not in source
    assert "session.status =" not in source


def test_stage3_fixtures_have_not_drifted() -> None:
    spec = importlib.util.spec_from_file_location("guided_session_fixture_check", FIXTURE_CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.check_fixtures() == 0


def test_http_server_create_get_and_unknown() -> None:
    api = LocalGuidedPracticeSessionApi()
    server, thread, url = serve_mvp_directory(
        REPO / "web" / "mvp1",
        open_browser=False,
        port=0,
        guided_session_api=api,
    )
    try:
        base = url.rsplit("/", 1)[0]
        body = json.dumps(_create_body("http-create")).encode()
        request = Request(
            f"{base}{GUIDED_SESSION_API_PREFIX}",
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            assert response.status == 201
            created = json.loads(response.read().decode("utf-8"))
        _validate(created)
        with urlopen(f"{base}{GUIDED_SESSION_API_PREFIX}/session-do015-http-create") as response:
            assert response.status == 200
            fetched = json.loads(response.read().decode("utf-8"))
        assert fetched == created
        with pytest.raises(HTTPError) as error:
            urlopen(f"{base}{GUIDED_SESSION_API_PREFIX}/missing-http")
        assert error.value.code == 404
        accept = Request(
            f"{base}{GUIDED_SESSION_API_PREFIX}/session-do015-http-create/disposition",
            data=json.dumps({"disposition": "MAYBE"}).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(accept)
        assert error.value.code == 400
        with urlopen(f"{base}{GUIDED_SESSION_API_PREFIX}/session-do015-http-create") as response:
            after_failed = json.loads(response.read().decode("utf-8"))
        assert after_failed == created
        for data, expected in ((b"{", 400), (b"[]", 400)):
            request = Request(
                f"{base}{GUIDED_SESSION_API_PREFIX}",
                data=data,
                headers={"content-type": "application/json"},
                method="POST",
            )
            with pytest.raises(HTTPError) as error:
                urlopen(request)
            assert error.value.code == expected
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_http_without_guided_session_api_is_404() -> None:
    server, thread, url = serve_mvp_directory(
        REPO / "web" / "mvp1",
        open_browser=False,
        port=0,
    )
    try:
        base = url.rsplit("/", 1)[0]
        with pytest.raises(HTTPError) as error:
            urlopen(f"{base}{GUIDED_SESSION_API_PREFIX}/missing")
        assert error.value.code == 404
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_existing_education_evaluate_route_is_unchanged() -> None:
    from master_all_strings.mvp.education_api import LocalPracticeEvaluationApi

    education = LocalPracticeEvaluationApi()
    server, thread, url = serve_mvp_directory(
        REPO / "web" / "mvp1",
        open_browser=False,
        port=0,
        education_api=education,
        guided_session_api=LocalGuidedPracticeSessionApi(),
    )
    try:
        base = url.rsplit("/", 1)[0]
        payload = {
            "assignment_id": "a1",
            "content_id": "c1",
            "performance_session_id": "p-non-interfere",
            "aligned_events": [
                {
                    "status": "matched_exact_pitch",
                    "expected_event_id": "ev-1",
                    "observed_event_id": "obs-1",
                    "repetition_index": 0,
                    "timing_delta_ms": 0,
                    "pitch_delta_semitones": 0,
                    "expected_start_tick": 0,
                }
            ],
        }
        request = Request(
            f"{base}/api/education/evaluate",
            data=json.dumps(payload).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            assert response.status == 200
            result = json.loads(response.read().decode("utf-8"))
        assert "evaluation" in result
        assert result["evaluation"]["primary_next_action"]["action_type"] == "continue"
    finally:
        server.shutdown()
        thread.join(timeout=2)
