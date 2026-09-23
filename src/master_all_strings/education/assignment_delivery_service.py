"""Receiving a delivery into a student's inbox.

Receiving is not accepting, and it is emphatically not loading. A received
delivery is a lesson that arrived: it is checked, stored, and left alone. No
canonical resolution, no Transport, no evaluation, no guided session, no
playback. Whether the student then opens it is a later decision this tranche
does not make, and building that decision in here would make "it arrived" and
"I am working on it" the same event.

Two things are refused. A delivery whose digests do not recompute is not the
one that was sent, and a delivery reusing an existing identity is a collision
rather than a retry -- idempotent resend belongs to whatever protocol
eventually carries deliveries over a network, not to the inbox.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from master_all_strings.education.assignment_delivery import (
    LessonDeliveryEnvelopeV1,
    LessonDeliverySummaryV1,
    validate_delivery_integrity,
)
from master_all_strings.education.assignment_delivery_repository import (
    InMemoryLessonDeliveryRepository,
    LessonDeliveryRepository,
)
from master_all_strings.education.errors import EducationContractError

__all__ = [
    "DuplicateDeliveryError",
    "LessonDeliveryNotFoundError",
    "LessonDeliveryService",
]


class DuplicateDeliveryError(EducationContractError):
    """A delivery identity already in the inbox."""


class LessonDeliveryNotFoundError(EducationContractError):
    """No delivery under that identity."""


@dataclass
class LessonDeliveryService:
    """Receive, get and list. The inbox does no more than that."""

    repository: LessonDeliveryRepository = field(
        default_factory=InMemoryLessonDeliveryRepository
    )

    def receive(self, envelope: LessonDeliveryEnvelopeV1) -> LessonDeliveryEnvelopeV1:
        """Check the delivery, then store it.

        Both checks happen before anything is written, so a refused delivery
        leaves the inbox exactly as it was. A half-received delivery would be
        worse than a rejected one: the student would have a lesson nobody
        could vouch for.
        """

        validate_delivery_integrity(envelope)
        if self.repository.contains(envelope.delivery_id):
            raise DuplicateDeliveryError(
                f"delivery_id {envelope.delivery_id!r} has already been received"
            )
        self.repository.put(envelope)
        return envelope

    def get(self, delivery_id: str) -> LessonDeliveryEnvelopeV1:
        """The delivery, assignment and all."""

        envelope = self.repository.get(delivery_id)
        if envelope is None:
            raise LessonDeliveryNotFoundError(f"unknown delivery_id {delivery_id!r}")
        return envelope

    def list(self, *, recipient_ref: str | None = None) -> tuple[LessonDeliverySummaryV1, ...]:
        """What arrived, ordered by ``delivery_id``, without the lessons.

        Summaries, not envelopes: listing an inbox answers what is in it, and
        should not be a way to pull every lesson it holds.
        """

        return tuple(
            LessonDeliverySummaryV1.of(envelope)
            for envelope in self.repository.list(recipient_ref=recipient_ref)
        )
