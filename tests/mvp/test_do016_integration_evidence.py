"""The integration evidence verifier rejects a packet that only claims success.

A consistent packet passes. Swapped pins, broken acknowledgements, a fabricated
restart, a changed retry result, a missing scenario, and edited frozen bytes
each fail on that boundary.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER = REPO_ROOT / "scripts" / "verify_do016_integration_evidence.py"
DRIVER = REPO_ROOT / "scripts" / "smoke_do016_integration.py"
ARTIFACT = "aa" * 32
BEHAVIOR = "bb" * 32
REVISION = "rev-stage9"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def verifier() -> ModuleType:
    return _load(VERIFIER, "verify_do016_integration_evidence")


@pytest.fixture(scope="module")
def driver() -> ModuleType:
    return _load(DRIVER, "smoke_do016_integration")


def _exchange(
    scenario: str,
    operation: str,
    status: int,
    request: dict[str, Any],
    response: dict[str, Any],
    *,
    source: str = "browser",
    fabricated: bool = False,
) -> dict[str, Any]:
    request_raw = json.dumps(request).encode()
    response_raw = json.dumps(response).encode()
    return {
        "id": f"{scenario}-{operation}-{status}-{request.get('sequence_number', operation)}",
        "scenario": scenario,
        "operation": operation,
        "source": source,
        "fabricated": fabricated,
        "status": status,
        "request_base64": base64.b64encode(request_raw).decode(),
        "request_sha256": hashlib.sha256(request_raw).hexdigest(),
        "response_base64": base64.b64encode(response_raw).decode(),
        "response_sha256": hashlib.sha256(response_raw).hexdigest(),
    }


def _pins(attempt: str, capture: str, session: str) -> dict[str, str]:
    return {
        "delivery_id": "delivery-stage9",
        "assignment_id": "assignment-stage9",
        "content_id": "content-stage9",
        "assignment_artifact_digest": f"sha256:{ARTIFACT}",
        "assignment_behavior_digest": f"sha256:{BEHAVIOR}",
        "attempt_id": attempt,
        "capture_id": capture,
        "performance_session_id": session,
    }


def _begin(attempt: str, capture: str, session: str) -> dict[str, Any]:
    body = _pins(attempt, capture, session)
    body.update(
        {
            "attempt_status": "CAPTURING",
            "preparation": {"score": {"canonical_revision": {"revision_id": REVISION}}},
        }
    )
    return body


def _evaluation(session: str) -> dict[str, Any]:
    """An evaluation body whose digest is computed the way the engine does."""

    action = {"action_type": "repeat", "reason_finding_ids": ["missing-0001"]}
    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "assignment_id": "assignment-stage9",
        "content_id": "content-stage9",
        "performance_session_id": session,
        "evaluation_policy_id": "policy-stage9",
        "evaluation_policy_version": "1.0.0",
        "findings": [{"finding_id": "missing-0001"}],
        "summary": {
            "performance_session_id": session,
            "matched_count": 1,
            "missing_count": 1,
            "extra_count": 0,
            "primary_action": action,
            "secondary_actions": [],
        },
        "primary_next_action": action,
        "secondary_actions": [],
        "provenance": {"alignment_session": session, "producer": "PracticeEvaluator/v1"},
    }
    payload = {key: value for key, value in body.items() if key != "schema_version"}
    payload["summary"] = {
        key: value
        for key, value in body["summary"].items()
        if key not in ("primary_action", "secondary_actions")
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True)
    body["evaluation_digest"] = "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()
    return body


def _evaluated(attempt: str, capture: str, session: str) -> dict[str, Any]:
    body = _pins(attempt, capture, session)
    evaluation = _evaluation(session)
    digest = evaluation["evaluation_digest"]
    body.update(
        {
            "attempt_status": "EVALUATED",
            "evaluation": evaluation,
            "guidance": {"evaluation_digest": digest, "canonical_revision_id": REVISION},
            "hardware_status": {
                "midi_input": "UNVERIFIED_PHYSICAL_MIDI_INPUT",
                "audio_output": "UNVERIFIED_AUDIO_OUTPUT",
            },
        }
    )
    return body


def _message(attempt: str, sequence: int) -> tuple[dict[str, Any], dict[str, Any]]:
    request = {"attempt_id": attempt, "sequence_number": sequence}
    response = {"attempt_id": attempt, "attempt_status": "CAPTURING",
        "accepted_event_count": sequence + 1}
    return request, response


def _chain(scenario: str, attempt: str, capture: str, session: str,
    messages: int) -> list[dict[str, Any]]:
    delivery = {
        key: value
        for key, value in _pins(attempt, capture, session).items()
        if key not in ("attempt_id", "capture_id", "performance_session_id")
    }
    items = [
        _exchange(scenario, "preview", 200, {}, {"preview_status": "READY", **delivery}),
        _exchange(scenario, "choice", 201, {"delivery_id": "delivery-stage9"},
            {"choice_status": "CHOSEN_FOR_PRACTICE", **delivery}),
        _exchange(scenario, "prepare", 200, {"delivery_id": "delivery-stage9"},
            {"preparation_status": "READY", **delivery,
                "score": {"canonical_revision": {"revision_id": REVISION}}}),
        _exchange(scenario, "begin", 201, {"delivery_id": "delivery-stage9"}, _begin(attempt,
            capture, session)),
    ]
    for sequence in range(messages):
        request, response = _message(attempt, sequence)
        items.append(_exchange(scenario, "message", 200, request, response))
    items.append(
        _exchange(
            scenario,
            "finish",
            200,
            {"attempt_id": attempt},
            _evaluated(attempt, capture, session),
        )
    )
    return items


def _terminal(
    scenario: str,
    operation: str,
    attempt: str,
    capture: str,
    session: str,
) -> list[dict[str, Any]]:
    request, response = _message(attempt, 0)
    return [
        _exchange(scenario, "begin", 201, {"delivery_id": "delivery-stage9"}, _begin(attempt,
            capture, session)),
        _exchange(scenario, "message", 200, request, response),
        _exchange(
            scenario,
            operation,
            404,
            {"attempt_id": attempt},
            {"error": "unknown_attempt"},
        ),
    ]


def _counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "begin": sum(item["operation"] == "begin" for item in items),
        "message": sum(item["operation"] == "message" for item in items),
        "finish": sum(item["operation"] == "finish" for item in items),
        "cancel": sum(item["operation"] == "cancel" for item in items),
        "guided": 0,
        "performance": 0,
    }


def _packet(frozen_dir: Path) -> dict[str, Any]:
    frozen_dir.mkdir(parents=True, exist_ok=True)
    frozen_file = frozen_dir / "browser_smoke_summary.json"
    payload = b'{"status":"frozen"}\n'
    frozen_file.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    t1 = _chain("T1", "attempt-t1", "capture-t1", "session-t1", 2)
    t6 = _chain("T6", "attempt-t6", "capture-t6", "session-t6", 2)
    t4 = _terminal("T4", "finish", "attempt-t4", "capture-t4", "session-t4")
    t5 = _terminal("T5", "cancel", "attempt-t5", "capture-t5", "session-t5")
    t3_request, t3_response = _message("attempt-t3", 0)
    t3 = [
        _exchange("T3", "begin", 201, {}, _begin("attempt-t3", "capture-t3", "session-t3")),
        _exchange("T3", "message", 200, t3_request, t3_response),
        _exchange(
            "T3",
            "cancel",
            200,
            {"attempt_id": "attempt-t3"},
            {"attempt_id": "attempt-t3", "attempt_status": "INTERRUPTED"},
        ),
    ]
    t7_request, t7_response = _message("attempt-t7", 0)
    stored = _evaluated("attempt-t7", "capture-t7", "session-t7")
    t7 = [
        _exchange("T7", "begin", 201, {}, _begin("attempt-t7", "capture-t7", "session-t7")),
        _exchange("T7", "message", 200, t7_request, t7_response),
        _exchange("T7", "finish", 200, {"attempt_id": "attempt-t7"}, stored,
            source="forwarded_server"),
        _exchange("T7", "finish", 200, {"attempt_id": "attempt-t7"}, stored),
    ]
    feedback = (
        "Attempt: {attempt} Matched: 1 Missing: 1 Extra: 0 "
        "UNVERIFIED_PHYSICAL_MIDI_INPUT UNVERIFIED_AUDIO_OUTPUT"
    )
    return {
        "schema": "master_all_strings.do016_integration_evidence",
        "schema_version": "1",
        "complete": True,
        "failures": 0,
        "run_id": "run-1",
        "tested_sha": "a" * 40,
        "tested_tree": "b" * 40,
        "dirty": "",
        "node": "v22.23.4",
        "python": "3.12.3",
        "browser": "Chrome/148.0.0.0",
        "chrome": "Google Chrome 148.0.0.0",
        "physical_midi": "UNVERIFIED_PHYSICAL_MIDI_INPUT",
        "physical_audio": "UNVERIFIED_AUDIO_OUTPUT",
        "injected_midi": True,
        "scenarios": {
            "T1": {
                "identities": {
                    **_pins("attempt-t1", "capture-t1", "session-t1"),
                    "revision_id": REVISION,
                    "evaluation_digest": _evaluation("session-t1")["evaluation_digest"],
                },
                "requests": _counts(t1),
                "feedback_text": feedback.format(attempt="attempt-t1"),
            },
            "T2": {
                "non_normal_rate_before": True,
                "loop_toggled_before": True,
                "normal_rate_during": True,
                "loop_off_during": True,
                "controls_locked": True,
                "timeline_not_moved": True,
                "position_restarted": True,
                "controls_restored": True,
            },
            "T3": {"feedback_text": "No evaluation was produced."},
            "T4": {
                "attempt_id": "attempt-t4",
                "epoch_before": "A",
                "epoch_after": "B",
                "status_text": (
                    "The server no longer has this attempt. The attempt was not evaluated."
                ),
                "feedback_text": "",
                "retry_hidden": True,
                "start_enabled": True,
                "reference_enabled": True,
            },
            "T5": {
                "attempt_id": "attempt-t5",
                "epoch_before": "B",
                "epoch_after": "C",
                "status_text": (
                    "The server no longer has this attempt. The cancellation was not recorded."
                ),
                "feedback_text": "",
                "retry_hidden": True,
                "start_enabled": True,
                "reference_enabled": True,
            },
            "T6": {
                "inbox_empty": True,
                "empty_text": "No deliveries have been received on this device.",
                "identities": {
                    **_pins("attempt-t6", "capture-t6", "session-t6"),
                    "revision_id": REVISION,
                    "evaluation_digest": _evaluation("session-t6")["evaluation_digest"],
                },
                "requests": _counts(t6),
                "feedback_text": feedback.format(attempt="attempt-t6"),
            },
            "T7": {
                "attempt_id": "attempt-t7",
                "browser_outcome": "transport_failure",
                "status_before_retry": "The finish request did not finish.",
                "retry_hidden_before": False,
                "begin_during_retry": 0,
                "appends_during_retry": 0,
            },
        },
        "exchanges": [*t1, *t3, *t4, *t5, *t6, *t7],
        "epochs": [
            {"name": "A", "pid": 11, "ready": True, "delivery_count_at_ready": 0},
            {"name": "B", "pid": 22, "ready": True, "delivery_count_at_ready": 0},
            {"name": "C", "pid": 33, "ready": True, "delivery_count_at_ready": 0},
        ],
        "barriers": [
            {
                "op": "restart",
                "ok": True,
                "epoch_before": "A",
                "epoch_after": "B",
                "previous_pid": 11,
                "pid": 22,
            },
            {
                "op": "restart",
                "ok": True,
                "epoch_before": "B",
                "epoch_after": "C",
                "previous_pid": 22,
                "pid": 33,
            },
        ],
        "frozen_files": [
            {
                "path": "docs/mvp2/do015_artifacts/browser_smoke_summary.json",
                "sha256": digest,
                "before_sha256": digest,
                "after_sha256": digest,
            }
        ],
    }


def _problems(verifier: ModuleType, packet: dict[str, Any], root: Path) -> list[str]:
    return verifier.verify_evidence(packet, frozen_root=root)


def test_consistent_packet_passes(verifier: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    assert _problems(verifier, packet, root) == []


def test_swapped_attempt_and_revision_fail(verifier: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    packet["scenarios"]["T1"]["identities"]["attempt_id"] = "attempt-t6"
    packet["scenarios"]["T1"]["identities"]["revision_id"] = "rev-other"
    problems = _problems(verifier, packet, root)
    assert any("T1: recorded identities" in problem for problem in problems)


def test_dropped_and_duplicated_acknowledgements_fail(verifier: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    messages = [item for item in packet["exchanges"] if item["scenario"] == "T1"
        and item["operation"] == "message"]
    packet["exchanges"] = [item for item in packet["exchanges"] if item is not messages[0]]
    packet["scenarios"]["T1"]["requests"]["message"] = 1
    dropped = _problems(verifier, packet, root)
    assert any("T1" in problem and "sequence" in problem for problem in dropped)

    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    duplicate = copy.deepcopy(messages[0])
    duplicate["id"] = "T1-message-duplicate"
    insert_at = packet["exchanges"].index(messages[1])
    packet["exchanges"].insert(insert_at, duplicate)
    packet["scenarios"]["T1"]["requests"]["message"] = 3
    duplicated = _problems(verifier, packet, root)
    assert any("sequence" in problem for problem in duplicated)


def test_fabricated_restart_and_changed_retry_fail(verifier: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    packet["epochs"][1]["pid"] = 11
    packet["barriers"][0]["pid"] = 11
    restart = _problems(verifier, packet, root)
    assert any("did not change process id" in problem for problem in restart)

    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    finish = next(
        item for item in packet["exchanges"] if item["scenario"] == "T4"
            and item["operation"] == "finish"
    )
    finish["fabricated"] = True
    fabricated = _problems(verifier, packet, root)
    assert any("T4" in problem and "live server" in problem for problem in fabricated)

    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    retry = [item for item in packet["exchanges"] if item["scenario"] == "T7"
        and item["operation"] == "finish"][1]
    changed = _evaluated("attempt-t7", "capture-t7", "session-t7")
    changed["evaluation"]["evaluation_digest"] = "sha256:" + "22" * 32
    changed["guidance"]["evaluation_digest"] = changed["evaluation"]["evaluation_digest"]
    raw = json.dumps(changed).encode()
    retry["response_base64"] = base64.b64encode(raw).decode()
    retry["response_sha256"] = hashlib.sha256(raw).hexdigest()
    changed_result = _problems(verifier, packet, root)
    assert any("different evaluation digest" in problem for problem in changed_result)


def _rewrite_response(exchange: dict[str, Any], body: dict[str, Any]) -> None:
    """Replace a response and recompute its byte hash, as a forger would."""

    raw = json.dumps(body).encode()
    exchange["response_base64"] = base64.b64encode(raw).decode()
    exchange["response_sha256"] = hashlib.sha256(raw).hexdigest()


def _response(exchange: dict[str, Any]) -> dict[str, Any]:
    body = json.loads(base64.b64decode(exchange["response_base64"]))
    assert isinstance(body, dict)
    return body


def _find(packet: dict[str, Any], scenario: str, operation: str) -> list[dict[str, Any]]:
    return [item for item in packet["exchanges"] if item["scenario"] == scenario
        and item["operation"] == operation]


def test_preview_with_another_assignment_fails(verifier: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    preview = _find(packet, "T1", "preview")[0]
    body = _response(preview)
    body["assignment_id"] = "assignment-other"
    body["assignment_artifact_digest"] = "sha256:" + "cc" * 32
    _rewrite_response(preview, body)
    problems = _problems(verifier, packet, root)
    assert any("preview" in problem and "assignment_id pin" in problem for problem in problems)
    assert any("assignment_artifact_digest pin" in problem for problem in problems)


def test_nested_and_cross_scenario_pins_fail(verifier: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    begin = _find(packet, "T7", "begin")[0]
    body = _response(begin)
    body["preparation"]["score"]["canonical_revision"]["revision_id"] = "rev-other"
    _rewrite_response(begin, body)
    nested = _problems(verifier, packet, root)
    assert any("T7" in problem and "revision_id pin" in problem for problem in nested)

    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    begin = _find(packet, "T4", "begin")[0]
    body = _response(begin)
    body["delivery_id"] = "delivery-other"
    _rewrite_response(begin, body)
    crossed = _problems(verifier, packet, root)
    assert any("T4" in problem and "delivery_id pin" in problem for problem in crossed)


def test_unsuccessful_choice_before_begin_fails(verifier: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    choice = _find(packet, "T1", "choice")[0]
    choice["status"] = 409
    _rewrite_response(choice, {"error": "assignment_digest_mismatch"})
    problems = _problems(verifier, packet, root)
    assert any("no successful choice preceded begin" in problem for problem in problems)


def test_evaluation_body_must_hash_to_its_digest(verifier: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    finish = _find(packet, "T1", "finish")[0]
    body = _response(finish)
    body["evaluation"]["summary"]["matched_count"] = 987654
    _rewrite_response(finish, body)
    problems = _problems(verifier, packet, root)
    assert any("T1: evaluation body does not hash" in problem for problem in problems)


def test_feedback_counts_must_be_the_evaluations(verifier: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    shown = packet["scenarios"]["T1"]["feedback_text"]
    packet["scenarios"]["T1"]["feedback_text"] = shown.replace("Matched: 1", "Matched: 2")
    problems = _problems(verifier, packet, root)
    assert problems == ["T1: feedback Matched count is not the evaluation's"]


def test_retry_with_a_changed_result_and_kept_digest_fails(
    verifier: ModuleType, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    retry = _find(packet, "T7", "finish")[1]
    body = _response(retry)
    body["evaluation"]["summary"]["matched_count"] = 987654
    _rewrite_response(retry, body)
    edited = _problems(verifier, packet, root)
    assert any("complete stored result" in problem for problem in edited)
    assert any("retry evaluation body does not hash" in problem for problem in edited)

    # A field outside the evaluation digest still has to be the stored one.
    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    retry = _find(packet, "T7", "finish")[1]
    body = _response(retry)
    body["hardware_status"]["midi_input"] = "VERIFIED"
    _rewrite_response(retry, body)
    undigested = _problems(verifier, packet, root)
    assert undigested == ["T7: retry did not return the complete stored result"]


def test_non_object_evaluation_is_reported_not_raised(
    verifier: ModuleType, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    for exchange in _find(packet, "T7", "finish"):
        body = _response(exchange)
        body["evaluation"] = None
        _rewrite_response(exchange, body)
    problems = _problems(verifier, packet, root)
    assert any("T7: the stored evaluation digest is not a sha256 pin" in problem
        for problem in problems)


def test_missing_scenario_and_frozen_drift_fail(verifier: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    del packet["scenarios"]["T4"]
    missing = _problems(verifier, packet, root)
    assert any("T4: required scenario is missing" in problem for problem in missing)

    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    frozen = root / "docs" / "mvp2" / "do015_artifacts" / "browser_smoke_summary.json"
    frozen.write_bytes(b'{"status":"changed"}\n')
    drifted = _problems(verifier, packet, root)
    assert any("browser_smoke_summary.json" in problem
        and "no longer match" in problem for problem in drifted)

    packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
    packet["complete"] = False
    incomplete = _problems(verifier, packet, root)
    assert any("incomplete" in problem for problem in incomplete)

    for loose_zero in (False, 0.0, "0", None):
        packet = _packet(root / "docs" / "mvp2" / "do015_artifacts")
        packet["failures"] = loose_zero
        loose = _problems(verifier, packet, root)
        assert loose == ["evidence: the driver recorded failures"], loose_zero


def test_missing_chrome_does_not_start_a_server(driver: ModuleType, tmp_path: Path) -> None:
    code = driver.main(
        [
            str(tmp_path),
            "--chrome-executable",
            str(tmp_path / "missing-chrome"),
            "--puppeteer-module",
            str(tmp_path / "missing-puppeteer.js"),
        ]
    )
    assert code == 2
    classification = json.loads((tmp_path / "classification.json").read_text(encoding="utf-8"))
    assert classification["kind"] == "browser_launch"


def test_readiness_timeout_is_bounded(driver: ModuleType) -> None:
    assert driver.wait_for_http("http://127.0.0.1:9/lesson-inbox.html", 0.3) is False


def test_driver_failure_reaps_its_child(driver: ModuleType, tmp_path: Path) -> None:
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    code = driver.run_command_and_reap(
        [sys.executable, "-c", "import sys; sys.exit(1)"],
        sleeper,
        tmp_path,
        timeout=5,
    )
    assert code == 1
    assert sleeper.poll() is not None
    classification = json.loads((tmp_path / "classification.json").read_text(encoding="utf-8"))
    assert classification["kind"] == "driver_failure"


def test_retained_packet_matches_its_bytes(verifier: ModuleType) -> None:
    path = REPO_ROOT / "docs/mvp2/do016_integration_artifacts/evidence.json"
    packet = json.loads(path.read_text(encoding="utf-8"))
    assert verifier.verify_evidence(packet, frozen_root=REPO_ROOT) == []


def test_child_server_restarts_on_the_same_port(driver: ModuleType, tmp_path: Path) -> None:
    port = driver.free_port()
    first = subprocess.Popen(
        [sys.executable, str(DRIVER), "--child-server", "--port", str(port)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert first.stdout is not None
    ready = json.loads(first.stdout.readline())
    assert driver.wait_for_http(f"{ready['base']}/lesson-inbox.html", 10)
    assert driver.delivery_count(ready["base"]) == 0
    driver.stop_child(first)
    assert first.wait(timeout=5) == 0
    second = subprocess.Popen(
        [sys.executable, str(DRIVER), "--child-server", "--port", str(port)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert second.stdout is not None
    again = json.loads(second.stdout.readline())
    assert again["pid"] != ready["pid"]
    assert driver.wait_for_http(f"{again['base']}/lesson-inbox.html", 10)
    driver.stop_child(second)
    assert second.wait(timeout=5) == 0
