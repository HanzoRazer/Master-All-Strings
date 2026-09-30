"""The preparation document is closed, and its nested artifacts stay theirs.

The schema composes the fretboard, playback, practice, and score-projection
contracts instead of restating them. A field added to the preparation, or a
nested artifact that no longer matches its own schema, fails here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

from master_all_strings.education.assignment_delivery_preview import LessonDeliveryPreviewService
from master_all_strings.education.assignment_delivery_serialization import envelope_for
from master_all_strings.education.assignment_delivery_service import LessonDeliveryService
from master_all_strings.education.local_practice_choice import LocalPracticeChoiceService
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.local_practice_preparation import (
    LOCAL_PRACTICE_PREPARATION_SCHEMA_ID,
    LOCAL_PRACTICE_PREPARATION_SCHEMA_VERSION,
    PREPARATION_STATUS_PREPARED,
    LocalPracticePreparationService,
    preparation_to_dict,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / "resources" / "mvp2" / "schema" / "local_practice_preparation_v1.schema.json"
NESTED = (
    REPO_ROOT / "resources" / "mvp1" / "schema" / "fretboard_scroll_projection_v1.schema.json",
    REPO_ROOT / "resources" / "mvp2" / "schema" / "lesson_playback_plan_v1.schema.json",
    REPO_ROOT / "resources" / "mvp2" / "schema" / "practice_session_policy_v1.schema.json",
    REPO_ROOT / "resources" / "projections" / "schema" / "projection_result_v1.schema.json",
    REPO_ROOT / "resources" / "projections" / "schema" / "tab_projection_v1.schema.json",
    REPO_ROOT / "resources" / "projections" / "schema" / "notation_projection_v1.schema.json",
    REPO_ROOT
    / "resources"
    / "projections"
    / "schema"
    / "projection_unsupported_feature_v1.schema.json",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    registry = Registry()
    for path in NESTED:
        schema = _load(path)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(_load(SCHEMA), registry=registry)


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    assignment = deserialize_lesson_assignment(
        (
            REPO_ROOT / "resources" / "lesson" / "examples" / "instruction_future_fields.json"
        ).read_text(encoding="utf-8")
    )
    deliveries = LessonDeliveryService()
    choices = LocalPracticeChoiceService(LessonDeliveryPreviewService(deliveries))
    envelope = deliveries.receive(
        envelope_for(
            assignment,
            delivery_id="delivery-001",
            sender_ref="teacher-ana",
            recipient_ref="student-bo",
        )
    )
    choices.choose(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )
    prepared = LocalPracticePreparationService(deliveries, choices, MvpApplication())
    return preparation_to_dict(
        prepared.prepare(
            envelope.delivery_id,
            envelope.assignment_artifact_digest,
            envelope.assignment_behavior_digest,
        )
    )


def test_the_schema_is_itself_valid() -> None:
    Draft202012Validator.check_schema(_load(SCHEMA))


def test_a_prepared_bundle_matches_the_closed_schema(
    validator: Draft202012Validator, document: dict[str, Any]
) -> None:
    validator.validate(document)
    assert document["schema_id"] == LOCAL_PRACTICE_PREPARATION_SCHEMA_ID
    assert document["schema_version"] == LOCAL_PRACTICE_PREPARATION_SCHEMA_VERSION
    assert document["preparation_status"] == PREPARATION_STATUS_PREPARED
    assert document["projection"]["demo_id"] is None
    assert set(document["score"]) == {"canonical_revision", "tab", "notation"}
    assert document["score"]["tab"]["projection_kind"] == "tab"
    assert document["score"]["notation"]["projection_kind"] == "notation"
    assert (
        document["score"]["tab"]["canonical_revision_id"]
        == document["score"]["canonical_revision"]["revision_id"]
    )
    assert (
        document["score"]["notation"]["payload"]["canonical_revision_id"]
        == document["score"]["canonical_revision"]["revision_id"]
    )


@pytest.mark.parametrize(
    "field_name",
    [
        "schema_id",
        "schema_version",
        "preparation_status",
        "delivery_id",
        "assignment_id",
        "content_id",
        "assignment_artifact_digest",
        "assignment_behavior_digest",
        "projection",
        "playback",
        "practice",
        "score",
    ],
)
def test_every_top_level_field_is_required(
    validator: Draft202012Validator, document: dict[str, Any], field_name: str
) -> None:
    broken = dict(document)
    del broken[field_name]
    with pytest.raises(ValidationError, match="required"):
        validator.validate(broken)


def test_an_extra_top_level_field_is_rejected(
    validator: Draft202012Validator, document: dict[str, Any]
) -> None:
    broken = dict(document)
    broken["accepted"] = True
    with pytest.raises(ValidationError, match="Additional properties"):
        validator.validate(broken)


def test_score_is_closed_and_status_is_fixed(
    validator: Draft202012Validator, document: dict[str, Any]
) -> None:
    extra_score = dict(document)
    extra_score["score"] = dict(document["score"])
    extra_score["score"]["history"] = []
    with pytest.raises(ValidationError, match="Additional properties"):
        validator.validate(extra_score)
    missing = dict(document)
    missing["score"] = {"canonical_revision": document["score"]["canonical_revision"]}
    with pytest.raises(ValidationError, match="required"):
        validator.validate(missing)
    wrong = dict(document)
    wrong["preparation_status"] = "STARTED"
    with pytest.raises(ValidationError):
        validator.validate(wrong)
    wrong_schema = dict(document)
    wrong_schema["schema_version"] = "1.1.0"
    with pytest.raises(ValidationError):
        validator.validate(wrong_schema)


def test_a_demo_id_and_a_mistyped_score_are_rejected(
    validator: Draft202012Validator, document: dict[str, Any]
) -> None:
    demo = dict(document)
    demo["projection"] = dict(document["projection"])
    demo["projection"]["demo_id"] = "ascending_scale"
    with pytest.raises(ValidationError):
        validator.validate(demo)
    swapped = dict(document)
    swapped["score"] = dict(document["score"])
    swapped["score"]["tab"] = document["score"]["notation"]
    with pytest.raises(ValidationError):
        validator.validate(swapped)
