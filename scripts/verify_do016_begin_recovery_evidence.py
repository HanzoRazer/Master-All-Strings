"""Offline checks for the keyed Begin recovery witness."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BEGIN_REQUEST_SCHEMA_ID = "master_all_strings.received_lesson_begin_request"
BEGIN_REQUEST_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def verify_evidence(packet: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not isinstance(packet, dict):
        return ["evidence: packet is not an object"]
    if packet.get("schema") != "master_all_strings.do016_begin_recovery_evidence":
        problems.append("evidence: schema is not the begin recovery packet")
    # bool is an int subclass and 0.0 == 0; only the integer zero is a clean run.
    failures = packet.get("failures")
    if packet.get("complete") is not True or type(failures) is not int or failures != 0:
        problems.append("evidence: the run is incomplete")
    scenarios = packet.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios.get("W1", {}).get("interrupted"):
        problems.append("W1: the stored begin was not interrupted")
    exchanges = packet.get("exchanges")
    if not isinstance(exchanges, list):
        problems.append("evidence: exchanges are missing")
        return problems
    for item in exchanges:
        problem = _wrapper_problem(item)
        if problem is not None:
            problems.append(f"{item.get('scenario')}: {item.get('source')} {problem}")
    forwarded = [
        item for item in exchanges
        if isinstance(item, dict)
        and item.get("scenario") == "W1"
        and item.get("source") == "forwarded_server"
    ]
    if len(forwarded) != 1 or forwarded[0].get("status") != 201:
        problems.append("W1: the live begin was not stored")
    elif forwarded[0].get("response", {}).get("status") != "STARTED":
        problems.append("W1: the stored begin was not started")
    early = _one(exchanges, "W2", "recovery_before_begin")
    if early is None or early.get("response", {}).get("status") != "NO_ATTEMPT":
        problems.append("W2: recovery did not seal the key before begin")
    during = _one(exchanges, "W3", "recovery_during_prepare")
    if during is None or during.get("response", {}).get("status") != "PENDING":
        problems.append("W3: recovery did not see a blocked preparation")
    hidden = _one(exchanges, "W4", "forwarded_recovery")
    if hidden is None or hidden.get("response", {}).get("status") != "INTERRUPTED":
        problems.append("W4: the hidden recovery was not a stored interruption")
    replay = _one(exchanges, "W5", "replayed_begin")
    if replay is None or replay.get("status") != 409:
        problems.append("W5: the restarted server did not refuse the delayed begin")
    elif replay.get("response", {}).get("error") != "begin_request_closed":
        problems.append("W5: the delayed begin was not closed")
    return problems


def _wrapper_problem(item: Any) -> str | None:
    """A gateway answer counts only as a wrapper for the key its request sent."""

    if not isinstance(item, dict):
        return "exchange is not an object"
    response = item.get("response")
    if not isinstance(response, dict) or "error" in response:
        return None
    request = item.get("request")
    if response.get("schema_id") != BEGIN_REQUEST_SCHEMA_ID:
        return "response is not a begin request wrapper"
    if response.get("schema_version") != "1.0.0":
        return "wrapper schema version is not 1.0.0"
    key = response.get("begin_request_id")
    if not isinstance(key, str) or BEGIN_REQUEST_ID.fullmatch(key) is None:
        return "wrapper key is not a lowercase uuid v4"
    if not isinstance(request, dict) or request.get("begin_request_id") != key:
        return "wrapper key is not the recorded request's key"
    return None


def _one(exchanges: list[Any], scenario: str, source: str) -> dict[str, Any] | None:
    found = [
        item for item in exchanges
        if isinstance(item, dict)
        and item.get("scenario") == scenario
        and item.get("source") == source
    ]
    if len(found) != 1:
        return None
    return found[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    packet = json.loads(args.evidence.read_text(encoding="utf-8"))
    problems = verify_evidence(packet)
    for problem in problems:
        print(problem)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
