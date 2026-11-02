"""Offline checks for the keyed Begin recovery witness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def verify_evidence(packet: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not isinstance(packet, dict):
        return ["evidence: packet is not an object"]
    if packet.get("schema") != "master_all_strings.do016_begin_recovery_evidence":
        problems.append("evidence: schema is not the begin recovery packet")
    if packet.get("complete") is not True or packet.get("failures") not in (0,):
        problems.append("evidence: the run is incomplete")
    scenarios = packet.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios.get("W1", {}).get("interrupted"):
        problems.append("W1: the stored begin was not interrupted")
    exchanges = packet.get("exchanges")
    if not isinstance(exchanges, list):
        problems.append("evidence: exchanges are missing")
        return problems
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
