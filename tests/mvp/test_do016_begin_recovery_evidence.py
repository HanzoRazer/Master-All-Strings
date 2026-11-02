"""Strict checks for the begin-recovery packet do not trust a pass flag."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER = REPO_ROOT / "scripts" / "verify_do016_begin_recovery_evidence.py"


@pytest.fixture(scope="module")
def verifier() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_do016_begin_recovery_evidence", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _packet() -> dict:
    attempt = {"attempt_id": "attempt-1"}
    return {
        "schema": "master_all_strings.do016_begin_recovery_evidence",
        "complete": True,
        "failures": 0,
        "scenarios": {"W1": {"interrupted": True}},
        "exchanges": [
            {
                "scenario": "W1",
                "source": "forwarded_server",
                "status": 201,
                "response": {"status": "STARTED", "attempt": attempt},
            },
            {
                "scenario": "W2",
                "source": "recovery_before_begin",
                "status": 200,
                "response": {"status": "NO_ATTEMPT", "attempt": None},
            },
            {
                "scenario": "W3",
                "source": "recovery_during_prepare",
                "status": 202,
                "response": {"status": "PENDING", "attempt": None},
            },
            {
                "scenario": "W4",
                "source": "forwarded_recovery",
                "status": 200,
                "response": {"status": "INTERRUPTED", "attempt": attempt},
            },
            {
                "scenario": "W5",
                "source": "replayed_begin",
                "status": 409,
                "response": {"error": "begin_request_closed"},
            },
        ],
    }


def test_a_consistent_packet_passes(verifier: ModuleType) -> None:
    assert verifier.verify_evidence(_packet()) == []


def test_a_rehashed_closed_begin_still_fails(verifier: ModuleType) -> None:
    packet = _packet()
    packet["exchanges"][-1]["response"] = {"error": "begin_request_conflict"}
    packet["exchanges"][-1]["status"] = 409
    problems = verifier.verify_evidence(packet)
    assert any("delayed begin" in item for item in problems)
