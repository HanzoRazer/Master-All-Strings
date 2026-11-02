"""Strict checks for the begin-recovery packet do not trust a pass flag."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
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


def _key(index: int) -> str:
    return f"{index:08x}-0000-4000-8000-00000000abcd"


def _exchange(scenario: str, source: str, status: int, index: int, response: dict) -> dict:
    key = _key(index)
    if "error" not in response:
        response = {
            "schema_id": "master_all_strings.received_lesson_begin_request",
            "schema_version": "1.0.0",
            "begin_request_id": key,
            **response,
        }
    return {
        "scenario": scenario,
        "source": source,
        "status": status,
        "request": {"begin_request_id": key, "begin": {"delivery_id": "delivery-stage9"}},
        "response": response,
    }


def _packet() -> dict:
    attempt = {"attempt_id": "attempt-1"}
    return {
        "schema": "master_all_strings.do016_begin_recovery_evidence",
        "complete": True,
        "failures": 0,
        "scenarios": {"W1": {"interrupted": True}},
        "exchanges": [
            _exchange("W1", "forwarded_server", 201, 1,
                {"status": "STARTED", "attempt": attempt}),
            _exchange("W2", "recovery_before_begin", 200, 2,
                {"status": "NO_ATTEMPT", "attempt": None}),
            _exchange("W3", "recovery_during_prepare", 202, 3,
                {"status": "PENDING", "attempt": None}),
            _exchange("W4", "forwarded_recovery", 200, 4,
                {"status": "INTERRUPTED", "attempt": attempt}),
            _exchange("W5", "replayed_begin", 409, 5, {"error": "begin_request_closed"}),
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


def test_the_retained_packet_passes(verifier: ModuleType) -> None:
    path = REPO_ROOT / "docs/mvp2/do016_begin_recovery_artifacts/evidence.json"
    packet = json.loads(path.read_text(encoding="utf-8"))
    assert verifier.verify_evidence(packet) == []


@pytest.mark.parametrize(
    ("change", "diagnostic"),
    [
        (lambda item: item["response"].update(begin_request_id=_key(99)),
            "not the recorded request's key"),
        (lambda item: item["request"].update(begin_request_id=_key(99)),
            "not the recorded request's key"),
        (lambda item: item["response"].update(begin_request_id=_key(1).upper()),
            "not a lowercase uuid v4"),
        (lambda item: item["response"].update(schema_version="2.0.0"),
            "schema version is not 1.0.0"),
        (lambda item: item["response"].pop("schema_id"), "not a begin request wrapper"),
    ],
)
def test_a_wrapper_for_another_key_fails(
    verifier: ModuleType, change: Callable[[dict], object], diagnostic: str
) -> None:
    packet = _packet()
    change(packet["exchanges"][3])
    problems = verifier.verify_evidence(packet)
    assert any(item.startswith("W4: ") and diagnostic in item for item in problems)


@pytest.mark.parametrize("loose_zero", [False, 0.0, "0", None])
def test_only_integer_zero_failures_pass(verifier: ModuleType, loose_zero: object) -> None:
    packet = _packet()
    packet["failures"] = loose_zero
    assert verifier.verify_evidence(packet) == ["evidence: the run is incomplete"]
