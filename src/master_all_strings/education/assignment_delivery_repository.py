"""Where received deliveries sit.

Storage only. The repository does not validate digests, resolve music, or know
what an assignment means -- it holds envelopes and hands them back in a
predictable order. Every rule about what may be stored lives in the service,
so that swapping this in-memory implementation for a durable one later changes
where deliveries live and nothing about what delivery means.

Ordering is by ``delivery_id``, explicitly. Insertion order, wall-clock time
and dictionary iteration are all things that happen to be stable until they are
not, and an inbox whose order depends on any of them is untestable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from master_all_strings.education.assignment_delivery import LessonDeliveryEnvelopeV1

__all__ = [
    "InMemoryLessonDeliveryRepository",
    "LessonDeliveryRepository",
]


class LessonDeliveryRepository(Protocol):
    """The storage a delivery service needs, and nothing more."""

    def contains(self, delivery_id: str) -> bool: ...

    def get(self, delivery_id: str) -> LessonDeliveryEnvelopeV1 | None: ...

    def put(self, envelope: LessonDeliveryEnvelopeV1) -> None: ...

    def list(
        self, *, recipient_ref: str | None = None
    ) -> tuple[LessonDeliveryEnvelopeV1, ...]: ...


@dataclass
class InMemoryLessonDeliveryRepository:
    """Deliveries for one process run. Nothing here survives a restart.

    Durable persistence is later work, and deliberately so: a database chosen
    now would be chosen before anyone knows whether deliveries are per-device,
    per-classroom or per-account.
    """

    _deliveries: dict[str, LessonDeliveryEnvelopeV1] = field(default_factory=dict)

    def contains(self, delivery_id: str) -> bool:
        return delivery_id in self._deliveries

    def get(self, delivery_id: str) -> LessonDeliveryEnvelopeV1 | None:
        return self._deliveries.get(delivery_id)

    def put(self, envelope: LessonDeliveryEnvelopeV1) -> None:
        self._deliveries[envelope.delivery_id] = envelope

    def list(
        self, *, recipient_ref: str | None = None
    ) -> tuple[LessonDeliveryEnvelopeV1, ...]:
        """Deliveries ordered by ``delivery_id``, optionally for one recipient.

        Filtering by recipient selects; it does not authorize. Nothing here
        knows who is asking, and this must not become the place that decides.
        """

        chosen = [
            envelope
            for envelope in self._deliveries.values()
            if recipient_ref is None or envelope.recipient_ref == recipient_ref
        ]
        return tuple(sorted(chosen, key=lambda envelope: envelope.delivery_id))
