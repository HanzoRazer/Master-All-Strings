"""The bytes a delivery crosses the boundary as.

A receiver sees JSON, not a dataclass, so the serialized form is the contract.
Two things have to hold: the same delivery always produces the same bytes, and
the assignment that comes back out is the one that went in -- not an equivalent
lesson that happens to compare equal on the fields anyone thought to check.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from master_all_strings.education.assignment_delivery import LessonDeliveryEnvelopeV1
from master_all_strings.education.assignment_delivery_serialization import (
    delivery_to_dict,
    deserialize_delivery,
    envelope_for,
    serialize_delivery,
)
from master_all_strings.education.errors import EducationContractError
from master_all_strings.lesson.models import LessonAssignmentV1
from master_all_strings.lesson.serialization import (
    deserialize_lesson_assignment,
    serialize_lesson_assignment,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"


@pytest.fixture(scope="module")
def assignment() -> LessonAssignmentV1:
    return deserialize_lesson_assignment((EXAMPLES / "local_midi_basic.json").read_text("utf-8"))


@pytest.fixture
def envelope(assignment: LessonAssignmentV1) -> LessonDeliveryEnvelopeV1:
    return envelope_for(
        assignment,
        delivery_id="delivery-001",
        sender_ref="teacher-ana",
        recipient_ref="student-bo",
        classroom_ref="class-7b",
    )


def test_serialization_is_deterministic(envelope: LessonDeliveryEnvelopeV1) -> None:
    assert serialize_delivery(envelope) == serialize_delivery(envelope)


def test_a_delivery_survives_a_round_trip(envelope: LessonDeliveryEnvelopeV1) -> None:
    assert deserialize_delivery(serialize_delivery(envelope)) == envelope


def test_the_embedded_assignment_comes_back_exactly(
    envelope: LessonDeliveryEnvelopeV1, assignment: LessonAssignmentV1
) -> None:
    recovered = deserialize_delivery(serialize_delivery(envelope)).assignment
    assert recovered == assignment
    # Equality on the dataclass is one claim; identical serialized bytes is the
    # one a student's copy actually depends on.
    assert serialize_lesson_assignment(recovered) == serialize_lesson_assignment(assignment)


def test_the_assignment_is_embedded_as_an_object_not_a_string(
    envelope: LessonDeliveryEnvelopeV1,
) -> None:
    # A JSON string holding JSON would make the assignment opaque to every
    # reader that is not this module, schema validation included.
    payload = json.loads(serialize_delivery(envelope))
    assert isinstance(payload["assignment"], dict)
    assert payload["assignment"]["schema_id"] == "master_all_strings.lesson_assignment"


def test_the_shape_never_varies(envelope: LessonDeliveryEnvelopeV1) -> None:
    with_classroom = json.loads(serialize_delivery(envelope))
    without = json.loads(serialize_delivery(replace(envelope, classroom_ref=None)))
    assert list(with_classroom) == list(without)
    assert without["classroom_ref"] is None


def test_non_ascii_references_survive(assignment: LessonAssignmentV1) -> None:
    envelope = envelope_for(
        assignment,
        delivery_id="delivery-004",
        sender_ref="profesora-Ángela",
        recipient_ref="学生-01",
    )
    text = serialize_delivery(envelope)
    assert "Ángela" in text
    assert deserialize_delivery(text.encode("utf-8")) == envelope


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda d: d.update(extra="x"), "unknown delivery fields"),
        (lambda d: d.pop("recipient_ref"), "missing delivery fields"),
        (lambda d: d.update(schema_id="master_all_strings.other"), "unsupported schema_id"),
        (lambda d: d.update(schema_version="2.0.0"), "unsupported schema_version"),
        (lambda d: d.update(classroom_ref=7), "classroom_ref"),
        (lambda d: d.update(delivery_id=7), "delivery_id"),
    ],
)
def test_a_malformed_envelope_is_refused(
    envelope: LessonDeliveryEnvelopeV1, mutate: object, match: str
) -> None:
    data = delivery_to_dict(envelope)
    mutate(data)  # type: ignore[operator]
    with pytest.raises(EducationContractError, match=match):
        deserialize_delivery(data)


def test_an_unknown_schema_is_refused_before_the_rest_is_read(
    envelope: LessonDeliveryEnvelopeV1,
) -> None:
    # A future envelope must not be half-understood by today's reader: the
    # version is checked before any other field is looked at, so a payload
    # that is otherwise nonsense still fails on the version.
    data = delivery_to_dict(envelope)
    data["schema_version"] = "9.9.9"
    data["assignment"] = "not an assignment at all"
    with pytest.raises(EducationContractError, match="unsupported schema_version"):
        deserialize_delivery(data)


def test_a_malformed_assignment_is_refused_by_the_lesson_package(
    envelope: LessonDeliveryEnvelopeV1,
) -> None:
    # Delivery does not parse lessons. It hands the payload to the contract
    # that owns them and lets that failure through.
    data = delivery_to_dict(envelope)
    data["assignment"] = {"schema_id": "master_all_strings.lesson_assignment", "nonsense": True}
    with pytest.raises(Exception, match="schema_version|malformed|unsupported|required"):
        deserialize_delivery(data)


def test_bytes_that_are_not_utf8_are_refused_as_a_delivery(
    envelope: LessonDeliveryEnvelopeV1,
) -> None:
    # Named where the decoding happens, not caught by something further out:
    # invalid bytes are a malformed delivery, the same family of failure as
    # malformed JSON, and a caller should be told so rather than meeting a
    # UnicodeDecodeError from inside the boundary.
    text = serialize_delivery(envelope).encode("utf-8")
    with pytest.raises(EducationContractError, match="malformed UTF-8"):
        deserialize_delivery(b"\xff\xfe" + text)
    with pytest.raises(EducationContractError, match="malformed UTF-8"):
        deserialize_delivery("teacher-Ángela".encode("latin-1"))


def test_malformed_json_is_refused(envelope: LessonDeliveryEnvelopeV1) -> None:
    with pytest.raises(EducationContractError, match="malformed JSON"):
        deserialize_delivery("{not json")
    with pytest.raises(EducationContractError, match="must be an object"):
        deserialize_delivery("[]")
