"""Keyed Begin and explicit cancellation recovery.

The browser keeps the key. This process remembers the payload and, when a
Begin actually inserted an attempt, cancels that attempt on recovery. A
sealed key never prepares another snapshot.
"""

from __future__ import annotations

from typing import Any

from master_all_strings.education.assignment_delivery_preview import (
    DeliveryIntegrityError,
    UnresolvableAssignmentError,
)
from master_all_strings.education.assignment_delivery_service import LessonDeliveryNotFoundError
from master_all_strings.education.local_practice_choice import (
    StalePreviewError,
    UnknownPracticeChoiceError,
)
from master_all_strings.mvp.local_practice_preparation import (
    PreparationFailure,
    UnpreparableAssignmentError,
    UnsupportedInstrumentError,
)
from master_all_strings.mvp.received_lesson_attempt import (
    ATTEMPT_STATUS_CAPTURING,
    ATTEMPT_STATUS_INTERRUPTED,
    AttemptConflictError,
    AttemptRequestError,
    AttemptSnapshotError,
    ReceivedLessonAttemptService,
)
from master_all_strings.mvp.received_lesson_begin_request_repository import (
    BeginPayload,
    BeginRequestRepository,
)

__all__ = [
    "BEGIN_REQUEST_SCHEMA_ID",
    "BEGIN_REQUEST_SCHEMA_VERSION",
    "ReceivedLessonBeginGateway",
]

BEGIN_REQUEST_SCHEMA_ID = "master_all_strings.received_lesson_begin_request"
BEGIN_REQUEST_SCHEMA_VERSION = "1.0.0"

_PRE_INSERT = (
    AttemptRequestError,
    UnknownPracticeChoiceError,
    LessonDeliveryNotFoundError,
    DeliveryIntegrityError,
    StalePreviewError,
    UnresolvableAssignmentError,
    UnsupportedInstrumentError,
    UnpreparableAssignmentError,
    PreparationFailure,
    AttemptSnapshotError,
)


class ReceivedLessonBeginGateway:
    """One attempt service, addressed by a browser-generated request key."""

    def __init__(
        self,
        service: ReceivedLessonAttemptService,
        repository: BeginRequestRepository | None = None,
    ) -> None:
        self.service = service
        self.repository = repository or BeginRequestRepository()

    def begin(self, key: str, payload: BeginPayload) -> tuple[int, dict[str, Any]]:
        decision = self.repository.reserve(key, payload)
        if decision.kind == "conflict":
            return 409, {"error": "begin_request_conflict"}
        if decision.kind == "closed":
            return 409, {"error": "begin_request_closed"}
        if decision.kind == "pending":
            return 202, _wrapper(key, "PENDING", None)
        if decision.kind == "unresolved":
            return 500, {"error": "internal server error"}
        if decision.kind == "started":
            return 200, _wrapper(key, "STARTED", decision.document)
        try:
            attempt, document = self.service.assemble_begin(
                payload.delivery_id,
                payload.artifact_digest,
                payload.behavior_digest,
                payload.device_id,
                payload.capture_time_ns,
            )
        except _PRE_INSERT as exc:
            self.repository.seal_no_attempt(key)
            return _public_error(exc)
        except Exception:
            self.repository.mark_unresolved(key, None)
            return 500, {"error": "internal server error"}
        try:
            self.service.commit_begin(attempt)
        except Exception:
            self.repository.seal_no_attempt(key)
            return 500, {"error": "internal server error"}
        try:
            published = self.repository.claim_publication(key, attempt.attempt_id, document)
        except Exception:
            self.repository.mark_unresolved(key, attempt.attempt_id)
            return 500, {"error": "internal server error"}
        if published.kind == "started":
            return 201, _wrapper(key, "STARTED", document)
        return self._cancel_published(key, attempt.attempt_id, payload.capture_time_ns)

    def recover(self, key: str, payload: BeginPayload) -> tuple[int, dict[str, Any]]:
        decision = self.repository.request_recovery(key, payload)
        if decision.kind == "conflict":
            return 409, {"error": "begin_request_conflict"}
        if decision.kind == "pending":
            return 202, _wrapper(key, "PENDING", None)
        if decision.kind == "no_attempt":
            return 200, _wrapper(key, "NO_ATTEMPT", None)
        if decision.kind == "interrupted":
            return 200, _wrapper(key, "INTERRUPTED", decision.document)
        if decision.kind == "unresolved":
            return 500, {"error": "internal server error"}
        return self._cancel_published(key, decision.attempt_id or "", payload.capture_time_ns)

    def _cancel_published(
        self, key: str, attempt_id: str, capture_time_ns: int
    ) -> tuple[int, dict[str, Any]]:
        attempt = self.service.repository.get(attempt_id)
        events = getattr(getattr(attempt, "capture", None), "events", ())
        open_capture = (
            attempt is not None
            and attempt.phase == ATTEMPT_STATUS_CAPTURING
            and attempt.next_sequence == 0
            and not events
        )
        if not open_capture:
            self.repository.mark_unresolved(key, attempt_id or None)
            return 409, {"error": "attempt_conflict"}
        try:
            document = self.service.cancel(attempt_id, capture_time_ns)
        except AttemptConflictError:
            self.repository.mark_unresolved(key, attempt_id)
            return 409, {"error": "attempt_conflict"}
        except Exception:
            self.repository.mark_unresolved(key, attempt_id)
            return 500, {"error": "internal server error"}
        if document.get("attempt_status") != ATTEMPT_STATUS_INTERRUPTED:
            self.repository.mark_unresolved(key, attempt_id)
            return 500, {"error": "internal server error"}
        if document.get("observed_events"):
            self.repository.mark_unresolved(key, attempt_id)
            return 409, {"error": "attempt_conflict"}
        stored = self.repository.publish_interrupted(key, document)
        return 200, _wrapper(key, "INTERRUPTED", stored)


def _wrapper(key: str, status: str, attempt: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "schema_id": BEGIN_REQUEST_SCHEMA_ID,
        "schema_version": BEGIN_REQUEST_SCHEMA_VERSION,
        "begin_request_id": key,
        "status": status,
        "attempt": attempt,
    }


def _public_error(exc: BaseException) -> tuple[int, dict[str, str]]:
    if isinstance(exc, AttemptRequestError):
        return 400, {"error": str(exc)}
    if isinstance(exc, UnknownPracticeChoiceError):
        return 404, {"error": "unknown_practice_choice"}
    if isinstance(exc, LessonDeliveryNotFoundError):
        return 404, {"error": "unknown_delivery_id"}
    if isinstance(exc, DeliveryIntegrityError):
        return 409, {"error": "integrity_mismatch"}
    if isinstance(exc, StalePreviewError):
        return 409, {"error": "stale_preview"}
    if isinstance(exc, UnresolvableAssignmentError):
        return 422, {"error": "unresolvable_assignment"}
    if isinstance(exc, UnsupportedInstrumentError):
        return 422, {"error": "unsupported_instrument"}
    if isinstance(exc, UnpreparableAssignmentError):
        return 422, {"error": "unpreparable_assignment"}
    return 500, {"error": "internal server error"}
