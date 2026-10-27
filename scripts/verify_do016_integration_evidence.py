"""Offline checks for one DO-016 integration evidence packet.

The packet's own PASS flag is not evidence. Every claim below is recomputed
from the recorded request and response bytes, the restart barriers, and the
frozen-file bytes on disk.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "master_all_strings.do016_integration_evidence"
SCHEMA_VERSION = "1"
REQUIRED_SCENARIOS = ("T1", "T2", "T3", "T4", "T5", "T6", "T7")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
PIN_FIELDS = (
    "delivery_id",
    "assignment_id",
    "content_id",
    "assignment_artifact_digest",
    "assignment_behavior_digest",
    "revision_id",
    "attempt_id",
    "capture_id",
    "performance_session_id",
    "evaluation_digest",
)
T2_FLAGS = (
    "non_normal_rate_before",
    "loop_toggled_before",
    "normal_rate_during",
    "loop_off_during",
    "controls_locked",
    "timeline_not_moved",
    "position_restarted",
    "controls_restored",
)


def verify_evidence(packet: dict[str, Any], *, frozen_root: Path | None = None) -> list[str]:
    """Return one diagnostic per broken boundary. An empty list is acceptance."""

    problems: list[str] = []
    if not isinstance(packet, dict):
        return ["evidence: the packet is not an object"]
    if packet.get("schema") != SCHEMA or packet.get("schema_version") != SCHEMA_VERSION:
        problems.append("evidence: schema or version is not the integration packet")
    if packet.get("complete") is not True:
        problems.append("evidence: the run is incomplete")
    if packet.get("failures") not in (0,):
        problems.append("evidence: the driver recorded failures")
    if not isinstance(packet.get("run_id"), str) or not packet["run_id"].strip():
        problems.append("evidence: run id is missing")
    for field in ("tested_sha", "tested_tree"):
        if not isinstance(packet.get(field), str) or SHA.fullmatch(packet[field]) is None:
            problems.append(f"evidence: {field} is not a full git sha")
    if packet.get("dirty"):
        problems.append("evidence: the tested tree was dirty")
    for field in ("node", "python", "browser", "chrome"):
        if not isinstance(packet.get(field), str) or not packet[field].strip():
            problems.append(f"evidence: {field} version was not recorded")
    if packet.get("physical_midi") != "UNVERIFIED_PHYSICAL_MIDI_INPUT":
        problems.append("evidence: physical MIDI is not labeled unverified")
    if packet.get("physical_audio") != "UNVERIFIED_AUDIO_OUTPUT":
        problems.append("evidence: physical audio is not labeled unverified")
    if packet.get("injected_midi") is not True:
        problems.append("evidence: MIDI injection was not labeled")

    scenarios = packet.get("scenarios")
    exchanges = packet.get("exchanges")
    epochs = packet.get("epochs")
    barriers = packet.get("barriers")
    if not isinstance(scenarios, dict):
        problems.append("evidence: scenarios are missing")
        scenarios = {}
    if not isinstance(exchanges, list):
        problems.append("evidence: exchanges are missing")
        exchanges = []
    if not isinstance(epochs, list) or not isinstance(barriers, list):
        problems.append("evidence: restart barriers are missing")
        epochs = epochs if isinstance(epochs, list) else []
        barriers = barriers if isinstance(barriers, list) else []
    for scenario_id in REQUIRED_SCENARIOS:
        if scenario_id not in scenarios:
            problems.append(f"{scenario_id}: required scenario is missing")

    decoded: list[dict[str, Any]] = []
    for index, exchange in enumerate(exchanges):
        item, item_problems = _decode_exchange(index, exchange)
        problems.extend(item_problems)
        if item is not None:
            decoded.append(item)

    by_scenario = {scenario_id: [] for scenario_id in REQUIRED_SCENARIOS}
    for item in decoded:
        scenario_id = item["scenario"]
        if scenario_id in by_scenario:
            by_scenario[scenario_id].append(item)
        elif isinstance(scenario_id, str):
            problems.append(f"evidence: exchange {item['id']} has unknown scenario {scenario_id}")

    identities: dict[str, dict[str, str]] = {}
    if "T1" in scenarios:
        found = _verify_evaluated_chain(problems, "T1", scenarios["T1"], by_scenario["T1"])
        if found is not None:
            identities["T1"] = found
    if "T2" in scenarios or "T1" in scenarios:
        _verify_t2(problems, scenarios.get("T2"))
    if "T3" in scenarios:
        _verify_t3(problems, scenarios["T3"], by_scenario["T3"], scenarios.get("T4"))
    if "T4" in scenarios:
        _verify_restart_terminal(
            problems,
            "T4",
            scenarios["T4"],
            by_scenario["T4"],
            epochs,
            barriers,
            operation="finish",
            phrase="not evaluated",
        )
    if "T5" in scenarios:
        _verify_restart_terminal(
            problems,
            "T5",
            scenarios["T5"],
            by_scenario["T5"],
            epochs,
            barriers,
            operation="cancel",
            phrase="not recorded",
        )
    if "T6" in scenarios:
        found = _verify_evaluated_chain(problems, "T6", scenarios["T6"], by_scenario["T6"])
        if found is not None:
            identities["T6"] = found
        _verify_t6_recovery(problems, scenarios["T6"], identities.get("T1"))
    if "T7" in scenarios:
        _verify_t7(problems, scenarios["T7"], by_scenario["T7"])
    _verify_epochs(problems, epochs, barriers)
    _verify_frozen(problems, packet.get("frozen_files"), frozen_root)
    return problems


def _decode_exchange(index: int, exchange: Any) -> tuple[dict[str, Any] | None, list[str]]:
    label = f"exchange[{index}]"
    problems: list[str] = []
    if not isinstance(exchange, dict):
        return None, [f"{label}: not an object"]
    label = str(exchange.get("id") or label)
    response, response_problem = _hashed_bytes(exchange, "response")
    request, request_problem = _hashed_bytes(exchange, "request")
    if response_problem:
        problems.append(f"{label}: {response_problem}")
    if request_problem:
        problems.append(f"{label}: {request_problem}")
    if problems:
        return None, problems
    assert response is not None and request is not None
    response_body = _json_object(response)
    request_body = _json_object(request)
    if response_body is None:
        problems.append(f"{label}: response bytes are not a JSON object")
    if request_body is None:
        problems.append(f"{label}: request bytes are not a JSON object")
    if problems or response_body is None or request_body is None:
        return None, problems
    return {
        "id": label,
        "scenario": exchange.get("scenario"),
        "operation": exchange.get("operation"),
        "source": exchange.get("source"),
        "fabricated": exchange.get("fabricated"),
        "status": exchange.get("status"),
        "response": response_body,
        "request": request_body,
    }, []


def _hashed_bytes(exchange: dict[str, Any], prefix: str) -> tuple[bytes | None, str | None]:
    encoded = exchange.get(f"{prefix}_base64")
    recorded = exchange.get(f"{prefix}_sha256")
    if not isinstance(encoded, str) or not isinstance(recorded, str):
        return None, f"missing {prefix} bytes"
    try:
        raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        return None, f"{prefix} bytes are not base64"
    if hashlib.sha256(raw).hexdigest() != recorded:
        return None, f"{prefix} sha256 does not match the recorded bytes"
    return raw, None


def _json_object(raw: bytes) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _verify_evaluated_chain(
    problems: list[str],
    scenario_id: str,
    scenario: Any,
    items: list[dict[str, Any]],
) -> dict[str, str] | None:
    if not isinstance(scenario, dict):
        problems.append(f"{scenario_id}: scenario is not an object")
        return None
    operations = [item["operation"] for item in items]
    preview = _index(operations, "preview")
    choice = _index(operations, "choice")
    prepare = _index(operations, "prepare")
    begin = _index(operations, "begin")
    finish = _rindex(operations, "finish")
    if not (0 <= preview < choice < prepare < begin < finish):
        problems.append(f"{scenario_id}: request order is not preview then finish")
        return None
    if operations.count("begin") != 1 or operations.count("finish") != 1:
        problems.append(f"{scenario_id}: expected one begin and one finish")
    if "cancel" in operations or "guided" in operations or "performance" in operations:
        problems.append(f"{scenario_id}: a forbidden request was recorded")
    messages = items[begin + 1 : finish]
    if not messages or any(item["operation"] != "message" for item in messages):
        problems.append(f"{scenario_id}: appends are not strictly between begin and finish")
    begin_item = items[begin]
    finish_item = items[finish]
    if begin_item["status"] != 201 or begin_item["response"].get("attempt_status") != "CAPTURING":
        problems.append(f"{scenario_id}: begin was not accepted")
    if finish_item["status"] != 200 or finish_item["response"].get("attempt_status") != "EVALUATED":
        problems.append(f"{scenario_id}: finish was not evaluated")
    if begin_item["fabricated"] is not False or finish_item["source"] != "browser":
        problems.append(f"{scenario_id}: begin or finish was not a live browser response")
    pins = _pins(begin_item["response"], finish_item["response"])
    if pins is None:
        problems.append(f"{scenario_id}: identity pins are incomplete or disagree")
        return None
    if len(set(pins.values())) != len(pins):
        problems.append(f"{scenario_id}: identity pins are not distinct")
    if not DIGEST.fullmatch(pins["assignment_artifact_digest"]):
        problems.append(f"{scenario_id}: artifact digest is not a sha256 pin")
    if not DIGEST.fullmatch(pins["assignment_behavior_digest"]):
        problems.append(f"{scenario_id}: behavior digest is not a sha256 pin")
    if not DIGEST.fullmatch(pins["evaluation_digest"]):
        problems.append(f"{scenario_id}: evaluation digest is not a sha256 pin")
    _verify_messages(problems, scenario_id, messages, pins["attempt_id"])
    recorded = scenario.get("identities")
    if recorded != pins:
        problems.append(f"{scenario_id}: recorded identities do not match the response bytes")
    _verify_counts(problems, scenario_id, scenario.get("requests"), items)
    feedback = scenario.get("feedback_text")
    if not isinstance(feedback, str):
        problems.append(f"{scenario_id}: feedback text is missing")
    else:
        if pins["attempt_id"] not in feedback:
            problems.append(f"{scenario_id}: feedback does not show this attempt")
        if not all(label in feedback for label in ("Matched:", "Missing:", "Extra:")):
            problems.append(f"{scenario_id}: feedback does not show the three counts")
        midi = "UNVERIFIED_PHYSICAL_MIDI_INPUT"
        audio = "UNVERIFIED_AUDIO_OUTPUT"
        if midi not in feedback or audio not in feedback:
            problems.append(f"{scenario_id}: feedback does not show unverified hardware")
        if re.search(r"lesson complete|mastered", feedback, re.IGNORECASE):
            problems.append(f"{scenario_id}: feedback claims lesson completion")
    hardware = finish_item["response"].get("hardware_status")
    if hardware != {
        "midi_input": "UNVERIFIED_PHYSICAL_MIDI_INPUT",
        "audio_output": "UNVERIFIED_AUDIO_OUTPUT",
    }:
        problems.append(f"{scenario_id}: server hardware status is not unverified")
    return pins


def _verify_messages(
    problems: list[str],
    scenario_id: str,
    messages: list[dict[str, Any]],
    attempt_id: str,
) -> None:
    for index, item in enumerate(messages):
        if item["status"] != 200:
            problems.append(f"{scenario_id}: append {index} was not accepted")
            continue
        if item["request"].get("sequence_number") != index:
            problems.append(f"{scenario_id}: append {index} broke sequence order")
        if item["request"].get("attempt_id") != attempt_id:
            problems.append(f"{scenario_id}: append {index} names another attempt")
        if item["response"].get("accepted_event_count") != index + 1:
            problems.append(f"{scenario_id}: append {index} acknowledgement count is wrong")
        if item["response"].get("attempt_id") != attempt_id:
            problems.append(f"{scenario_id}: append {index} acknowledgement names another attempt")
        if item["fabricated"] is not False:
            problems.append(f"{scenario_id}: append {index} was fabricated")


def _verify_counts(problems: list[str], scenario_id: str, requests: Any, items: list[dict[str,
    Any]]) -> None:
    if not isinstance(requests, dict):
        problems.append(f"{scenario_id}: request counts are missing")
        return
    expected = {
        "begin": sum(item["operation"] == "begin" for item in items),
        "message": sum(item["operation"] == "message" for item in items),
        "finish": sum(item["operation"] == "finish" for item in items),
        "cancel": sum(item["operation"] == "cancel" for item in items),
        "guided": 0,
        "performance": 0,
    }
    if requests != expected:
        problems.append(f"{scenario_id}: request counts do not match the exchanges")


def _verify_t2(problems: list[str], scenario: Any) -> None:
    if not isinstance(scenario, dict):
        problems.append("T2: scenario is not an object")
        return
    for flag in T2_FLAGS:
        if scenario.get(flag) is not True:
            problems.append(f"T2: {flag} was not observed")


def _verify_t3(
    problems: list[str],
    scenario: Any,
    items: list[dict[str, Any]],
    next_scenario: Any,
) -> None:
    if not isinstance(scenario, dict):
        problems.append("T3: scenario is not an object")
        return
    operations = [item["operation"] for item in items]
    begin = _index(operations, "begin")
    cancel = _rindex(operations, "cancel")
    if begin < 0 or cancel < begin:
        problems.append("T3: cancel does not follow begin")
        return
    messages = [item for item in items[begin + 1 : cancel] if item["operation"] == "message"]
    if not messages:
        problems.append("T3: cancel has no acknowledged message")
    begin_item = items[begin]
    attempt_id = begin_item["response"].get("attempt_id")
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        problems.append("T3: begin has no attempt id")
        attempt_id = ""
    cancelled = items[cancel]
    if cancelled["status"] != 200 or cancelled["response"].get("attempt_status") != "INTERRUPTED":
        problems.append("T3: cancel was not an interrupted result")
    if "evaluation" in items[cancel]["response"]:
        problems.append("T3: interrupted result contains evaluation")
    if items[cancel]["request"].get("attempt_id") != attempt_id:
        problems.append("T3: cancel names another attempt")
    feedback = scenario.get("feedback_text")
    if not isinstance(feedback, str) or "No evaluation was produced." not in feedback:
        problems.append("T3: interrupted feedback does not disclaim evaluation")
    if isinstance(feedback, str) and "Matched:" in feedback:
        problems.append("T3: interrupted feedback shows evaluation counts")
    next_id = ""
    if isinstance(next_scenario, dict):
        next_id = str(next_scenario.get("attempt_id") or "")
    if not next_id or next_id == attempt_id:
        problems.append("T3: the next attempt does not have a fresh id")
    _verify_messages(problems, "T3", messages, attempt_id)


def _verify_restart_terminal(
    problems: list[str],
    scenario_id: str,
    scenario: Any,
    items: list[dict[str, Any]],
    epochs: list[Any],
    barriers: list[Any],
    *,
    operation: str,
    phrase: str,
) -> None:
    if not isinstance(scenario, dict):
        problems.append(f"{scenario_id}: scenario is not an object")
        return
    operations = [item["operation"] for item in items]
    begin = _index(operations, "begin")
    terminal = _rindex(operations, operation)
    if begin < 0 or terminal < begin:
        problems.append(f"{scenario_id}: {operation} does not follow begin")
        return
    messages = [item for item in items[begin + 1 : terminal] if item["operation"] == "message"]
    if not messages:
        problems.append(f"{scenario_id}: no message was acknowledged before restart")
    if items[begin]["status"] != 201:
        problems.append(f"{scenario_id}: begin was not accepted")
    attempt_id = items[begin]["response"].get("attempt_id")
    if not isinstance(attempt_id, str):
        problems.append(f"{scenario_id}: begin has no attempt id")
        attempt_id = ""
    if scenario.get("attempt_id") != attempt_id:
        problems.append(f"{scenario_id}: recorded attempt id disagrees with begin")
    terminal_item = items[terminal]
    if terminal_item["fabricated"] is not False or terminal_item["source"] != "browser":
        problems.append(f"{scenario_id}: the terminal response was not the live server")
    if terminal_item["status"] != 404 or terminal_item["response"] != {"error": "unknown_attempt"}:
        problems.append(f"{scenario_id}: expected a real 404 unknown_attempt")
    if terminal_item["request"].get("attempt_id") != attempt_id:
        problems.append(f"{scenario_id}: {operation} names another attempt")
    status_text = scenario.get("status_text")
    feedback = scenario.get("feedback_text")
    if not isinstance(status_text, str) or "no longer has this attempt" not in status_text:
        problems.append(f"{scenario_id}: the page did not report the lost attempt")
    if not isinstance(status_text, str) or phrase not in status_text:
        problems.append(f"{scenario_id}: the page claimed the {operation} succeeded")
    leaked = isinstance(feedback, str) and (
        "Matched:" in feedback or "No evaluation was produced." in feedback
    )
    if not isinstance(feedback, str) or leaked:
        problems.append(f"{scenario_id}: stale or evaluated feedback remained")
    if scenario.get("retry_hidden") is not True:
        problems.append(f"{scenario_id}: finish retry stayed available")
    if scenario.get("start_enabled") is not True or scenario.get("reference_enabled") is not True:
        problems.append(f"{scenario_id}: reference practice did not recover")
    before = scenario.get("epoch_before")
    after = scenario.get("epoch_after")
    barrier = _restart_barrier(barriers, before, after)
    if barrier is None:
        problems.append(f"{scenario_id}: no restart barrier joins the two epochs")
        return
    epoch_before = _epoch(epochs, before)
    epoch_after = _epoch(epochs, after)
    if epoch_before is None or epoch_after is None:
        problems.append(f"{scenario_id}: restart epochs are missing")
        return
    if epoch_before.get("pid") == epoch_after.get("pid"):
        problems.append(f"{scenario_id}: restart did not change process id")
    same_process = barrier.get("previous_pid") == epoch_before.get("pid")
    same_successor = barrier.get("pid") == epoch_after.get("pid")
    if not same_process or not same_successor:
        problems.append(f"{scenario_id}: restart barrier disagrees with the epoch process ids")
    if epoch_after.get("delivery_count_at_ready") != 0:
        problems.append(f"{scenario_id}: the restarted process still had deliveries")
    _verify_messages(problems, scenario_id, messages, attempt_id)


def _verify_t6_recovery(
    problems: list[str],
    scenario: dict[str, Any],
    previous: dict[str, str] | None,
) -> None:
    if scenario.get("inbox_empty") is not True:
        problems.append("T6: the inbox still showed a delivery after restart")
    if not isinstance(scenario.get("empty_text"), str) or not scenario["empty_text"].strip():
        problems.append("T6: empty-inbox text was not recorded")
    if previous is None:
        problems.append("T6: there is no earlier evaluated attempt to compare")
        return
    current = scenario.get("identities")
    if not isinstance(current, dict):
        return
    for field in ("attempt_id", "capture_id", "performance_session_id"):
        if current.get(field) == previous.get(field):
            problems.append(f"T6: {field} was reused after recovery")
    feedback = scenario.get("feedback_text")
    if isinstance(feedback, str) and previous["attempt_id"] in feedback:
        problems.append("T6: the previous attempt's feedback leaked into the new one")


def _verify_t7(problems: list[str], scenario: Any, items: list[dict[str, Any]]) -> None:
    if not isinstance(scenario, dict):
        problems.append("T7: scenario is not an object")
        return
    finishes = [item for item in items if item["operation"] == "finish"]
    begins = [item for item in items if item["operation"] == "begin"]
    if len(begins) != 1 or len(finishes) != 2:
        problems.append("T7: expected one begin and two finishes")
        return
    forwarded, retry = finishes
    if forwarded["source"] != "forwarded_server" or forwarded["fabricated"] is not False:
        problems.append("T7: the stored finish was not forwarded once to the server")
    if retry["source"] != "browser" or retry["fabricated"] is not False:
        problems.append("T7: the retry was not a live browser response")
    if forwarded["status"] != 200 or retry["status"] != 200:
        problems.append("T7: both finishes were not stored successes")
    if forwarded["response"].get("attempt_status") != "EVALUATED":
        problems.append("T7: the stored finish was not evaluated")
    if retry["response"].get("attempt_status") != "EVALUATED":
        problems.append("T7: the retry was not evaluated")
    attempt_id = begins[0]["response"].get("attempt_id")
    if scenario.get("attempt_id") != attempt_id:
        problems.append("T7: recorded attempt id disagrees with begin")
    for item in (forwarded, retry):
        request_id = item["request"].get("attempt_id")
        response_id = item["response"].get("attempt_id")
        if request_id != attempt_id or response_id != attempt_id:
            problems.append("T7: a finish names another attempt")
    stored_digest = forwarded["response"].get("evaluation", {}).get("evaluation_digest")
    retry_digest = retry["response"].get("evaluation", {}).get("evaluation_digest")
    if stored_digest != retry_digest:
        problems.append("T7: retry returned a different evaluation digest")
    if forwarded["response"].get("capture_id") != retry["response"].get("capture_id"):
        problems.append("T7: retry returned a different capture")
    stored_session = forwarded["response"].get("performance_session_id")
    retry_session = retry["response"].get("performance_session_id")
    if stored_session != retry_session:
        problems.append("T7: retry returned a different performance session")
    if scenario.get("browser_outcome") != "transport_failure":
        problems.append("T7: the browser was not shown a lost finish")
    status_text = scenario.get("status_before_retry")
    if not isinstance(status_text, str) or "did not finish" not in status_text:
        problems.append("T7: the page did not stay unconfirmed")
    if scenario.get("retry_hidden_before") is not False:
        problems.append("T7: retry was not offered")
    if scenario.get("begin_during_retry") != 0 or scenario.get("appends_during_retry") != 0:
        problems.append("T7: retry replayed begin or MIDI")
    begin_at = _index([item["operation"] for item in items], "begin")
    forward_at = next(index for index, item in enumerate(items) if item is forwarded)
    retry_at = next(index for index, item in enumerate(items) if item is retry)
    between = items[forward_at + 1 : retry_at + 1]
    if any(item["operation"] in {"begin", "message"} for item in between):
        problems.append("T7: MIDI or a new begin was recorded between finish and retry")
    messages = [item for item in items[begin_at + 1 : forward_at] if item["operation"] == "message"]
    if not messages:
        problems.append("T7: no message was acknowledged before the lost finish")
    else:
        _verify_messages(problems, "T7", messages, str(attempt_id))


def _verify_epochs(problems: list[str], epochs: list[Any], barriers: list[Any]) -> None:
    names = []
    pids = []
    for epoch in epochs:
        if not isinstance(epoch, dict):
            problems.append("epochs: one entry is not an object")
            continue
        names.append(epoch.get("name"))
        pid = epoch.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            problems.append(f"epochs: {epoch.get('name')} has no process id")
        else:
            pids.append(pid)
        if epoch.get("ready") is not True:
            problems.append(f"epochs: {epoch.get('name')} was not acknowledged ready")
    if len(pids) != len(set(pids)):
        problems.append("epochs: two epochs share a process id")
    if names[:3] != ["A", "B", "C"]:
        problems.append("epochs: expected process epochs A, B, and C")
    restarts = [item for item in barriers if isinstance(item, dict) and item.get("op") == "restart"]
    if len(restarts) < 2:
        problems.append("epochs: fewer than two real restarts were acknowledged")


def _verify_frozen(problems: list[str], recorded: Any, frozen_root: Path | None) -> None:
    if not isinstance(recorded, list) or not recorded:
        problems.append("frozen: no protected files were recorded")
        return
    for item in recorded:
        if not isinstance(item, dict):
            problems.append("frozen: one record is not an object")
            continue
        path = item.get("path")
        digest = item.get("sha256")
        before = item.get("before_sha256")
        after = item.get("after_sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            problems.append("frozen: path or hash is missing")
            continue
        if before != digest or after != digest:
            problems.append(f"frozen: {path} changed during the witness")
        if frozen_root is None:
            continue
        file_path = frozen_root / path
        if not file_path.is_file():
            problems.append(f"frozen: {path} is missing on disk")
            continue
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual != digest:
            problems.append(f"frozen: {path} bytes no longer match the packet")


def _pins(begin: dict[str, Any], finish: dict[str, Any]) -> dict[str, str] | None:
    revision = (
        begin.get("preparation", {})
        .get("score", {})
        .get("canonical_revision", {})
        .get("revision_id")
    )
    evaluation = finish.get("evaluation", {})
    guidance = finish.get("guidance", {})
    digest = evaluation.get("evaluation_digest") if isinstance(evaluation, dict) else None
    if not isinstance(guidance, dict) or guidance.get("evaluation_digest") != digest:
        return None
    if guidance.get("canonical_revision_id") != revision:
        return None
    values = {
        "delivery_id": begin.get("delivery_id"),
        "assignment_id": begin.get("assignment_id"),
        "content_id": begin.get("content_id"),
        "assignment_artifact_digest": begin.get("assignment_artifact_digest"),
        "assignment_behavior_digest": begin.get("assignment_behavior_digest"),
        "revision_id": revision,
        "attempt_id": begin.get("attempt_id"),
        "capture_id": begin.get("capture_id"),
        "performance_session_id": begin.get("performance_session_id"),
        "evaluation_digest": digest,
    }
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        return None
    for field in PIN_FIELDS:
        if field == "revision_id":
            continue
        if finish.get(field) != values[field] and field != "evaluation_digest":
            return None
    return {key: str(value) for key, value in values.items()}


def _index(operations: list[Any], operation: str) -> int:
    try:
        return operations.index(operation)
    except ValueError:
        return -1


def _rindex(operations: list[Any], operation: str) -> int:
    for index in range(len(operations) - 1, -1, -1):
        if operations[index] == operation:
            return index
    return -1


def _epoch(epochs: list[Any], name: Any) -> dict[str, Any] | None:
    for epoch in epochs:
        if isinstance(epoch, dict) and epoch.get("name") == name:
            return epoch
    return None


def _restart_barrier(barriers: list[Any], before: Any, after: Any) -> dict[str, Any] | None:
    for barrier in barriers:
        if (
            isinstance(barrier, dict)
            and barrier.get("op") == "restart"
            and barrier.get("epoch_before") == before
            and barrier.get("epoch_after") == after
            and barrier.get("ok") is True
        ):
            return barrier
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        packet = json.loads(args.evidence.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"evidence: cannot read the packet ({exc})")
        return 1
    problems = verify_evidence(packet, frozen_root=args.root)
    for problem in problems:
        print(problem)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
