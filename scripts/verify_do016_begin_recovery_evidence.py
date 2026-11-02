"""Offline checks for the keyed Begin recovery witness.

Every check reads the recorded request and response bytes. The parsed copies
beside them must decode from those bytes, and the packet's own pass flag and
notes are not evidence. Recomputed hashes do not make a rewritten packet pass:
it still has to keep every relationship between exchanges, namely the key a
wrapper answers, the payload a key was bound to, the attempt a recovery
interrupted, which process answered, and the order the server saw them in.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "master_all_strings.do016_begin_recovery_evidence"
SCHEMA_VERSION = "2"
BEGIN_REQUEST_SCHEMA_ID = "master_all_strings.received_lesson_begin_request"
BEGIN_REQUEST_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
SHA = re.compile(r"^[0-9a-f]{40}$")
SCENARIOS = ("W1", "W2", "W3", "W4", "W5")
REQUEST_FIELDS = {"begin_request_id", "begin"}
BEGIN_FIELDS = {
    "delivery_id",
    "expected_assignment_artifact_digest",
    "expected_assignment_behavior_digest",
    "device_id",
    "capture_time_ns",
}
WRAPPER_FIELDS = {"schema_id", "schema_version", "begin_request_id", "status", "attempt"}
# The HTTP statuses each wrapper status may arrive with.
WRAPPER_HTTP = {
    "STARTED": {200, 201},
    "PENDING": {202},
    "NO_ATTEMPT": {200},
    "INTERRUPTED": {200},
}
ATTEMPT_PINS = ("attempt_id", "capture_id", "performance_session_id")
# What each scenario must have recorded, in server order:
# (source, route, sender, page outcome, epoch, HTTP status, wrapper status or error).
EXPECTED: dict[str, list[tuple[str, str, str, str, str, int | None, str | None]]] = {
    "W1": [
        ("forwarded_server", "begin", "harness", "network_failure", "A", 201, "STARTED"),
        ("browser", "recovery", "browser", "response", "A", 200, "INTERRUPTED"),
    ],
    "W2": [
        ("recovery_before_begin", "recovery", "harness", "not_sent_by_page", "A", 200,
            "NO_ATTEMPT"),
        ("browser", "begin", "browser", "response", "A", 409, "begin_request_closed"),
        ("browser", "recovery", "browser", "response", "A", 200, "NO_ATTEMPT"),
    ],
    "W3": [
        ("recovery_during_prepare", "recovery", "harness", "not_sent_by_page", "A", 202,
            "PENDING"),
        ("browser", "begin", "browser", "response", "A", 200, "INTERRUPTED"),
    ],
    "W4": [
        ("forwarded_begin", "begin", "harness", "network_failure", "A", 201, "STARTED"),
        ("forwarded_recovery", "recovery", "harness", "network_failure", "A", 200,
            "INTERRUPTED"),
        ("browser", "recovery", "browser", "response", "A", 200, "INTERRUPTED"),
    ],
    "W5": [
        ("aborted_begin", "begin", "none", "network_failure", "A", None, None),
        ("browser", "recovery", "browser", "response", "B", 200, "NO_ATTEMPT"),
        ("replayed_begin", "begin", "harness", "not_sent_by_page", "B", 409,
            "begin_request_closed"),
    ],
}
# Scenarios whose page must still show the interrupted attempt it recovered.
FEEDBACK_SCENARIOS = ("W1", "W3", "W4")


def verify_evidence(packet: dict[str, Any]) -> list[str]:
    """Return one diagnostic per broken relationship. An empty list is acceptance."""

    if not isinstance(packet, dict):
        return ["evidence: packet is not an object"]
    problems: list[str] = []
    _verify_run(problems, packet)
    exchanges = packet.get("exchanges")
    epochs = packet.get("epochs")
    if not isinstance(exchanges, list) or not exchanges:
        problems.append("evidence: exchanges are missing")
        return problems
    decoded: list[dict[str, Any]] = []
    for index, exchange in enumerate(exchanges):
        item = _decode(problems, index, exchange)
        if item is not None:
            decoded.append(item)
    if len(decoded) != len(exchanges):
        return problems
    restart_seq = _verify_epochs(problems, epochs)
    _verify_order(problems, decoded, restart_seq)
    for item in decoded:
        _verify_shape(problems, item)
    _verify_sequences(problems, decoded)
    _verify_keys(problems, decoded)
    attempts = _verify_identities(problems, decoded)
    _verify_restart(problems, decoded, restart_seq)
    _verify_feedback(problems, packet.get("scenarios"), attempts)
    return problems


def _verify_run(problems: list[str], packet: dict[str, Any]) -> None:
    if packet.get("schema") != SCHEMA or packet.get("schema_version") != SCHEMA_VERSION:
        problems.append("evidence: schema or version is not the begin recovery packet")
    # bool is an int subclass and 0.0 == 0; only the integer zero is a clean run.
    failures = packet.get("failures")
    if packet.get("complete") is not True or type(failures) is not int or failures != 0:
        problems.append("evidence: the run is incomplete")
    for field in ("tested_sha", "tested_tree"):
        value = packet.get(field)
        if not isinstance(value, str) or SHA.fullmatch(value) is None:
            problems.append(f"evidence: {field} is not a full git sha")
    if packet.get("dirty") != "":
        problems.append("evidence: the tested tree was dirty")
    for field in ("python", "node", "chrome", "os"):
        value = packet.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"evidence: {field} version was not recorded")
    transport = packet.get("transport")
    if not isinstance(transport, dict) or transport.get("server_responses") != "live":
        problems.append("evidence: server responses are not labeled live")


def _decode(problems: list[str], index: int, exchange: Any) -> dict[str, Any] | None:
    label = f"exchange[{index}]"
    if not isinstance(exchange, dict):
        problems.append(f"{label}: not an object")
        return None
    seq = exchange.get("seq")
    if type(seq) is not int:
        problems.append(f"{label}: sequence number is missing")
        return None
    label = f"{exchange.get('scenario')} #{seq}"
    request_raw = _bytes(problems, label, exchange, "request")
    if request_raw is None:
        return None
    request = _object(request_raw)
    if request is None:
        problems.append(f"{label}: request bytes are not a JSON object")
        return None
    if exchange.get("request") != request:
        problems.append(f"{label}: parsed request is not its bytes")
    response: dict[str, Any] | None = None
    response_raw: bytes | None = None
    if exchange.get("response_base64") is None:
        if exchange.get("response_sha256") is not None or exchange.get("response") is not None:
            problems.append(f"{label}: an unsent request carries a response")
        if exchange.get("status") is not None:
            problems.append(f"{label}: an unsent request carries a status")
    else:
        response_raw = _bytes(problems, label, exchange, "response")
        if response_raw is None:
            return None
        response = _object(response_raw)
        if response is None:
            problems.append(f"{label}: response bytes are not a JSON object")
            return None
        if exchange.get("response") != response:
            problems.append(f"{label}: parsed response is not its bytes")
    return {
        "label": label,
        "seq": seq,
        "scenario": exchange.get("scenario"),
        "source": exchange.get("source"),
        "route": exchange.get("route"),
        "sender": exchange.get("sender"),
        "page_outcome": exchange.get("page_outcome"),
        "epoch": exchange.get("epoch"),
        "status": exchange.get("status"),
        "request_raw": request_raw,
        "request": request,
        "response": response,
    }


def _bytes(
    problems: list[str], label: str, exchange: dict[str, Any], prefix: str
) -> bytes | None:
    encoded = exchange.get(f"{prefix}_base64")
    recorded = exchange.get(f"{prefix}_sha256")
    if not isinstance(encoded, str) or not isinstance(recorded, str):
        problems.append(f"{label}: {prefix} bytes are missing")
        return None
    try:
        raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError, binascii.Error):
        problems.append(f"{label}: {prefix} bytes are not base64")
        return None
    if hashlib.sha256(raw).hexdigest() != recorded:
        problems.append(f"{label}: {prefix} sha256 does not match the recorded bytes")
        return None
    return raw


def _object(raw: bytes) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _verify_epochs(problems: list[str], epochs: Any) -> int | None:
    if not isinstance(epochs, list) or len(epochs) != 2:
        problems.append("epochs: expected process epochs A and B")
        return None
    first, second = epochs
    if not isinstance(first, dict) or not isinstance(second, dict):
        problems.append("epochs: an epoch is not an object")
        return None
    if first.get("name") != "A" or second.get("name") != "B":
        problems.append("epochs: expected process epochs A and B")
    pids = [first.get("pid"), second.get("pid")]
    if any(type(pid) is not int or pid <= 0 for pid in pids):
        problems.append("epochs: an epoch has no process id")
    elif pids[0] == pids[1]:
        problems.append("epochs: the restart did not change process id")
    if second.get("previous_pid") != first.get("pid"):
        problems.append("epochs: the restart did not replace epoch A's process")
    restart_seq = second.get("restart_seq")
    if type(restart_seq) is not int:
        problems.append("epochs: the restart has no place in the sequence")
        return None
    return int(restart_seq)


def _verify_order(
    problems: list[str], items: list[dict[str, Any]], restart_seq: int | None
) -> None:
    numbers = [item["seq"] for item in items]
    if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
        problems.append("order: exchanges are not in sequence order")
    expected = set(range(1, len(numbers) + 2))
    if restart_seq is None or set(numbers) | {restart_seq} != expected:
        problems.append("order: the sequence has a gap or a duplicate")
    positions = []
    for item in items:
        if item["scenario"] not in SCENARIOS:
            problems.append(f"{item['label']}: unknown scenario")
            continue
        positions.append(SCENARIOS.index(item["scenario"]))
    if positions != sorted(positions):
        problems.append("order: scenarios interleave")


def _verify_shape(problems: list[str], item: dict[str, Any]) -> None:
    label = item["label"]
    request = item["request"]
    if set(request) != REQUEST_FIELDS:
        problems.append(f"{label}: request is not a keyed begin request")
        return
    key = request["begin_request_id"]
    if not isinstance(key, str) or BEGIN_REQUEST_ID.fullmatch(key) is None:
        problems.append(f"{label}: request key is not a lowercase uuid v4")
    begin = request["begin"]
    if not isinstance(begin, dict) or set(begin) != BEGIN_FIELDS:
        problems.append(f"{label}: request payload is not a begin payload")
        return
    capture = begin["capture_time_ns"]
    if type(capture) is not int or capture < 0:
        problems.append(f"{label}: request capture time is not a nonnegative integer")
    response = item["response"]
    if response is None:
        return
    if "error" in response:
        if set(response) != {"error"} or not isinstance(response["error"], str):
            problems.append(f"{label}: error response is not a single error")
        if item["status"] not in (400, 404, 409, 422, 500):
            problems.append(f"{label}: error response has a success status")
        return
    if set(response) != WRAPPER_FIELDS:
        problems.append(f"{label}: response is not a begin request wrapper")
        return
    if response["schema_id"] != BEGIN_REQUEST_SCHEMA_ID or response["schema_version"] != "1.0.0":
        problems.append(f"{label}: wrapper schema is not begin request 1.0.0")
    if response["begin_request_id"] != key:
        problems.append(f"{label}: wrapper key is not the request's key")
    status = response["status"]
    if status not in WRAPPER_HTTP:
        problems.append(f"{label}: wrapper status {status!r} is unknown")
        return
    if item["status"] not in WRAPPER_HTTP[status]:
        problems.append(f"{label}: HTTP {item['status']} cannot carry {status}")
    attempt = response["attempt"]
    if status in ("PENDING", "NO_ATTEMPT"):
        if attempt is not None:
            problems.append(f"{label}: {status} carries an attempt")
        return
    if not isinstance(attempt, dict):
        problems.append(f"{label}: {status} carries no attempt")
        return
    phase = "CAPTURING" if status == "STARTED" else "INTERRUPTED"
    if attempt.get("attempt_status") != phase:
        problems.append(f"{label}: {status} attempt is not {phase}")
    if status == "INTERRUPTED":
        capture_events = attempt.get("raw_capture", {}).get("events") if isinstance(
            attempt.get("raw_capture"), dict
        ) else None
        if attempt.get("observed_events") != [] or capture_events != []:
            problems.append(f"{label}: a recovered interruption captured notes")
    pins = (
        ("delivery_id", "delivery_id"),
        ("assignment_artifact_digest", "expected_assignment_artifact_digest"),
        ("assignment_behavior_digest", "expected_assignment_behavior_digest"),
    )
    for attempt_field, begin_field in pins:
        if attempt.get(attempt_field) != begin[begin_field]:
            problems.append(f"{label}: attempt {attempt_field} is not the request's")
    for field in ATTEMPT_PINS:
        if not isinstance(attempt.get(field), str) or not attempt[field].strip():
            problems.append(f"{label}: attempt {field} is missing")


def _outcome(item: dict[str, Any]) -> str | None:
    response = item["response"]
    if response is None:
        return None
    if "error" in response:
        return str(response["error"])
    status = response.get("status")
    return status if isinstance(status, str) else None


def _verify_sequences(problems: list[str], items: list[dict[str, Any]]) -> None:
    for scenario_id, expected in EXPECTED.items():
        recorded = [
            (
                item["source"],
                item["route"],
                item["sender"],
                item["page_outcome"],
                item["epoch"],
                item["status"],
                _outcome(item),
            )
            for item in items
            if item["scenario"] == scenario_id
        ]
        if recorded != expected:
            problems.append(f"{scenario_id}: recorded exchanges are not the witnessed sequence")


def _key(item: dict[str, Any]) -> Any:
    return item["request"].get("begin_request_id")


def _verify_keys(problems: list[str], items: list[dict[str, Any]]) -> None:
    keys_by_scenario: dict[str, set[Any]] = {}
    payload_by_key: dict[Any, Any] = {}
    for item in items:
        key = _key(item)
        keys_by_scenario.setdefault(item["scenario"], set()).add(key)
        payload = item["request"].get("begin")
        if key in payload_by_key and payload_by_key[key] != payload:
            problems.append(f"{item['label']}: the key was reused with another payload")
        payload_by_key.setdefault(key, payload)
    seen: dict[Any, str] = {}
    for scenario_id in SCENARIOS:
        keys = keys_by_scenario.get(scenario_id, set())
        if len(keys) != 1:
            problems.append(f"{scenario_id}: expected one begin request key")
            continue
        key = next(iter(keys))
        if key in seen:
            problems.append(f"{scenario_id}: reuses {seen[key]}'s begin request key")
        seen[key] = scenario_id


def _verify_identities(
    problems: list[str], items: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Every attempt document for one key is the same attempt. Return the interrupted ones."""

    first: dict[Any, dict[str, Any]] = {}
    interrupted: dict[str, dict[str, Any]] = {}
    owners: dict[Any, str] = {}
    for item in items:
        response = item["response"]
        attempt = response.get("attempt") if isinstance(response, dict) else None
        if not isinstance(attempt, dict):
            continue
        key = _key(item)
        if key in first:
            for field in ATTEMPT_PINS:
                if attempt.get(field) != first[key].get(field):
                    problems.append(f"{item['label']}: {field} is not the key's attempt")
        else:
            first[key] = attempt
            attempt_id = attempt.get("attempt_id")
            if attempt_id in owners:
                problems.append(f"{item['label']}: reuses {owners[attempt_id]}'s attempt")
            owners[attempt_id] = item["scenario"]
        if response is not None and response.get("status") == "INTERRUPTED":
            stored = interrupted.get(item["scenario"])
            if stored is not None and stored != attempt:
                problems.append(f"{item['label']}: a repeated recovery changed the stored result")
            interrupted.setdefault(item["scenario"], attempt)
    return interrupted


def _verify_restart(
    problems: list[str], items: list[dict[str, Any]], restart_seq: int | None
) -> None:
    w5 = [item for item in items if item["scenario"] == "W5"]
    aborted = [item for item in w5 if item["source"] == "aborted_begin"]
    replayed = [item for item in w5 if item["source"] == "replayed_begin"]
    if len(aborted) != 1 or len(replayed) != 1:
        return
    if aborted[0]["request_raw"] != replayed[0]["request_raw"]:
        problems.append("W5: the replayed begin is not the page's aborted bytes")
    if restart_seq is None:
        return
    for item in items:
        before = item["epoch"] == "A"
        if before and item["seq"] > restart_seq:
            problems.append(f"{item['label']}: epoch A answered after the restart")
        if not before and item["seq"] < restart_seq:
            problems.append(f"{item['label']}: epoch B answered before the restart")


def _verify_feedback(
    problems: list[str], scenarios: Any, interrupted: dict[str, dict[str, Any]]
) -> None:
    if not isinstance(scenarios, dict):
        problems.append("evidence: scenarios are missing")
        return
    for scenario_id in FEEDBACK_SCENARIOS:
        observed = scenarios.get(scenario_id)
        attempt = interrupted.get(scenario_id)
        if not isinstance(observed, dict) or observed.get("feedback_visible") is not True:
            problems.append(f"{scenario_id}: recovered interruption feedback was not visible")
            continue
        text = observed.get("feedback_text")
        if not isinstance(text, str) or "No evaluation was produced." not in text:
            problems.append(f"{scenario_id}: feedback does not disclaim evaluation")
            continue
        if "Matched:" in text:
            problems.append(f"{scenario_id}: interrupted feedback shows evaluation counts")
        attempt_id = attempt.get("attempt_id") if attempt is not None else None
        if not isinstance(attempt_id, str) or attempt_id not in text:
            problems.append(f"{scenario_id}: feedback does not show the recovered attempt")


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
    problems = verify_evidence(packet)
    for problem in problems:
        print(problem)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
