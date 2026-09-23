"""Deterministic JSON for lesson deliveries.

The envelope crosses an application boundary as bytes, so the bytes are the
contract a receiver sees. Two serializations of one delivery are identical, and
a reload returns the same assignment object the sender held -- not an
equivalent one.

The assignment inside is parsed by `lesson.serialization`, never here. A second
parser for `LessonAssignmentV1` would be a second definition of what a lesson
is, and the two would drift.
"""

from __future__ import annotations

import json
from typing import Any

from master_all_strings.education.assignment_delivery import (
    LESSON_DELIVERY_SCHEMA_ID,
    LESSON_DELIVERY_SCHEMA_VERSION,
    LessonDeliveryEnvelopeV1,
)
from master_all_strings.education.errors import EducationContractError
from master_all_strings.lesson.serialization import (
    compute_assignment_artifact_digest,
    compute_lesson_behavior_digest,
    deserialize_lesson_assignment,
)
from master_all_strings.lesson.serialization import (
    to_dict as assignment_to_dict,
)

__all__ = [
    "delivery_from_mapping",
    "delivery_to_dict",
    "deserialize_delivery",
    "envelope_for",
    "serialize_delivery",
]

_FIELDS = (
    "schema_id",
    "schema_version",
    "delivery_id",
    "sender_ref",
    "recipient_ref",
    "classroom_ref",
    "assignment_artifact_digest",
    "assignment_behavior_digest",
    "assignment",
)


def delivery_to_dict(envelope: LessonDeliveryEnvelopeV1) -> dict[str, Any]:
    """Plain data, in a fixed key order, with every key present.

    ``classroom_ref`` is written as ``null`` rather than omitted: a closed
    shape where absence and emptiness look the same is easier to verify than
    one where a missing key has to be interpreted.
    """

    return {
        "schema_id": envelope.schema_id,
        "schema_version": envelope.schema_version,
        "delivery_id": envelope.delivery_id,
        "sender_ref": envelope.sender_ref,
        "recipient_ref": envelope.recipient_ref,
        "classroom_ref": envelope.classroom_ref,
        "assignment_artifact_digest": envelope.assignment_artifact_digest,
        "assignment_behavior_digest": envelope.assignment_behavior_digest,
        "assignment": assignment_to_dict(envelope.assignment),
    }


def serialize_delivery(envelope: LessonDeliveryEnvelopeV1) -> str:
    """Serialize to deterministic UTF-8 JSON text."""

    return (
        json.dumps(delivery_to_dict(envelope), indent=2, sort_keys=False, ensure_ascii=False) + "\n"
    )


def delivery_from_mapping(data: dict[str, Any]) -> LessonDeliveryEnvelopeV1:
    """Build an envelope from plain data, refusing anything it does not know."""

    if not isinstance(data, dict):
        raise EducationContractError("delivery must be an object")

    # Version before meaning. Interpreting the fields of a contract this code
    # does not implement is how a future envelope gets silently half-read.
    schema_id = data.get("schema_id")
    if schema_id != LESSON_DELIVERY_SCHEMA_ID:
        raise EducationContractError(f"unsupported schema_id: {schema_id!r}")
    schema_version = data.get("schema_version")
    if schema_version != LESSON_DELIVERY_SCHEMA_VERSION:
        raise EducationContractError(f"unsupported schema_version: {schema_version!r}")

    unknown = sorted(set(data) - set(_FIELDS))
    if unknown:
        raise EducationContractError(f"unknown delivery fields: {', '.join(unknown)}")
    missing = sorted(field for field in _FIELDS if field not in data)
    if missing:
        raise EducationContractError(f"missing delivery fields: {', '.join(missing)}")

    classroom_ref = data["classroom_ref"]
    if classroom_ref is not None and not isinstance(classroom_ref, str):
        raise EducationContractError("classroom_ref must be a string or null")
    for name in ("delivery_id", "sender_ref", "recipient_ref"):
        if not isinstance(data[name], str):
            raise EducationContractError(f"{name} must be a string")

    # The assignment is read by the lesson package, which owns what one is.
    assignment = deserialize_lesson_assignment(data["assignment"])
    return LessonDeliveryEnvelopeV1(
        schema_id=str(schema_id),
        schema_version=str(schema_version),
        delivery_id=data["delivery_id"],
        sender_ref=data["sender_ref"],
        recipient_ref=data["recipient_ref"],
        classroom_ref=classroom_ref,
        assignment_artifact_digest=str(data["assignment_artifact_digest"]),
        assignment_behavior_digest=str(data["assignment_behavior_digest"]),
        assignment=assignment,
    )


def deserialize_delivery(text: str | bytes | dict[str, Any]) -> LessonDeliveryEnvelopeV1:
    """Deserialize JSON into an envelope; reject unsupported schemas."""

    if isinstance(text, dict):
        return delivery_from_mapping(text)
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EducationContractError(f"malformed JSON: {exc.msg}") from exc
    if not isinstance(loaded, dict):
        raise EducationContractError("delivery must be an object")
    return delivery_from_mapping(loaded)


def envelope_for(
    assignment: Any,
    *,
    delivery_id: str,
    sender_ref: str,
    recipient_ref: str,
    classroom_ref: str | None = None,
) -> LessonDeliveryEnvelopeV1:
    """Address an assignment, computing both digests from it.

    A convenience for senders, and deliberately not one for receivers: it
    derives the digests rather than checking them, so nothing that arrives
    over the boundary should be rebuilt with it.
    """

    return LessonDeliveryEnvelopeV1(
        schema_id=LESSON_DELIVERY_SCHEMA_ID,
        schema_version=LESSON_DELIVERY_SCHEMA_VERSION,
        delivery_id=delivery_id,
        sender_ref=sender_ref,
        recipient_ref=recipient_ref,
        classroom_ref=classroom_ref,
        assignment_artifact_digest=compute_assignment_artifact_digest(assignment),
        assignment_behavior_digest=compute_lesson_behavior_digest(assignment),
        assignment=assignment,
    )
