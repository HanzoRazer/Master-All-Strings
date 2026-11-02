"""The begin-recovery verifier reads recorded bytes and the relationships between them.

Every mutation below rewrites bytes the way a careful forger would: new bytes,
a recomputed sha256, and a parsed copy that matches. The hashes stay valid, so
only the broken relationship can fail the packet.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER = REPO_ROOT / "scripts" / "verify_do016_begin_recovery_evidence.py"
RETAINED = REPO_ROOT / "docs/mvp2/do016_begin_recovery_artifacts/evidence.json"
ARTIFACT = "sha256:" + "aa" * 32
BEHAVIOR = "sha256:" + "bb" * 32


@pytest.fixture(scope="module")
def verifier() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_do016_begin_recovery_evidence", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _key(index: int) -> str:
    return f"{index:08x}-0000-4000-8000-00000000abcd"


def _begin_request(index: int, capture: int = 1_000) -> dict[str, Any]:
    return {
        "begin_request_id": _key(index),
        "begin": {
            "delivery_id": "delivery-stage9",
            "expected_assignment_artifact_digest": ARTIFACT,
            "expected_assignment_behavior_digest": BEHAVIOR,
            "device_id": "Injected Begin Recovery",
            "capture_time_ns": capture,
        },
    }


def _attempt(index: int, phase: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "attempt_id": f"attempt-{index}",
        "capture_id": f"capture-{index}",
        "performance_session_id": f"session-{index}",
        "delivery_id": "delivery-stage9",
        "assignment_artifact_digest": ARTIFACT,
        "assignment_behavior_digest": BEHAVIOR,
        "attempt_status": phase,
    }
    if phase == "INTERRUPTED":
        body["raw_capture"] = {"events": []}
        body["observed_events"] = []
    return body


def _wrapper(index: int, status: str, attempt: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "schema_id": "master_all_strings.received_lesson_begin_request",
        "schema_version": "1.0.0",
        "begin_request_id": _key(index),
        "status": status,
        "attempt": attempt,
    }


def _encode(exchange: dict[str, Any], side: str, body: dict[str, Any] | None) -> None:
    """Write bytes, hash, and parsed copy together, as a forger would."""

    if body is None:
        exchange[f"{side}_base64"] = None
        exchange[f"{side}_sha256"] = None
        exchange[side] = None
        return
    raw = json.dumps(body).encode()
    exchange[f"{side}_base64"] = base64.b64encode(raw).decode()
    exchange[f"{side}_sha256"] = hashlib.sha256(raw).hexdigest()
    exchange[side] = json.loads(raw)


def _exchange(
    scenario: str,
    shape: tuple[str, str, str, str, str, int | None],
    request: dict[str, Any],
    response: dict[str, Any] | None,
) -> dict[str, Any]:
    source, route, sender, outcome, epoch, status = shape
    item: dict[str, Any] = {
        "seq": 0,
        "scenario": scenario,
        "source": source,
        "route": route,
        "sender": sender,
        "page_outcome": outcome,
        "epoch": epoch,
        "status": status,
    }
    _encode(item, "request", request)
    _encode(item, "response", response)
    return item


def _packet() -> dict[str, Any]:
    started_1 = _attempt(1, "CAPTURING")
    stopped_1 = _attempt(1, "INTERRUPTED")
    stopped_3 = _attempt(3, "INTERRUPTED")
    started_4 = _attempt(4, "CAPTURING")
    stopped_4 = _attempt(4, "INTERRUPTED")
    closed = {"error": "begin_request_closed"}
    harness = ("harness", "not_sent_by_page")
    exchanges = [
        _exchange("W1", ("forwarded_server", "begin", "harness", "network_failure", "A", 201),
            _begin_request(1), _wrapper(1, "STARTED", started_1)),
        _exchange("W1", ("browser", "recovery", "browser", "response", "A", 200),
            _begin_request(1), _wrapper(1, "INTERRUPTED", stopped_1)),
        _exchange("W2", ("recovery_before_begin", "recovery", *harness, "A", 200),
            _begin_request(2), _wrapper(2, "NO_ATTEMPT", None)),
        _exchange("W2", ("browser", "begin", "browser", "response", "A", 409),
            _begin_request(2), closed),
        _exchange("W2", ("browser", "recovery", "browser", "response", "A", 200),
            _begin_request(2), _wrapper(2, "NO_ATTEMPT", None)),
        _exchange("W3", ("recovery_during_prepare", "recovery", *harness, "A", 202),
            _begin_request(3), _wrapper(3, "PENDING", None)),
        _exchange("W3", ("browser", "begin", "browser", "response", "A", 200),
            _begin_request(3), _wrapper(3, "INTERRUPTED", stopped_3)),
        _exchange("W4", ("forwarded_begin", "begin", "harness", "network_failure", "A", 201),
            _begin_request(4), _wrapper(4, "STARTED", started_4)),
        _exchange("W4", ("forwarded_recovery", "recovery", "harness", "network_failure", "A",
            200), _begin_request(4), _wrapper(4, "INTERRUPTED", stopped_4)),
        _exchange("W4", ("browser", "recovery", "browser", "response", "A", 200),
            _begin_request(4), _wrapper(4, "INTERRUPTED", stopped_4)),
        _exchange("W5", ("aborted_begin", "begin", "none", "network_failure", "A", None),
            _begin_request(5), None),
        _exchange("W5", ("browser", "recovery", "browser", "response", "B", 200),
            _begin_request(5), _wrapper(5, "NO_ATTEMPT", None)),
        _exchange("W5", ("replayed_begin", "begin", *harness, "B", 409),
            _begin_request(5), closed),
    ]
    restart_seq = 12
    numbers = [n for n in range(1, len(exchanges) + 2) if n != restart_seq]
    for item, number in zip(exchanges, numbers, strict=True):
        item["seq"] = number
    feedback = "Attempt interruptedAttempt: {}No evaluation was produced."
    return {
        "schema": "master_all_strings.do016_begin_recovery_evidence",
        "schema_version": "2",
        "complete": True,
        "failures": 0,
        "tested_sha": "a" * 40,
        "tested_tree": "b" * 40,
        "dirty": "",
        "python": "3.11.9",
        "node": "v24.11.0",
        "chrome": "Chrome/156.0.8078.74",
        "os": "Windows-10-10.0.26100-SP0",
        "transport": {"server_responses": "live"},
        "scenarios": {
            "W1": {"feedback_visible": True, "feedback_text": feedback.format("attempt-1")},
            "W2": {},
            "W3": {"feedback_visible": True, "feedback_text": feedback.format("attempt-3")},
            "W4": {"feedback_visible": True, "feedback_text": feedback.format("attempt-4")},
            "W5": {},
        },
        "exchanges": exchanges,
        "epochs": [
            {"name": "A", "pid": 101},
            {"name": "B", "pid": 202, "previous_pid": 101, "restart_seq": restart_seq},
        ],
    }


def _find(packet: dict[str, Any], scenario: str, source: str, route: str = "") -> dict[str, Any]:
    found = [
        item for item in packet["exchanges"]
        if item["scenario"] == scenario and item["source"] == source
        and (not route or item["route"] == route)
    ]
    assert len(found) == 1
    return found[0]


def _edit(item: dict[str, Any], side: str, change: Callable[[dict[str, Any]], object]) -> None:
    body = copy.deepcopy(item[side])
    change(body)
    _encode(item, side, body)


def test_a_consistent_packet_passes(verifier: ModuleType) -> None:
    assert verifier.verify_evidence(_packet()) == []


def test_the_retained_packet_passes(verifier: ModuleType) -> None:
    packet = json.loads(RETAINED.read_text(encoding="utf-8"))
    assert verifier.verify_evidence(packet) == []


def test_a_parsed_copy_that_disagrees_with_its_bytes_fails(verifier: ModuleType) -> None:
    packet = _packet()
    item = _find(packet, "W1", "browser")
    item["response"]["status"] = "NO_ATTEMPT"
    problems = verifier.verify_evidence(packet)
    assert any("parsed response is not its bytes" in problem for problem in problems)


def test_unrehashed_bytes_fail(verifier: ModuleType) -> None:
    packet = _packet()
    item = _find(packet, "W2", "browser", "begin")
    item["response_base64"] = base64.b64encode(b'{"error":"begin_request_conflict"}').decode()
    problems = verifier.verify_evidence(packet)
    assert any("sha256 does not match" in problem for problem in problems)


Mutation = Callable[[dict[str, Any]], None]


def _wrapper_key(packet: dict[str, Any]) -> None:
    _edit(_find(packet, "W1", "browser"), "response",
        lambda body: body.update(begin_request_id=_key(9)))


def _request_and_wrapper_key(packet: dict[str, Any]) -> None:
    item = _find(packet, "W1", "browser")
    _edit(item, "request", lambda body: body.update(begin_request_id=_key(9)))
    _edit(item, "response", lambda body: body.update(begin_request_id=_key(9)))


def _reused_key(packet: dict[str, Any]) -> None:
    for item in packet["exchanges"]:
        if item["scenario"] == "W2":
            _edit(item, "request", lambda body: body.update(begin_request_id=_key(1)))
            if "begin_request_id" in item["response"]:
                _edit(item, "response", lambda body: body.update(begin_request_id=_key(1)))


def _payload(packet: dict[str, Any]) -> None:
    _edit(_find(packet, "W2", "browser", "begin"), "request",
        lambda body: body["begin"].update(capture_time_ns=2_000))


def _http_status(packet: dict[str, Any]) -> None:
    _find(packet, "W2", "recovery_before_begin")["status"] = 201


def _wrapper_status(packet: dict[str, Any]) -> None:
    def started(body: dict[str, Any]) -> None:
        body["status"] = "STARTED"
        body["attempt"]["attempt_status"] = "CAPTURING"

    _edit(_find(packet, "W3", "browser"), "response", started)


def _attempt_identity(packet: dict[str, Any]) -> None:
    _edit(_find(packet, "W4", "browser"), "response",
        lambda body: body["attempt"].update(attempt_id="attempt-9"))


def _capture_identity(packet: dict[str, Any]) -> None:
    _edit(_find(packet, "W1", "browser"), "response",
        lambda body: body["attempt"].update(capture_id="capture-9"))


def _attempt_pin(packet: dict[str, Any]) -> None:
    _edit(_find(packet, "W1", "forwarded_server"), "response",
        lambda body: body["attempt"].update(delivery_id="delivery-other"))


def _captured_notes(packet: dict[str, Any]) -> None:
    def noted(body: dict[str, Any]) -> None:
        body["attempt"]["observed_events"] = [{"midi_note": 60}]

    _edit(_find(packet, "W4", "forwarded_recovery"), "response", noted)
    _edit(_find(packet, "W4", "browser"), "response", noted)


def _swapped_order(packet: dict[str, Any]) -> None:
    first = _find(packet, "W2", "recovery_before_begin")
    second = _find(packet, "W2", "browser", "begin")
    first["seq"], second["seq"] = second["seq"], first["seq"]
    packet["exchanges"].sort(key=lambda item: item["seq"])


def _epoch_after_restart(packet: dict[str, Any]) -> None:
    _find(packet, "W5", "browser")["epoch"] = "A"


def _replayed_bytes(packet: dict[str, Any]) -> None:
    item = _find(packet, "W5", "replayed_begin")
    raw = json.dumps(item["request"], indent=1).encode()
    item["request_base64"] = base64.b64encode(raw).decode()
    item["request_sha256"] = hashlib.sha256(raw).hexdigest()


def _previous_pid(packet: dict[str, Any]) -> None:
    packet["epochs"][1]["previous_pid"] = 999


def _hidden_feedback(packet: dict[str, Any]) -> None:
    packet["scenarios"]["W3"]["feedback_visible"] = False


def _feedback_for_another_attempt(packet: dict[str, Any]) -> None:
    packet["scenarios"]["W1"]["feedback_text"] = (
        "Attempt interruptedAttempt: attempt-4No evaluation was produced."
    )


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    [
        (_wrapper_key, "W1 #2: wrapper key is not the request's key"),
        (_request_and_wrapper_key, "W1: expected one begin request key"),
        (_reused_key, "W2: reuses W1's begin request key"),
        (_payload, "the key was reused with another payload"),
        (_http_status, "HTTP 201 cannot carry NO_ATTEMPT"),
        (_wrapper_status, "W3: recorded exchanges are not the witnessed sequence"),
        (_attempt_identity, "W4 #10: attempt_id is not the key's attempt"),
        (_capture_identity, "W1 #2: capture_id is not the key's attempt"),
        (_attempt_pin, "attempt delivery_id is not the request's"),
        (_captured_notes, "a recovered interruption captured notes"),
        (_swapped_order, "W2: recorded exchanges are not the witnessed sequence"),
        (_epoch_after_restart, "epoch A answered after the restart"),
        (_replayed_bytes, "W5: the replayed begin is not the page's aborted bytes"),
        (_previous_pid, "the restart did not replace epoch A's process"),
        (_hidden_feedback, "W3: recovered interruption feedback was not visible"),
        (_feedback_for_another_attempt, "W1: feedback does not show the recovered attempt"),
    ],
)
def test_a_rehashed_packet_that_breaks_a_relationship_fails(
    verifier: ModuleType, mutation: Mutation, diagnostic: str
) -> None:
    packet = _packet()
    mutation(packet)
    problems = verifier.verify_evidence(packet)
    assert any(diagnostic in problem for problem in problems), problems


def test_the_version_one_packet_format_is_refused(verifier: ModuleType) -> None:
    packet = _packet()
    packet["schema_version"] = "1"
    problems = verifier.verify_evidence(packet)
    assert "evidence: schema or version is not the begin recovery packet" in problems


@pytest.mark.parametrize("loose_zero", [False, 0.0, "0", None])
def test_only_integer_zero_failures_pass(verifier: ModuleType, loose_zero: object) -> None:
    packet = _packet()
    packet["failures"] = loose_zero
    assert verifier.verify_evidence(packet) == ["evidence: the run is incomplete"]


def test_a_dirty_tree_fails(verifier: ModuleType) -> None:
    packet = _packet()
    packet["dirty"] = " M scripts/smoke_do016_begin_recovery.py"
    assert verifier.verify_evidence(packet) == ["evidence: the tested tree was dirty"]
