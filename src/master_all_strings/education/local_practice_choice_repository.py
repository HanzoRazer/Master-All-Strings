"""Where a local practice choice sits.

Storage only. The repository does not preview a delivery, compare digests, or
decide what a choice means. Uniqueness of a delivery identity is decided here,
in one locked step, because the localhost server is threaded: two identical
requests must not both be told they created the record.

There is no unconditional write. A caller that could replace a choice could
also lose a race, or let a stale request overwrite a choice it did not match.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from master_all_strings.education.local_practice_choice import LocalPracticeChoiceV1

__all__ = [
    "InMemoryLocalPracticeChoiceRepository",
    "LocalPracticeChoiceRepository",
]


class LocalPracticeChoiceRepository(Protocol):
    """The storage a choice service needs, and nothing more."""

    def get(self, delivery_id: str) -> LocalPracticeChoiceV1 | None: ...

    def put_if_absent(self, choice: LocalPracticeChoiceV1) -> bool:
        """Store it unless its delivery identity is taken. True when stored.

        The only write. There is deliberately no plain ``put``.
        """
        ...


@dataclass
class InMemoryLocalPracticeChoiceRepository:
    """Choices for one process run. Nothing here survives a restart.

    This is separate from the delivery inbox. Choosing a lesson does not
    rewrite the delivery, and receiving a delivery does not choose it.
    """

    _choices: dict[str, LocalPracticeChoiceV1] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get(self, delivery_id: str) -> LocalPracticeChoiceV1 | None:
        with self._lock:
            return self._choices.get(delivery_id)

    def put_if_absent(self, choice: LocalPracticeChoiceV1) -> bool:
        """Claim the delivery identity and store, or refuse -- one step."""

        with self._lock:
            if choice.delivery_id in self._choices:
                return False
            self._choices[choice.delivery_id] = choice
            return True
