"""Process-local bindings for one keyed Begin request.

A key is bound to one payload for the life of this process. The repository
lock only finds or creates that entry. Preparation and cancellation happen
outside both locks. Callers take the entry lock after releasing the
repository lock, never the other way around.
"""

from __future__ import annotations

import threading
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

__all__ = [
    "BeginPayload",
    "BeginRequestRepository",
    "PHASE_CLOSING",
    "PHASE_INTERRUPTED",
    "PHASE_NO_ATTEMPT",
    "PHASE_PREPARING",
    "PHASE_RECOVERY_REQUESTED",
    "PHASE_STARTED",
    "PHASE_UNRESOLVED",
]

PHASE_PREPARING = "preparing"
PHASE_STARTED = "started"
PHASE_RECOVERY_REQUESTED = "recovery_requested"
PHASE_CLOSING = "closing"
PHASE_INTERRUPTED = "interrupted"
PHASE_NO_ATTEMPT = "no_attempt"
PHASE_UNRESOLVED = "unresolved"

_OPEN = frozenset({PHASE_PREPARING, PHASE_RECOVERY_REQUESTED, PHASE_CLOSING})
_SEALED = frozenset({PHASE_INTERRUPTED, PHASE_NO_ATTEMPT})


@dataclass(frozen=True)
class BeginPayload:
    """The five Begin fields, compared exactly and never rewritten."""

    delivery_id: str
    artifact_digest: str
    behavior_digest: str
    device_id: str
    capture_time_ns: int


@dataclass(frozen=True)
class _Decision:
    kind: str
    attempt_id: str | None = None
    document: dict[str, Any] | None = None


@dataclass
class _Entry:
    payload: BeginPayload
    phase: str
    lock: threading.Lock
    attempt_id: str | None = None
    started: dict[str, Any] | None = None
    settled: dict[str, Any] | None = None


class BeginRequestRepository:
    """Immutable payload bindings and the published gateway documents."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._entries: dict[str, _Entry] = {}

    def reserve(self, key: str, payload: BeginPayload) -> _Decision:
        """Claim preparation, or report the key's existing fate."""

        with self._guard:
            entry = self._entries.get(key)
            if entry is None:
                self._entries[key] = _Entry(
                    payload=payload, phase=PHASE_PREPARING, lock=threading.Lock()
                )
                return _Decision("owner")
        return self._read(entry, payload, pending_ok=True)

    def request_recovery(self, key: str, payload: BeginPayload) -> _Decision:
        """Seal an unknown key, or ask the owner to cancel an open attempt."""

        with self._guard:
            entry = self._entries.get(key)
            if entry is None:
                self._entries[key] = _Entry(
                    payload=payload, phase=PHASE_NO_ATTEMPT, lock=threading.Lock()
                )
                return _Decision("no_attempt")
        with entry.lock:
            if entry.payload != payload:
                return _Decision("conflict")
            if entry.phase == PHASE_NO_ATTEMPT:
                return _Decision("no_attempt")
            if entry.phase == PHASE_INTERRUPTED:
                return _Decision("interrupted", entry.attempt_id, deepcopy(entry.settled))
            if entry.phase == PHASE_STARTED:
                entry.phase = PHASE_CLOSING
                return _Decision("cancel", entry.attempt_id)
            if entry.phase == PHASE_UNRESOLVED and entry.attempt_id:
                entry.phase = PHASE_CLOSING
                return _Decision("cancel", entry.attempt_id)
            if entry.phase == PHASE_UNRESOLVED:
                return _Decision("unresolved")
            if entry.phase == PHASE_PREPARING:
                entry.phase = PHASE_RECOVERY_REQUESTED
            return _Decision("pending")

    def claim_publication(
        self, key: str, attempt_id: str, document: dict[str, Any]
    ) -> _Decision:
        """Attach a committed attempt. Recovery requested during preparation cancels it."""

        entry = self._entry(key)
        with entry.lock:
            entry.attempt_id = attempt_id
            entry.started = deepcopy(document)
            if entry.phase == PHASE_RECOVERY_REQUESTED:
                entry.phase = PHASE_CLOSING
                return _Decision("cancel", attempt_id)
            entry.phase = PHASE_STARTED
            return _Decision("started", attempt_id, deepcopy(document))

    def publish_interrupted(self, key: str, document: dict[str, Any]) -> dict[str, Any]:
        entry = self._entry(key)
        with entry.lock:
            entry.phase = PHASE_INTERRUPTED
            entry.settled = deepcopy(document)
            return deepcopy(entry.settled)

    def seal_no_attempt(self, key: str) -> None:
        """Record that this key inserted nothing. Do not hide a stored attempt."""

        entry = self._entry(key)
        with entry.lock:
            if entry.attempt_id is not None or entry.phase in (_SEALED | {PHASE_STARTED}):
                return
            entry.phase = PHASE_NO_ATTEMPT
            entry.settled = None

    def mark_unresolved(self, key: str, attempt_id: str | None) -> None:
        entry = self._entry(key)
        with entry.lock:
            if entry.phase in _SEALED or entry.phase == PHASE_STARTED:
                return
            entry.phase = PHASE_UNRESOLVED
            if attempt_id:
                entry.attempt_id = attempt_id

    def started_document(self, key: str) -> dict[str, Any] | None:
        entry = self._entry(key)
        with entry.lock:
            if entry.started is None:
                return None
            return deepcopy(entry.started)

    def phase(self, key: str) -> str | None:
        with self._guard:
            entry = self._entries.get(key)
        if entry is None:
            return None
        with entry.lock:
            return entry.phase

    def _entry(self, key: str) -> _Entry:
        with self._guard:
            entry = self._entries.get(key)
        if entry is None:
            raise KeyError(key)
        return entry

    def _read(self, entry: _Entry, payload: BeginPayload, *, pending_ok: bool) -> _Decision:
        with entry.lock:
            if entry.payload != payload:
                return _Decision("conflict")
            if entry.phase in _SEALED:
                return _Decision("closed")
            if entry.phase == PHASE_STARTED:
                return _Decision("started", entry.attempt_id, deepcopy(entry.started))
            if entry.phase == PHASE_UNRESOLVED:
                return _Decision("unresolved")
            if pending_ok and entry.phase in _OPEN:
                return _Decision("pending")
            return _Decision("pending")
