"""What Musical Core answers with.

The result is where Core-minted identity appears. Performance never predicts a document
or revision id; it reads them here.

Partial success is a first-class outcome. A capture with one unmatched note-on and
forty good notes should not be thrown away, but it must not be reported as complete
either — ``status`` and ``rejections`` together say exactly what happened, and
``revision_is_complete_for_input`` answers the one question a caller actually has.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.core.score.errors import (
    ScoreContractError,
    require_bool,
    require_identifier,
    require_nonnegative_int,
    require_optional_identifier,
    require_schema_version,
    require_tuple,
    require_utc_timestamp,
)


class IngestionStatus(StrEnum):
    """How an ingestion ended."""

    ACCEPTED = "accepted"
    ACCEPTED_WITH_REJECTIONS = "accepted_with_rejections"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"


class RejectionReason(StrEnum):
    """Why a source event or a whole request was refused.

    A closed vocabulary rather than free text: a caller has to be able to branch on the
    reason, and generic errors at a public service boundary cannot be handled.
    """

    UNMATCHED_NOTE_ON = "UNMATCHED_NOTE_ON"
    UNMATCHED_NOTE_OFF = "UNMATCHED_NOTE_OFF"
    DURATION_BELOW_ONE_TICK = "DURATION_BELOW_ONE_TICK"
    EVENT_BEFORE_CAPTURE_ORIGIN = "EVENT_BEFORE_CAPTURE_ORIGIN"
    UNSUPPORTED_CAPTURE_TYPE = "UNSUPPORTED_CAPTURE_TYPE"
    INVALID_TEMPO_MAP = "INVALID_TEMPO_MAP"
    INVALID_METER_MAP = "INVALID_METER_MAP"
    INGESTION_IDEMPOTENCY_CONFLICT = "INGESTION_IDEMPOTENCY_CONFLICT"
    NO_CONVERTIBLE_EVENTS = "NO_CONVERTIBLE_EVENTS"


class IngestionWarningCode(StrEnum):
    """Something worth reporting that did not stop the ingestion."""

    ROUNDING_APPLIED = "ROUNDING_APPLIED"
    SOURCE_STRING_UNRESOLVED = "SOURCE_STRING_UNRESOLVED"
    CHANNEL_NOT_MAPPED_TO_VOICE = "CHANNEL_NOT_MAPPED_TO_VOICE"


@dataclass(frozen=True)
class IngestionRejectionV1:
    """One source event, or one request, that could not be ingested."""

    schema_version: str
    reason: RejectionReason
    detail: str
    source_event_ids: tuple[str, ...] = ()

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        if not isinstance(self.reason, RejectionReason):
            raise ScoreContractError("reason must be a RejectionReason")
        require_identifier(self.detail, "detail")
        require_tuple(self.source_event_ids, "source_event_ids")
        for source_id in self.source_event_ids:
            require_identifier(source_id, "source_event_ids entry")


@dataclass(frozen=True)
class IngestionWarningV1:
    """Something the caller should know that did not prevent ingestion."""

    schema_version: str
    code: IngestionWarningCode
    detail: str
    source_event_ids: tuple[str, ...] = ()

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        if not isinstance(self.code, IngestionWarningCode):
            raise ScoreContractError("code must be an IngestionWarningCode")
        require_identifier(self.detail, "detail")
        require_tuple(self.source_event_ids, "source_event_ids")
        for source_id in self.source_event_ids:
            require_identifier(source_id, "source_event_ids entry")


@dataclass(frozen=True)
class CanonicalIngestionResultV1:
    """Musical Core's answer to an ingestion request."""

    schema_version: str
    request_id: str
    status: IngestionStatus
    source_capture_id: str
    source_capture_digest: str
    policy_version: str
    completed_at: str
    document_id: str | None = None
    revision_id: str | None = None
    created_new_document: bool = False
    created_new_revision: bool = False
    accepted_event_count: int = 0
    rejected_event_count: int = 0
    warnings: tuple[IngestionWarningV1, ...] = ()
    rejections: tuple[IngestionRejectionV1, ...] = ()

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.request_id, "request_id")
        if not isinstance(self.status, IngestionStatus):
            raise ScoreContractError("status must be an IngestionStatus")
        require_identifier(self.source_capture_id, "source_capture_id")
        require_identifier(self.source_capture_digest, "source_capture_digest")
        require_identifier(self.policy_version, "policy_version")
        require_utc_timestamp(self.completed_at, "completed_at")
        require_optional_identifier(self.document_id, "document_id")
        require_optional_identifier(self.revision_id, "revision_id")
        require_bool(self.created_new_document, "created_new_document")
        require_bool(self.created_new_revision, "created_new_revision")
        require_nonnegative_int(self.accepted_event_count, "accepted_event_count")
        require_nonnegative_int(self.rejected_event_count, "rejected_event_count")

        require_tuple(self.warnings, "warnings")
        for warning in self.warnings:
            if not isinstance(warning, IngestionWarningV1):
                raise ScoreContractError("warnings must contain IngestionWarningV1 values")
        require_tuple(self.rejections, "rejections")
        for rejection in self.rejections:
            if not isinstance(rejection, IngestionRejectionV1):
                raise ScoreContractError("rejections must contain IngestionRejectionV1 values")

        self._validate_status_agreement()

    def _validate_status_agreement(self) -> None:
        succeeded = self.status in (
            IngestionStatus.ACCEPTED,
            IngestionStatus.ACCEPTED_WITH_REJECTIONS,
            IngestionStatus.DUPLICATE,
        )
        if succeeded and (self.document_id is None or self.revision_id is None):
            raise ScoreContractError(
                f"status {self.status} requires both document_id and revision_id"
            )
        if self.status is IngestionStatus.REJECTED:
            if self.revision_id is not None:
                raise ScoreContractError("a rejected ingestion must not name a revision")
            if not self.rejections:
                raise ScoreContractError("a rejected ingestion must say why")
        # The distinction between clean and partial acceptance is the whole reason a
        # caller reads this field, so it may not disagree with the rejection list.
        if self.status is IngestionStatus.ACCEPTED and self.rejections:
            raise ScoreContractError(
                "status ACCEPTED cannot carry rejections; use ACCEPTED_WITH_REJECTIONS"
            )
        if self.status is IngestionStatus.ACCEPTED_WITH_REJECTIONS and not self.rejections:
            raise ScoreContractError(
                "status ACCEPTED_WITH_REJECTIONS requires at least one rejection"
            )
        if self.status is IngestionStatus.DUPLICATE and self.created_new_revision:
            raise ScoreContractError("a duplicate ingestion cannot have created a revision")
        if len(self.rejections) and self.rejected_event_count == 0:
            raise ScoreContractError(
                "rejected_event_count must account for the reported rejections"
            )

    @property
    def succeeded(self) -> bool:
        """Whether a revision exists for this request."""
        return self.revision_id is not None

    @property
    def revision_is_complete_for_input(self) -> bool:
        """Whether every source event reached the revision.

        The question a caller actually has after a partial ingestion.
        """
        return self.succeeded and not self.rejections

    def rejection_reasons(self) -> tuple[str, ...]:
        """The distinct reasons events were refused, in first-seen order."""
        seen: list[str] = []
        for rejection in self.rejections:
            if rejection.reason.value not in seen:
                seen.append(rejection.reason.value)
        return tuple(seen)
