"""Closed attempt documents, including the nested contracts they cite."""

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
from master_all_strings.education.local_practice_choice_repository import (
    InMemoryLocalPracticeChoiceRepository,
)
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.mvp.received_lesson_attempt import ReceivedLessonAttemptService

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / "resources" / "mvp2" / "schema" / "received_lesson_attempt_v1.schema.json"
NESTED = (
    REPO_ROOT / "resources" / "mvp2" / "schema" / "local_practice_preparation_v1.schema.json",
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
    REPO_ROOT / "resources" / "performance" / "schema" / "raw_performance_capture_v1.schema.json",
    REPO_ROOT / "resources" / "performance" / "schema" / "observed_midi_note_v1.schema.json",
    REPO_ROOT / "resources" / "education" / "schema" / "practice_evaluation_result_v1.schema.json",
    REPO_ROOT
    / "resources"
    / "education"
    / "schema"
    / "teaching_guidance_projection_v1.schema.json",
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
def documents() -> dict[str, dict[str, Any]]:
    assignment = deserialize_lesson_assignment(
        (REPO_ROOT / "resources" / "lesson" / "examples" / "local_midi_basic.json").read_text(
            "utf-8"
        )
    )
    deliveries = LessonDeliveryService()
    choices = InMemoryLocalPracticeChoiceRepository()
    envelope = envelope_for(
        assignment,
        delivery_id="delivery-001",
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
    )
    deliveries.receive(envelope)
    LocalPracticeChoiceService(LessonDeliveryPreviewService(deliveries), choices).choose(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
    )
    service = ReceivedLessonAttemptService(
        deliveries, choices, now_utc=lambda: "2026-10-02T19:42:00Z"
    )
    begun = service.begin(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
        "keyboard-a",
        1_000,
    )
    event = begun["preparation"]["playback"]["events"][0]
    accepted = service.append_message(
        begun["attempt_id"], 0, 2_000, event["onset_seconds"], [0x90, event["midi_note"], 80]
    )
    cancelled = service.cancel(begun["attempt_id"], 2_100)
    other = service.begin(
        envelope.delivery_id,
        envelope.assignment_artifact_digest,
        envelope.assignment_behavior_digest,
        "keyboard-a",
        1_000,
    )
    evaluated = service.finish(other["attempt_id"], 2_000)
    return {
        "begin": begun,
        "message": accepted,
        "interrupted": cancelled,
        "evaluated": evaluated,
    }


def test_the_schema_is_itself_valid() -> None:
    Draft202012Validator.check_schema(_load(SCHEMA))


@pytest.mark.parametrize("kind", ["begin", "message", "interrupted", "evaluated"])
def test_each_response_shape_matches(
    validator: Draft202012Validator, documents: dict[str, dict[str, Any]], kind: str
) -> None:
    validator.validate(documents[kind])


def test_an_extra_field_and_a_missing_field_fail(
    validator: Draft202012Validator, documents: dict[str, dict[str, Any]]
) -> None:
    extra = dict(documents["message"])
    extra["preparation"] = documents["begin"]["preparation"]
    with pytest.raises(ValidationError):
        validator.validate(extra)
    missing = dict(documents["evaluated"])
    del missing["guidance"]
    with pytest.raises(ValidationError):
        validator.validate(missing)
