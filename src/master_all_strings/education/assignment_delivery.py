"""Delivery envelope for a lesson assignment.

`LessonAssignmentV1` is portable and frozen at schema 1.0.0. It says what a
lesson *is*; it has never said where a copy of it is going. Routing metadata
exists inside it but is semantically inert, and it stays that way: two students
receiving the same lesson must receive the *same artifact*, not two artifacts
differing by destination.

So addressing lives out here, in an envelope wrapped around the assignment:

    LessonDeliveryEnvelopeV1
        delivery identity        who sent it, who receives it, which classroom
        assignment digests       what was sent, pinned twice
        assignment               the unmodified LessonAssignmentV1

The two digests answer two different questions. The artifact digest asks
whether the exact serialized assignment changed; the behaviour digest asks
whether the musical or instructional meaning changed. Editing an assignment's
routing moves the first and not the second, which is the distinction this
envelope depends on and must not blur.

This module owns the contract only. Storing deliveries is the repository's
job, receiving them is the service's, and neither belongs here.
"""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.education.errors import (
    EducationContractError,
    require_identifier,
    require_optional_identifier,
    require_schema_version,
)
from master_all_strings.lesson.models import LessonAssignmentV1
from master_all_strings.lesson.serialization import (
    compute_assignment_artifact_digest,
    compute_lesson_behavior_digest,
)

__all__ = [
    "LESSON_DELIVERY_SCHEMA_ID",
    "LESSON_DELIVERY_SCHEMA_VERSION",
    "LessonDeliveryEnvelopeV1",
    "LessonDeliverySummaryV1",
    "validate_delivery_integrity",
]

#: The delivery contract versions independently of the lesson it carries. A
#: change to how assignments are addressed is not a change to what a lesson is.
LESSON_DELIVERY_SCHEMA_ID = "master_all_strings.lesson_delivery"
LESSON_DELIVERY_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class LessonDeliveryEnvelopeV1:
    """One assignment, addressed to one recipient.

    The same assignment may be delivered many times under different delivery
    identities; that is how one lesson reaches a class. What may not happen is
    the assignment changing because its destination did.
    """

    schema_id: str
    schema_version: str
    delivery_id: str
    sender_ref: str
    recipient_ref: str
    classroom_ref: str | None
    assignment_artifact_digest: str
    assignment_behavior_digest: str
    assignment: LessonAssignmentV1

    def __post_init__(self) -> None:
        # Schema identity is checked before anything else is interpreted: an
        # envelope from a contract this code does not know is not an envelope
        # with unfamiliar fields, it is an unknown object.
        if self.schema_id != LESSON_DELIVERY_SCHEMA_ID:
            raise EducationContractError(
                f"schema_id must be {LESSON_DELIVERY_SCHEMA_ID!r}, got {self.schema_id!r}"
            )
        require_schema_version(self.schema_version, LESSON_DELIVERY_SCHEMA_VERSION)
        require_identifier(self.delivery_id, "delivery_id")
        # Opaque strings. Not accounts, not addresses, not identities the
        # system can authenticate -- and nothing here should start treating
        # them as any of those.
        require_identifier(self.sender_ref, "sender_ref")
        require_identifier(self.recipient_ref, "recipient_ref")
        require_optional_identifier(self.classroom_ref, "classroom_ref")
        require_identifier(self.assignment_artifact_digest, "assignment_artifact_digest")
        require_identifier(self.assignment_behavior_digest, "assignment_behavior_digest")
        if not isinstance(self.assignment, LessonAssignmentV1):
            raise EducationContractError("assignment must be a LessonAssignmentV1")

    @property
    def assignment_id(self) -> str:
        return self.assignment.assignment_id

    @property
    def content_id(self) -> str:
        return self.assignment.content_id


@dataclass(frozen=True)
class LessonDeliverySummaryV1:
    """What an inbox listing shows: addressing and identity, no lesson body.

    Listing an inbox is a question about what arrived, not a request for every
    lesson in it. Carrying assignments here would make a list of fifty
    deliveries a transfer of fifty lessons.
    """

    delivery_id: str
    sender_ref: str
    recipient_ref: str
    classroom_ref: str | None
    assignment_artifact_digest: str
    assignment_behavior_digest: str
    assignment_id: str
    content_id: str

    @classmethod
    def of(cls, envelope: LessonDeliveryEnvelopeV1) -> LessonDeliverySummaryV1:
        return cls(
            delivery_id=envelope.delivery_id,
            sender_ref=envelope.sender_ref,
            recipient_ref=envelope.recipient_ref,
            classroom_ref=envelope.classroom_ref,
            assignment_artifact_digest=envelope.assignment_artifact_digest,
            assignment_behavior_digest=envelope.assignment_behavior_digest,
            assignment_id=envelope.assignment_id,
            content_id=envelope.content_id,
        )


def validate_delivery_integrity(envelope: LessonDeliveryEnvelopeV1) -> None:
    """Recompute both digests from the carried assignment; raise on mismatch.

    A digest the sender supplied is a claim. Recomputing it from the assignment
    actually present is what makes it evidence, and the two failures are
    reported separately because they mean different things: a changed artifact
    with intact behaviour is an edit to routing or provenance, while a changed
    behaviour digest means the lesson itself is not the one that was sent.
    """

    artifact = compute_assignment_artifact_digest(envelope.assignment)
    if artifact != envelope.assignment_artifact_digest:
        raise EducationContractError(
            "assignment_artifact_digest does not match the carried assignment: "
            f"declared {envelope.assignment_artifact_digest}, computed {artifact}"
        )
    behavior = compute_lesson_behavior_digest(envelope.assignment)
    if behavior != envelope.assignment_behavior_digest:
        raise EducationContractError(
            "assignment_behavior_digest does not match the carried assignment: "
            f"declared {envelope.assignment_behavior_digest}, computed {behavior}"
        )
