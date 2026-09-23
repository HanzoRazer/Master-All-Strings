"""Where received deliveries sit.

Storage only. The repository does not validate digests, resolve music, or know
what an assignment means -- it holds envelopes and hands them back in a
predictable order. Every rule about what may be stored lives in the service,
so that swapping this in-memory implementation for a durable one later changes
where deliveries live and nothing about what delivery means.

One exception, and it is deliberate: *uniqueness of a delivery identity is
decided here*, in a single atomic operation. Asking "does this exist?" and
then writing is two operations, and the local server is threaded -- two
requests carrying one delivery_id can both pass the question before either
writes, and both be told they succeeded while one lesson silently replaces the
other. The check and the insert therefore happen together, under this store's
own lock, and a durable repository inherits the same obligation rather than
re-deriving it.

Ordering is by ``delivery_id``, explicitly. Insertion order, wall-clock time
and dictionary iteration are all things that happen to be stable until they are
not, and an inbox whose order depends on any of them is untestable.
"""

from __future__ import annotations

import threading
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

    def put_if_absent(self, envelope: LessonDeliveryEnvelopeV1) -> bool:
        """Store it unless its identity is taken. True when stored.

        The only write. There is deliberately no plain ``put``: a caller that
        could write unconditionally could also lose a race it did not know it
        was in.
        """
        ...

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
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def contains(self, delivery_id: str) -> bool:
        with self._lock:
            return delivery_id in self._deliveries

    def get(self, delivery_id: str) -> LessonDeliveryEnvelopeV1 | None:
        with self._lock:
            return self._deliveries.get(delivery_id)

    def put_if_absent(self, envelope: LessonDeliveryEnvelopeV1) -> bool:
        """Claim the identity and store, or refuse -- one indivisible step."""

        with self._lock:
            if envelope.delivery_id in self._deliveries:
                return False
            self._deliveries[envelope.delivery_id] = envelope
            return True

    def list(
        self, *, recipient_ref: str | None = None
    ) -> tuple[LessonDeliveryEnvelopeV1, ...]:
        """Deliveries ordered by ``delivery_id``, optionally for one recipient.

        Filtering by recipient selects; it does not authorize. Nothing here
        knows who is asking, and this must not become the place that decides.
        """

        with self._lock:
            snapshot = tuple(self._deliveries.values())
        chosen = [
            envelope
            for envelope in snapshot
            if recipient_ref is None or envelope.recipient_ref == recipient_ref
        ]
        return tuple(sorted(chosen, key=lambda envelope: envelope.delivery_id))
