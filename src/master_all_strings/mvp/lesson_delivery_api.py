"""Localhost application seam for lesson deliveries.

This is where a delivery crosses a process boundary instead of a function call,
which is the whole point of the tranche: the same envelope that a future
network layer will carry is already the thing this API accepts today. What that
future layer plugs into is settled here; what it is built from is not.

It is not networking. There is no client, no discovery, no remote host, and no
identity: `recipient_ref` selects an inbox view and authorizes nothing. When
authentication eventually exists, it belongs in front of this, not inside it.

Status codes carry the distinction the service draws:

    201  received and stored
    400  malformed, or digests that do not recompute on receipt;
         a preview whose delivery_id query is missing, blank, or repeated
         (a delivery_id is percent-encoded: it is opaque, and opaque includes
         characters that mean something in a URL)
    409  a delivery identity already used, or a stored preview whose declared
         digests do not recompute (``integrity_mismatch``)
    404  no such delivery
    405  a method other than GET on the preview route, other than GET or POST
         on the practice-choice route, or other than POST on the preparation
         route
    422  a stored assignment that cannot be resolved (``unresolvable_assignment``),
         or a preparation whose declared instrument is missing
         (``unsupported_instrument``) or whose assignment fails a known check
         (``unpreparable_assignment``)
    500  a defect in this application, reported without detail

A practice choice uses the same codes, plus ``unknown_practice_choice``,
``unknown_delivery_id``, ``stale_preview``, and ``choice_conflict``. A
preparation uses those codes except ``choice_conflict``, and adds the two
422 codes above. Those bodies are codes. Stage 1's not-found sentence stays
on the delivery routes. An unexpected projection or playback failure during
preparation is the sanitized 500, not a 422.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from master_all_strings.education.assignment_delivery import (
    LessonDeliverySummaryV1,
    require_digest,
)
from master_all_strings.education.assignment_delivery_preview import (
    DeliveryIntegrityError,
    LessonDeliveryPreviewService,
    UnresolvableAssignmentError,
    preview_to_dict,
)
from master_all_strings.education.assignment_delivery_serialization import (
    delivery_to_dict,
    deserialize_delivery,
)
from master_all_strings.education.assignment_delivery_service import (
    DuplicateDeliveryError,
    LessonDeliveryNotFoundError,
    LessonDeliveryService,
)
from master_all_strings.education.errors import EducationContractError
from master_all_strings.education.local_practice_choice import (
    ChoiceConflictError,
    LocalPracticeChoiceService,
    StalePreviewError,
    UnknownPracticeChoiceError,
    choice_to_dict,
)
from master_all_strings.education.local_practice_choice_repository import (
    InMemoryLocalPracticeChoiceRepository,
)
from master_all_strings.lesson.errors import LessonAssignmentError
from master_all_strings.mvp.local_practice_preparation import (
    LocalPracticePreparationService,
    PreparationFailure,
    UnpreparableAssignmentError,
    UnsupportedInstrumentError,
    preparation_to_dict,
    shared_application,
)

__all__ = [
    "LESSON_DELIVERY_API_PREFIX",
    "LESSON_DELIVERY_PREVIEW_PATH",
    "LESSON_PRACTICE_CHOICE_PATH",
    "LESSON_PRACTICE_PREPARATION_PATH",
    "LocalLessonDeliveryApi",
]

LESSON_DELIVERY_API_PREFIX = "/api/education/lesson-deliveries"
#: Sibling of the collection, not a suffix of it. Equality is the match.
LESSON_DELIVERY_PREVIEW_PATH = "/api/education/lesson-delivery-preview"
#: Exact collection. Not a suffix of the delivery inbox or the preview route.
LESSON_PRACTICE_CHOICE_PATH = "/api/education/lesson-practice-choices"
#: Exact collection. Preparing a choice is not choosing it, and not fetching it.
LESSON_PRACTICE_PREPARATION_PATH = "/api/education/lesson-practice-preparations"
_CHOICE_FIELDS = (
    "delivery_id",
    "expected_assignment_artifact_digest",
    "expected_assignment_behavior_digest",
)


class _PreviewQueryError(Exception):
    """The preview route was asked for an identity it can refuse locally."""


class _ChoiceRequestError(Exception):
    """The choice route was asked for a body or query it can refuse locally."""


def _single_delivery_id(query: str) -> str:
    """One nonblank delivery id, decoded once by the query parser.

    ``parse_qs`` percent-decodes. Calling ``unquote`` on the result would
    decode a second time, and an id that contains the characters ``%2F`` would
    become a slash. Blank values are kept so ``delivery_id=`` is a blank id,
    not a missing one. The returned string is not stripped: a padded id is a
    different id.
    """

    values = parse_qs(query, keep_blank_values=True).get("delivery_id")
    if values is None:
        raise _PreviewQueryError("delivery_id is required")
    if len(values) != 1:
        raise _PreviewQueryError("delivery_id must appear exactly once")
    delivery_id = values[0]
    if not delivery_id.strip():
        raise _PreviewQueryError("delivery_id must be nonblank")
    return delivery_id


def _choice_body(payload: dict[str, Any]) -> tuple[str, str, str]:
    """Exactly the three choice fields. The caller cannot send a status."""

    return _pinned_body(payload, label="choice")


def _preparation_body(payload: dict[str, Any]) -> tuple[str, str, str]:
    """The same three fields as a choice. Preparation adds no fourth."""

    return _pinned_body(payload, label="preparation")


def _pinned_body(payload: dict[str, Any], *, label: str) -> tuple[str, str, str]:
    if not isinstance(payload, dict):
        raise _ChoiceRequestError("payload must be an object")
    if set(payload) != set(_CHOICE_FIELDS):
        names = ", ".join(_CHOICE_FIELDS)
        raise _ChoiceRequestError(f"{label} body must contain exactly {names}")
    delivery_id = payload["delivery_id"]
    if not isinstance(delivery_id, str) or not delivery_id.strip():
        raise _ChoiceRequestError("delivery_id must be nonblank")
    artifact = payload["expected_assignment_artifact_digest"]
    behavior = payload["expected_assignment_behavior_digest"]
    _require_choice_digest(artifact, "expected_assignment_artifact_digest")
    _require_choice_digest(behavior, "expected_assignment_behavior_digest")
    return delivery_id, artifact, behavior


def _require_choice_digest(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise _ChoiceRequestError(f"{field_name} must be a string")
    try:
        require_digest(value, field_name)
    except EducationContractError as exc:
        raise _ChoiceRequestError(str(exc)) from exc


def _summary_to_dict(summary: LessonDeliverySummaryV1) -> dict[str, Any]:
    return {
        "delivery_id": summary.delivery_id,
        "sender_ref": summary.sender_ref,
        "recipient_ref": summary.recipient_ref,
        "classroom_ref": summary.classroom_ref,
        "assignment_artifact_digest": summary.assignment_artifact_digest,
        "assignment_behavior_digest": summary.assignment_behavior_digest,
        "assignment_id": summary.assignment_id,
        "content_id": summary.content_id,
    }


@dataclass
class LocalLessonDeliveryApi:
    """Receive, list and fetch deliveries over localhost.

    Receiving stores an envelope and stops there. Preview reads one stored
    envelope and returns a summary; it does not start playback, evaluate a
    learner, or open a guided session. Addressing on the envelope authorizes
    nothing in either path.
    """

    service: LessonDeliveryService = field(default_factory=LessonDeliveryService)
    choices: InMemoryLocalPracticeChoiceRepository = field(
        default_factory=InMemoryLocalPracticeChoiceRepository
    )

    def _practice_choices(self) -> LocalPracticeChoiceService:
        return LocalPracticeChoiceService(
            LessonDeliveryPreviewService(self.service),
            self.choices,
        )

    def _preparations(self) -> LocalPracticePreparationService:
        return LocalPracticePreparationService(
            self.service,
            self._practice_choices(),
            shared_application(),
        )

    def receive(self, payload: dict[str, Any]) -> dict[str, Any]:
        envelope = deserialize_delivery(payload)
        return delivery_to_dict(self.service.receive(envelope))

    def get(self, delivery_id: str) -> dict[str, Any]:
        return delivery_to_dict(self.service.get(delivery_id))

    def list(self, *, recipient_ref: str | None = None) -> dict[str, Any]:
        summaries = self.service.list(recipient_ref=recipient_ref)
        return {
            "recipient_ref": recipient_ref,
            "count": len(summaries),
            "deliveries": [_summary_to_dict(summary) for summary in summaries],
        }

    def handle_http(
        self, method: str, path: str, payload: dict[str, Any]
    ) -> tuple[int, dict[str, Any]]:
        """Map a request onto the service, and failures onto status codes."""

        parsed = urlparse(path)
        if parsed.path == LESSON_PRACTICE_PREPARATION_PATH:
            return self._handle_preparation(method, parsed.query, payload)
        if parsed.path == LESSON_PRACTICE_CHOICE_PATH:
            return self._handle_choice(method, parsed.query, payload)
        if parsed.path == LESSON_DELIVERY_PREVIEW_PATH:
            return self._handle_preview(method, parsed.query)
        trimmed = parsed.path[len(LESSON_DELIVERY_API_PREFIX) :].strip("/")
        try:
            if method == "POST" and not trimmed:
                return 201, self.receive(payload)
            if method == "GET" and not trimmed:
                query = parse_qs(parsed.query)
                recipients = query.get("recipient_ref", [])
                return 200, self.list(recipient_ref=recipients[0] if recipients else None)
            if method == "GET" and "/" not in trimmed:
                # Percent-decoded, because delivery_id is an opaque string and
                # opaque includes "/". Reading the raw segment would accept a
                # delivery the boundary could never hand back, which breaks the
                # one promise Stage 1 makes: what was delivered is recoverable.
                return 200, self.get(unquote(trimmed))
        except DuplicateDeliveryError as exc:
            # Distinct from 400: the delivery is well formed, the identity is
            # taken. A sender that retried needs to know which of the two
            # happened.
            return 409, {"error": str(exc)}
        except LessonDeliveryNotFoundError as exc:
            return 404, {"error": str(exc)}
        except (EducationContractError, LessonAssignmentError) as exc:
            # A caller's payload was wrong, and saying how is useful to them.
            return 400, {"error": str(exc)}
        except Exception:
            # Ours, not theirs. Reporting it as 400 would send a caller looking
            # for a mistake in a correct request; the detail stays out of the
            # body, because an unexpected exception's text is not written for
            # whoever is on the other end of a socket.
            return 500, {"error": "internal server error"}
        return 404, {"error": f"unsupported lesson delivery request: {method} {path}"}

    def _handle_preparation(
        self, method: str, query: str, payload: dict[str, Any]
    ) -> tuple[int, dict[str, Any]]:
        """Build one practice bundle, or return a code and nothing else.

        Serialization sits in this handler so a defect while encoding the
        document is the same sanitized 500 as a defect while building it.
        """

        if method != "POST":
            return 405, {"error": "method not allowed"}
        if query:
            return 400, {"error": "query string is not allowed"}
        try:
            delivery_id, artifact, behavior = _preparation_body(payload)
        except _ChoiceRequestError as exc:
            return 400, {"error": str(exc)}
        try:
            prepared = self._preparations().prepare(delivery_id, artifact, behavior)
            return 200, preparation_to_dict(prepared)
        except UnknownPracticeChoiceError:
            return 404, {"error": "unknown_practice_choice"}
        except LessonDeliveryNotFoundError:
            return 404, {"error": "unknown_delivery_id"}
        except DeliveryIntegrityError:
            return 409, {"error": "integrity_mismatch"}
        except StalePreviewError:
            return 409, {"error": "stale_preview"}
        except UnresolvableAssignmentError:
            return 422, {"error": "unresolvable_assignment"}
        except UnsupportedInstrumentError:
            return 422, {"error": "unsupported_instrument"}
        except UnpreparableAssignmentError:
            return 422, {"error": "unpreparable_assignment"}
        except PreparationFailure:
            return 500, {"error": "internal server error"}
        except Exception:
            return 500, {"error": "internal server error"}

    def _handle_preview(self, method: str, query: str) -> tuple[int, dict[str, Any]]:
        """Select one delivery and return its read-only summary, or an error.

        The body is not a preview. A failure returns a code and no lesson fields,
        so a caller cannot treat a rejected inspection as a partial lesson.
        """

        if method != "GET":
            return 405, {"error": "method not allowed"}
        try:
            delivery_id = _single_delivery_id(query)
        except _PreviewQueryError as exc:
            return 400, {"error": str(exc)}
        try:
            preview = LessonDeliveryPreviewService(self.service).preview(delivery_id)
            # Inside the handler so a serializer defect is the sanitized 500,
            # not an exception escaping onto the socket.
            return 200, preview_to_dict(preview)
        except LessonDeliveryNotFoundError as exc:
            return 404, {"error": str(exc)}
        except DeliveryIntegrityError:
            return 409, {"error": "integrity_mismatch"}
        except UnresolvableAssignmentError:
            return 422, {"error": "unresolvable_assignment"}
        except Exception:
            return 500, {"error": "internal server error"}

    def _handle_choice(
        self, method: str, query: str, payload: dict[str, Any]
    ) -> tuple[int, dict[str, Any]]:
        """Record or read one local practice choice.

        Failures are codes and carry no choice fields. GET previews again
        before it will say the choice is still usable, and does not delete it.
        """

        if method not in ("GET", "POST"):
            return 405, {"error": "method not allowed"}
        if method == "POST":
            if query:
                return 400, {"error": "query string is not allowed"}
            try:
                delivery_id, artifact, behavior = _choice_body(payload)
            except _ChoiceRequestError as exc:
                return 400, {"error": str(exc)}
            try:
                choice, created = self._practice_choices().choose(delivery_id, artifact, behavior)
                document = choice_to_dict(choice)
                return (201 if created else 200), document
            except LessonDeliveryNotFoundError:
                return 404, {"error": "unknown_delivery_id"}
            except DeliveryIntegrityError:
                return 409, {"error": "integrity_mismatch"}
            except StalePreviewError:
                return 409, {"error": "stale_preview"}
            except ChoiceConflictError:
                return 409, {"error": "choice_conflict"}
            except UnresolvableAssignmentError:
                return 422, {"error": "unresolvable_assignment"}
            except Exception:
                return 500, {"error": "internal server error"}
        try:
            delivery_id = _single_delivery_id(query)
        except _PreviewQueryError as exc:
            return 400, {"error": str(exc)}
        try:
            choice = self._practice_choices().get(delivery_id)
            return 200, choice_to_dict(choice)
        except UnknownPracticeChoiceError:
            return 404, {"error": "unknown_practice_choice"}
        except LessonDeliveryNotFoundError:
            return 404, {"error": "unknown_delivery_id"}
        except DeliveryIntegrityError:
            return 409, {"error": "integrity_mismatch"}
        except StalePreviewError:
            return 409, {"error": "stale_preview"}
        except UnresolvableAssignmentError:
            return 422, {"error": "unresolvable_assignment"}
        except Exception:
            return 500, {"error": "internal server error"}
