"""Localhost HTTP boundary for isolated received-lesson attempts.

The four routes are exact paths. A body is a closed object, a query string is
refused, and a failure is an error document with no attempt fields. Stage 5
begin failures keep that stage's public codes. This module does not capture
through the legacy performance facade or evaluate through the legacy
education facade.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from master_all_strings.education.assignment_delivery import require_digest
from master_all_strings.education.assignment_delivery_preview import (
    DeliveryIntegrityError,
    UnresolvableAssignmentError,
)
from master_all_strings.education.assignment_delivery_service import (
    LessonDeliveryNotFoundError,
    LessonDeliveryService,
)
from master_all_strings.education.errors import EducationContractError
from master_all_strings.education.local_practice_choice import (
    StalePreviewError,
    UnknownPracticeChoiceError,
)
from master_all_strings.education.local_practice_choice_repository import (
    InMemoryLocalPracticeChoiceRepository,
)
from master_all_strings.mvp.local_practice_preparation import (
    PreparationFailure,
    UnpreparableAssignmentError,
    UnsupportedInstrumentError,
)
from master_all_strings.mvp.received_lesson_attempt import (
    AttemptClosedError,
    AttemptConflictError,
    AttemptEvaluationError,
    AttemptRequestError,
    AttemptSnapshotError,
    ReceivedLessonAttemptService,
    SequenceConflictError,
    UnknownAttemptError,
)

__all__ = [
    "LESSON_PRACTICE_ATTEMPT_CANCELLATION_PATH",
    "LESSON_PRACTICE_ATTEMPT_FINISH_PATH",
    "LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH",
    "LESSON_PRACTICE_ATTEMPT_PATH",
    "LocalReceivedLessonAttemptApi",
]

LESSON_PRACTICE_ATTEMPT_PATH = "/api/education/lesson-practice-attempts"
LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH = "/api/education/lesson-practice-attempt-messages"
LESSON_PRACTICE_ATTEMPT_FINISH_PATH = "/api/education/lesson-practice-attempt-finishes"
LESSON_PRACTICE_ATTEMPT_CANCELLATION_PATH = "/api/education/lesson-practice-attempt-cancellations"

ATTEMPT_PATHS = frozenset(
    {
        LESSON_PRACTICE_ATTEMPT_PATH,
        LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH,
        LESSON_PRACTICE_ATTEMPT_FINISH_PATH,
        LESSON_PRACTICE_ATTEMPT_CANCELLATION_PATH,
    }
)

_BEGIN_FIELDS = (
    "delivery_id",
    "expected_assignment_artifact_digest",
    "expected_assignment_behavior_digest",
    "device_id",
    "capture_time_ns",
)
_MESSAGE_FIELDS = (
    "attempt_id",
    "sequence_number",
    "capture_time_ns",
    "practice_position_seconds",
    "raw_payload",
)
_TERMINAL_FIELDS = ("attempt_id", "capture_time_ns")


class LocalReceivedLessonAttemptApi:
    """Dispatch the four attempt routes onto one shared delivery inbox."""

    def __init__(
        self,
        deliveries: LessonDeliveryService,
        choices: InMemoryLocalPracticeChoiceRepository,
        *,
        service: ReceivedLessonAttemptService | None = None,
    ) -> None:
        self.service = service or ReceivedLessonAttemptService(deliveries, choices)

    def handle_http(
        self, method: str, path: str, payload: dict[str, Any]
    ) -> tuple[int, dict[str, Any]]:
        parsed = urlparse(path)
        if parsed.path not in ATTEMPT_PATHS:
            return 404, {"error": f"unsupported lesson attempt request: {method} {path}"}
        if method != "POST":
            return 405, {"error": "method not allowed"}
        if parsed.query:
            return 400, {"error": "query string is not allowed"}
        try:
            if parsed.path == LESSON_PRACTICE_ATTEMPT_PATH:
                return 201, self.service.begin(*_begin_body(payload))
            if parsed.path == LESSON_PRACTICE_ATTEMPT_MESSAGE_PATH:
                return 200, self.service.append_message(*_message_body(payload))
            if parsed.path == LESSON_PRACTICE_ATTEMPT_FINISH_PATH:
                return 200, self.service.finish(*_terminal_body(payload))
            return 200, self.service.cancel(*_terminal_body(payload))
        except AttemptRequestError as exc:
            return 400, {"error": str(exc)}
        except UnknownPracticeChoiceError:
            return 404, {"error": "unknown_practice_choice"}
        except LessonDeliveryNotFoundError:
            return 404, {"error": "unknown_delivery_id"}
        except UnknownAttemptError:
            return 404, {"error": "unknown_attempt"}
        except DeliveryIntegrityError:
            return 409, {"error": "integrity_mismatch"}
        except StalePreviewError:
            return 409, {"error": "stale_preview"}
        except SequenceConflictError:
            return 409, {"error": "sequence_conflict"}
        except AttemptClosedError:
            return 409, {"error": "attempt_closed"}
        except AttemptConflictError:
            return 409, {"error": "attempt_conflict"}
        except UnresolvableAssignmentError:
            return 422, {"error": "unresolvable_assignment"}
        except UnsupportedInstrumentError:
            return 422, {"error": "unsupported_instrument"}
        except UnpreparableAssignmentError:
            return 422, {"error": "unpreparable_assignment"}
        except (PreparationFailure, AttemptSnapshotError, AttemptEvaluationError):
            return 500, {"error": "internal server error"}
        except Exception:
            return 500, {"error": "internal server error"}


def _closed(payload: dict[str, Any], fields: tuple[str, ...], label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AttemptRequestError("payload must be an object")
    if set(payload) != set(fields):
        names = ", ".join(fields)
        raise AttemptRequestError(f"{label} body must contain exactly {names}")
    return payload


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise AttemptRequestError(f"{name} must be a string")
    try:
        require_digest(value, name)
    except EducationContractError as exc:
        raise AttemptRequestError(str(exc)) from exc
    return value


def _begin_body(payload: dict[str, Any]) -> tuple[str, str, str, str, int]:
    body = _closed(payload, _BEGIN_FIELDS, "begin")
    return (
        body["delivery_id"],
        _digest(body["expected_assignment_artifact_digest"], "expected_assignment_artifact_digest"),
        _digest(body["expected_assignment_behavior_digest"], "expected_assignment_behavior_digest"),
        body["device_id"],
        body["capture_time_ns"],
    )


def _message_body(payload: dict[str, Any]) -> tuple[str, int, int, float, list[int]]:
    body = _closed(payload, _MESSAGE_FIELDS, "message")
    raw = body["raw_payload"]
    if not isinstance(raw, list):
        raise AttemptRequestError("raw_payload must be three MIDI bytes")
    return (
        body["attempt_id"],
        body["sequence_number"],
        body["capture_time_ns"],
        body["practice_position_seconds"],
        raw,
    )


def _terminal_body(payload: dict[str, Any]) -> tuple[str, int]:
    body = _closed(payload, _TERMINAL_FIELDS, "terminal")
    return body["attempt_id"], body["capture_time_ns"]
