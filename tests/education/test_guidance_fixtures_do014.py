"""DO-014 golden teaching-guidance fixtures: schema, drift, semantics."""

from __future__ import annotations

import functools
import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator

from master_all_strings.education.guidance_builder import build_teaching_guidance_projection
from master_all_strings.education.serialization import to_dict

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "resources" / "education" / "examples" / "guidance"
SCHEMA_DIR = REPO / "resources" / "education" / "schema"
SCHEMA = SCHEMA_DIR / "teaching_guidance_projection_v1.schema.json"
GENERATOR = REPO / "scripts" / "build_guidance_fixtures.py"

FIXTURE_STEMS = (
    "single_finding_guidance",
    "multiple_finding_guidance",
    "isolate_passage_guidance",
    "slow_down_guidance",
    "continue_guidance",
    "unrenderable_event_guidance",
)


@functools.lru_cache(maxsize=1)
def _generator():
    name = "build_guidance_fixtures"
    spec = importlib.util.spec_from_file_location(name, GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _fixture(stem: str) -> dict:
    return json.loads((EXAMPLES / f"{stem}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("stem", FIXTURE_STEMS)
def test_every_required_fixture_exists(stem: str) -> None:
    assert (EXAMPLES / f"{stem}.json").is_file()


@pytest.mark.parametrize("stem", FIXTURE_STEMS)
def test_fixture_validates_against_schema(stem: str) -> None:
    Draft202012Validator.check_schema(_schema())
    jsonschema.validate(_fixture(stem), _schema())


def test_fixtures_have_no_drift() -> None:
    assert _generator().check_fixtures() == 0


def test_single_finding_cites_the_canonical_event() -> None:
    payload = _fixture("single_finding_guidance")
    assert payload["items"][0]["canonical_event_id"] == "ev-2"
    assert payload["items"][0]["finding_id"] == "timing-late-0001"


def test_multiple_findings_keep_both_identities() -> None:
    payload = _fixture("multiple_finding_guidance")
    finding_ids = [item["finding_id"] for item in payload["items"]]
    events = [item["canonical_event_id"] for item in payload["items"]]
    assert finding_ids == ["pitch-0001", "timing-late-0001"]
    assert events == ["ev-3", "ev-1"]


def test_isolate_preserves_the_educational_range() -> None:
    action = _fixture("isolate_passage_guidance")["next_action"]
    assert action["action_type"] == "isolate_passage"
    assert action["focus_start_tick"] == 960
    assert action["focus_end_tick"] == 1920


def test_slow_down_is_advisory_in_the_fixture() -> None:
    payload = _fixture("slow_down_guidance")
    assert payload["next_action"]["action_type"] == "slow_down"
    assert payload["next_action"]["target_rate"] == 0.75
    assert "playback_rate" not in payload


def test_continue_is_not_mastery() -> None:
    payload = _fixture("continue_guidance")
    assert payload["next_action"]["action_type"] == "continue"
    blob = json.dumps(payload).lower()
    for token in ("mastered", "perfect", "complete", "passed curriculum"):
        assert token not in blob


def test_unrenderable_event_is_not_moved() -> None:
    payload = _fixture("unrenderable_event_guidance")
    assert payload["items"][0]["canonical_event_id"] == "ev-ghost"
    assert payload["canonical_revision_id"] == "rev-b85e77022251b045cfe38b7d"


def test_builder_round_trip_matches_committed_single_fixture() -> None:
    generator = _generator()
    evaluation = generator._cases()["single_finding_guidance"]
    projection = build_teaching_guidance_projection(
        evaluation, canonical_revision_id=generator.REVISION
    )
    assert to_dict(projection) == _fixture("single_finding_guidance")
