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
    400  malformed, or digests that do not recompute
         (a delivery_id is percent-encoded in the path: it is opaque, and
         opaque includes characters that mean something in a URL)
    409  a delivery identity already used
    404  no such delivery
    500  a defect in this application, reported without detail
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from master_all_strings.education.assignment_delivery import LessonDeliverySummaryV1
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
from master_all_strings.lesson.errors import LessonAssignmentError

__all__ = [
    "LESSON_DELIVERY_API_PREFIX",
    "LocalLessonDeliveryApi",
]

LESSON_DELIVERY_API_PREFIX = "/api/education/lesson-deliveries"


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

    Receiving stores an envelope and stops there. Nothing in this class
    resolves music, starts playback, evaluates a learner or opens a guided
    session, and a request that arrives here must not be able to cause any of
    those as a side effect.
    """

    service: LessonDeliveryService = field(default_factory=LessonDeliveryService)

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
