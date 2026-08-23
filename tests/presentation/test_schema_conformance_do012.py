"""JSON Schema and Python validator agreement for DO-012 presentation fixtures.

Two independent descriptions of the same contract only earn their keep if they
agree. Every valid fixture must pass both the schema and the dataclass; every
invalid fixture must be refused by at least one of them, and the fixtures are
authored so the *reason* is the same in both.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from master_all_strings.presentation.contracts import (
    MediaTimelineBindingV1,
    SynchronizationHealthV1,
    TeachingPlayheadStateV1,
    TeachingTimelineStateV1,
    TimelineAnchorV1,
)
from master_all_strings.presentation.errors import PresentationContractError
from master_all_strings.presentation.serialization import from_dict, to_dict

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "resources" / "presentation" / "schema"
EXAMPLES = REPO_ROOT / "resources" / "presentation" / "examples"
INVALID = EXAMPLES / "invalid"

# Fixture stem prefix -> (schema file, contract class). Anchors are arrays of
# records rather than a single record, so they are handled separately.
_ROUTES: tuple[tuple[str, str, type], ...] = (
    ("timeline_state_", "teaching_timeline_state_v1", TeachingTimelineStateV1),
    ("bounded_loop", "teaching_timeline_state_v1", TeachingTimelineStateV1),
    ("playhead_", "teaching_playhead_state_v1", TeachingPlayheadStateV1),
    ("health_", "synchronization_health_v1", SynchronizationHealthV1),
    ("binding_", "media_timeline_binding_v1", MediaTimelineBindingV1),
    ("zero_offset_binding", "media_timeline_binding_v1", MediaTimelineBindingV1),
    ("offset_binding", "media_timeline_binding_v1", MediaTimelineBindingV1),
    ("detached_media", "media_timeline_binding_v1", MediaTimelineBindingV1),
    ("partial_range_binding", "media_timeline_binding_v1", MediaTimelineBindingV1),
    ("full_range_binding", "media_timeline_binding_v1", MediaTimelineBindingV1),
)


def _route(path: Path) -> tuple[str, type]:
    for prefix, schema_name, contract in _ROUTES:
        if path.stem.startswith(prefix):
            return schema_name, contract
    raise AssertionError(f"no schema route for fixture {path.name}")


def _validator(schema_name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / f"{schema_name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


# Not single contract records: anchor tables are arrays, and the interpolation
# vectors are a cross-language test asset with their own suite.
_NON_RECORD_STEMS = ("timeline_anchors_", "interpolation_vectors")


def _valid_record_fixtures() -> list[Path]:
    return sorted(
        path
        for path in EXAMPLES.glob("*.json")
        if not path.stem.startswith(_NON_RECORD_STEMS)
    )


def _anchor_fixtures() -> list[Path]:
    return sorted(EXAMPLES.glob("timeline_anchors_*.json"))


def _invalid_fixtures() -> list[Path]:
    return sorted(INVALID.glob("*.json"))


def test_every_schema_is_itself_valid() -> None:
    schemas = sorted(SCHEMA_DIR.glob("*.schema.json"))
    assert schemas, "presentation schemas are missing"
    for path in schemas:
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_fixture_set_is_not_empty() -> None:
    assert _valid_record_fixtures()
    assert _anchor_fixtures()
    assert _invalid_fixtures()


@pytest.mark.parametrize("path", _valid_record_fixtures(), ids=lambda p: p.stem)
def test_valid_fixture_passes_schema_and_contract(path: Path) -> None:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    schema_name, contract = _route(path)
    _validator(schema_name).validate(payload)
    record = from_dict(contract, payload)
    assert to_dict(record) == payload


@pytest.mark.parametrize("path", _anchor_fixtures(), ids=lambda p: p.stem)
def test_anchor_fixture_passes_schema_and_contract(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, list) and payload
    validator = _validator("timeline_anchor_v1")
    for entry in payload:
        validator.validate(entry)
        anchor = from_dict(TimelineAnchorV1, entry)
        assert to_dict(anchor) == entry


@pytest.mark.parametrize("path", _invalid_fixtures(), ids=lambda p: p.stem)
def test_invalid_fixture_is_refused(path: Path) -> None:
    """Refusal must come from the contract, the schema, or both -- never neither."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_name, contract = _route(path)

    schema_ok = _validator(schema_name).is_valid(payload)
    try:
        from_dict(contract, payload)
    except (PresentationContractError, ValueError):
        contract_ok = False
    else:
        contract_ok = True

    assert not (schema_ok and contract_ok), (
        f"{path.name} was accepted by both the schema and the contract"
    )


def test_partial_range_golden_binding_matches_the_bundled_asset() -> None:
    """The golden clip is 3.0 s against a 4.5 s lesson, and the binding says so."""

    payload = json.loads((EXAMPLES / "partial_range_binding.json").read_text(encoding="utf-8"))
    binding = from_dict(MediaTimelineBindingV1, payload)
    assert binding.lesson_end_seconds == 3.0
    assert binding.media_end_seconds == 3.0
    assert binding.media_id == "half-steps-demo-video"


def test_full_range_binding_exercises_the_non_degraded_path() -> None:
    payload = json.loads((EXAMPLES / "full_range_binding.json").read_text(encoding="utf-8"))
    binding = from_dict(MediaTimelineBindingV1, payload)
    assert binding.lesson_end_seconds == binding.media_end_seconds
