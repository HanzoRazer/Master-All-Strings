"""JSON Schema and Python contract agreement for lesson deliveries.

The dataclass and the schema are two independent descriptions of one boundary,
and two descriptions only earn their keep if they agree: whatever the Python
contract accepts must validate, and whatever it refuses must fail validation
too. A schema that quietly permits what the code rejects is worse than none --
it tells an outside integrator the wrong thing.

Cross-file ``$ref`` resolution uses a registry holding the frozen lesson
assignment schema. That is local test wiring: the delivery schema references
the assignment schema by its canonical ``$id`` rather than copying its fields,
so the assignment contract stays the single definition of what a lesson is.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from master_all_strings.education.assignment_delivery import LessonDeliveryEnvelopeV1
from master_all_strings.education.assignment_delivery_serialization import (
    delivery_to_dict,
    envelope_for,
)
from master_all_strings.lesson.models import LessonAssignmentV1
from master_all_strings.lesson.serialization import deserialize_lesson_assignment

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = REPO_ROOT / "resources"
DELIVERY_SCHEMA = SCHEMAS / "education" / "schema" / "lesson_delivery_v1.schema.json"
ASSIGNMENT_SCHEMA = SCHEMAS / "lesson" / "schema" / "lesson_assignment_v1.schema.json"
LESSON_EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"
DELIVERY_FIXTURES = REPO_ROOT / "resources" / "education" / "examples" / "lesson_deliveries"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    assignment = _load(ASSIGNMENT_SCHEMA)
    registry = Registry().with_resource(
        assignment["$id"], Resource.from_contents(assignment)
    )
    return Draft202012Validator(_load(DELIVERY_SCHEMA), registry=registry)


@pytest.fixture(scope="module")
def assignment() -> LessonAssignmentV1:
    return deserialize_lesson_assignment(
        (LESSON_EXAMPLES / "local_midi_basic.json").read_text("utf-8")
    )


@pytest.fixture
def envelope(assignment: LessonAssignmentV1) -> LessonDeliveryEnvelopeV1:
    return envelope_for(
        assignment,
        delivery_id="delivery-001",
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
        classroom_ref="class-7b",
    )


def test_the_schema_is_itself_valid(validator: Draft202012Validator) -> None:
    Draft202012Validator.check_schema(_load(DELIVERY_SCHEMA))


def test_the_schema_references_the_assignment_rather_than_restating_it() -> None:
    # If the delivery schema ever grows its own copy of the assignment's
    # fields, the two definitions start drifting and the frozen one stops
    # being authoritative.
    schema = _load(DELIVERY_SCHEMA)
    assert schema["properties"]["assignment"] == {
        "$ref": _load(ASSIGNMENT_SCHEMA)["$id"],
        "description": schema["properties"]["assignment"]["description"],
    }


def test_what_the_contract_builds_validates(
    validator: Draft202012Validator, envelope: LessonDeliveryEnvelopeV1
) -> None:
    validator.validate(delivery_to_dict(envelope))


def test_a_null_classroom_validates(
    validator: Draft202012Validator, envelope: LessonDeliveryEnvelopeV1
) -> None:
    validator.validate(delivery_to_dict(replace(envelope, classroom_ref=None)))


@pytest.mark.parametrize("name", sorted(p.name for p in DELIVERY_FIXTURES.glob("*.json")))
def test_every_golden_delivery_validates(validator: Draft202012Validator, name: str) -> None:
    validator.validate(_load(DELIVERY_FIXTURES / name))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(extra="x"),
        lambda d: d.pop("classroom_ref"),
        lambda d: d.pop("assignment"),
        lambda d: d.update(schema_id="master_all_strings.other"),
        lambda d: d.update(schema_version="2.0.0"),
        lambda d: d.update(delivery_id=""),
        lambda d: d.update(sender_ref="  padded  "),
        lambda d: d.update(recipient_ref=None),
        lambda d: d.update(assignment_artifact_digest="not-a-digest"),
        lambda d: d.update(assignment_behavior_digest="sha256:short"),
        lambda d: d.update(assignment="an encoded string, not an object"),
    ],
)
def test_the_schema_refuses_what_the_contract_refuses(
    validator: Draft202012Validator, envelope: LessonDeliveryEnvelopeV1, mutate: object
) -> None:
    data = delivery_to_dict(envelope)
    mutate(data)  # type: ignore[operator]
    assert not validator.is_valid(data)


def test_the_schema_reaches_into_the_embedded_assignment(
    validator: Draft202012Validator, envelope: LessonDeliveryEnvelopeV1
) -> None:
    # The $ref has to actually resolve. If it silently did not, a corrupt
    # assignment would validate and this suite would prove nothing.
    data = delivery_to_dict(envelope)
    data["assignment"]["schema_version"] = "2.0.0"
    assert not validator.is_valid(data)
