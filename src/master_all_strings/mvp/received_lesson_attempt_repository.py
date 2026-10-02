"""In-memory store of isolated received-lesson attempts.

An attempt is inserted once. A second insert with the same id does not replace
the active record. Callers serialize transitions on the record's own lock and
do not hold the repository lock while they prepare or evaluate.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "AttemptCollisionError",
    "ReceivedLessonAttemptRepository",
    "StoredAttempt",
]


class AttemptCollisionError(Exception):
    """The attempt id is already stored."""


@dataclass
class StoredAttempt:
    """One attempt's snapshot, capture, and terminal state.

    The repository does not interpret these fields. The service does, under
    ``lock``. ``ready`` is bound to that same lock so a waiter can sleep
    without pinning every other attempt.
    """

    attempt_id: str
    capture_id: str
    performance_session_id: str
    device_id: str
    begin_capture_time_ns: int
    preparation: dict[str, Any]
    policy: dict[str, Any]
    expected_events: tuple[Any, ...]
    tempo_changes: tuple[Any, ...]
    ticks_per_quarter: int
    total_seconds: float
    tempo_context: float
    meter_context: Any
    canonical_revision_id: str
    capture: Any
    history: Any
    lock: threading.Lock = field(default_factory=threading.Lock)
    ready: threading.Condition = field(init=False)
    phase: str = "CAPTURING"
    intent: str | None = None
    next_sequence: int = 0
    last_capture_time_ns: int = 0
    last_practice_position: float | None = None
    positions: dict[str, float] = field(default_factory=dict)
    result: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.ready = threading.Condition(self.lock)
        self.last_capture_time_ns = self.begin_capture_time_ns


class ReceivedLessonAttemptRepository:
    """Process-local attempts. Nothing here is written to disk."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._attempts: dict[str, StoredAttempt] = {}

    def insert(self, attempt: StoredAttempt) -> None:
        """Store ``attempt`` unless that id is already present."""

        with self._guard:
            if attempt.attempt_id in self._attempts:
                raise AttemptCollisionError(attempt.attempt_id)
            self._attempts[attempt.attempt_id] = attempt

    def get(self, attempt_id: str) -> StoredAttempt | None:
        """Return the record, or none. The repository lock is not held after."""

        with self._guard:
            return self._attempts.get(attempt_id)
