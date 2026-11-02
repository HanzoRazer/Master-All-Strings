"""The keyed Begin wrapper cites the existing attempt shapes and adds none."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from tests.mvp.test_received_lesson_begin_request_do016 import KEY, _gateway

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = (
    REPO_ROOT / "resources" / "mvp2" / "schema" / "received_lesson_begin_request_v1.schema.json"
)
ATTEMPT = (
    REPO_ROOT / "resources" / "mvp2" / "schema" / "received_lesson_attempt_v1.schema.json"
)


def _validator() -> Draft202012Validator:
    registry = Registry()
    for path in (ATTEMPT, SCHEMA):
        schema = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    # Nested attempt documents cite the same schemas the attempt contract does.
    from tests.mvp.test_received_lesson_attempt_schema_do016 import NESTED, _load

    for path in NESTED:
        schema = _load(path)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")), registry=registry)


def test_started_and_interrupted_wrappers_match_the_schema() -> None:
    gateway, payload = _gateway()
    _status, started = gateway.begin(KEY, payload)
    validator = _validator()
    validator.validate(started)
    _code, interrupted = gateway.recover(KEY, payload)
    validator.validate(interrupted)
    pending: dict[str, Any] = {
        "schema_id": "master_all_strings.received_lesson_begin_request",
        "schema_version": "1.0.0",
        "begin_request_id": KEY,
        "status": "PENDING",
        "attempt": None,
    }
    validator.validate(pending)
    extra = dict(started)
    extra["evaluation"] = {}
    errors = list(validator.iter_errors(extra))
    assert errors
