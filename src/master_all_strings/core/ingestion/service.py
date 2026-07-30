"""The real ingestion seam.

Turns a Performance-produced request into a Musical Core document and revision, and
answers with Core-minted identity. This is what replaces the DO-006 test double in the
end-to-end proof.

Idempotency is keyed on ``(request_id, raw_capture_digest, policy_version)``. Repeating
an accepted request returns the existing result rather than creating a second document.
Reusing a ``request_id`` with different content is refused: one name meaning two things
is a defect, not a new version, and accepting it would make the request id useless as a
retry key.
"""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.core.ingestion.contracts import CanonicalIngestionRequestV1
from master_all_strings.core.ingestion.policies import (
    POLICY_VERSION,
    import_direct_events,
)
from master_all_strings.core.ingestion.results import (
    CanonicalIngestionResultV1,
    IngestionRejectionV1,
    IngestionStatus,
    RejectionReason,
)
from master_all_strings.core.score.errors import ScoreContractError, require_utc_timestamp
from master_all_strings.core.score.provenance import (
    RevisionProvenanceV1,
    ScoreSourceKind,
)
from master_all_strings.core.score.revision_service import CanonicalRevisionService
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.core.score.timing import DEFAULT_TICKS_PER_QUARTER


class IngestionIdempotencyConflictError(ScoreContractError):
    """INGESTION_IDEMPOTENCY_CONFLICT."""


@dataclass(frozen=True)
class _IdempotencyKey:
    request_id: str
    raw_capture_digest: str
    policy_version: str


class CanonicalIngestionService:
    """Ingests captured performance into canonical revisions.

    ``completed_at`` is supplied by the caller for the same reason the revision service
    takes ``created_at``: reading a clock here would make results irreproducible and
    every test time-dependent.
    """

    def __init__(self, revision_service: CanonicalRevisionService) -> None:
        self._revisions = revision_service
        self._results: dict[_IdempotencyKey, CanonicalIngestionResultV1] = {}
        self._seen_request_ids: dict[str, str] = {}

    def ingest(
        self, request: CanonicalIngestionRequestV1, *, completed_at: str
    ) -> CanonicalIngestionResultV1:
        """Ingest a request, or return the result of an identical earlier one."""
        require_utc_timestamp(completed_at, "completed_at")
        key = _IdempotencyKey(
            request_id=request.request_id,
            raw_capture_digest=request.raw_capture_digest,
            policy_version=POLICY_VERSION,
        )

        existing = self._results.get(key)
        if existing is not None:
            return self._as_duplicate(existing, completed_at=completed_at)

        previous_digest = self._seen_request_ids.get(request.request_id)
        if previous_digest is not None and previous_digest != request.raw_capture_digest:
            # One request id meaning two captures makes the id useless as a retry key.
            raise IngestionIdempotencyConflictError(
                f"INGESTION_IDEMPOTENCY_CONFLICT: request {request.request_id!r} was seen "
                f"with capture digest {previous_digest!r} and is now {request.raw_capture_digest!r}"
            )

        outcome = import_direct_events(request)

        if not outcome.events:
            return self._rejected(
                request,
                completed_at=completed_at,
                rejections=outcome.rejections
                or (
                    IngestionRejectionV1(
                        schema_version=IngestionRejectionV1.SCHEMA_VERSION,
                        reason=RejectionReason.NO_CONVERTIBLE_EVENTS,
                        detail="the request carried no events this policy can convert",
                    ),
                ),
            )

        provenance = RevisionProvenanceV1(
            schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
            source_kind=ScoreSourceKind.PERFORMANCE_CAPTURE,
            policy_version=POLICY_VERSION,
            source_reference=request.capture_id,
            event_provenance=outcome.event_provenance,
        )
        creation = self._revisions.create_document_with_revision(
            created_at=completed_at,
            provenance=provenance,
            events=outcome.events,
            tempo_changes=(
                TempoChangeV1(
                    schema_version=TempoChangeV1.SCHEMA_VERSION,
                    tick=0,
                    microseconds_per_quarter=request.tempo_microseconds_per_quarter,
                ),
            ),
            meter_changes=(request.meter,),
            ticks_per_quarter=request.ticks_per_quarter or DEFAULT_TICKS_PER_QUARTER,
            external_reference=request.capture_id,
        )

        result = CanonicalIngestionResultV1(
            schema_version=CanonicalIngestionResultV1.SCHEMA_VERSION,
            request_id=request.request_id,
            status=(
                IngestionStatus.ACCEPTED_WITH_REJECTIONS
                if outcome.rejections
                else IngestionStatus.ACCEPTED
            ),
            source_capture_id=request.capture_id,
            source_capture_digest=request.raw_capture_digest,
            policy_version=POLICY_VERSION,
            completed_at=completed_at,
            document_id=creation.document.document_id,
            revision_id=creation.revision.revision_id,
            created_new_document=True,
            created_new_revision=True,
            accepted_event_count=outcome.accepted_count,
            rejected_event_count=outcome.rejected_count,
            warnings=outcome.warnings,
            rejections=outcome.rejections,
        )
        self._results[key] = result
        self._seen_request_ids[request.request_id] = request.raw_capture_digest
        return result

    def find_result(
        self, *, request_id: str, raw_capture_digest: str
    ) -> CanonicalIngestionResultV1 | None:
        """Return a previously recorded result, or ``None``."""
        return self._results.get(
            _IdempotencyKey(
                request_id=request_id,
                raw_capture_digest=raw_capture_digest,
                policy_version=POLICY_VERSION,
            )
        )

    def _as_duplicate(
        self, existing: CanonicalIngestionResultV1, *, completed_at: str
    ) -> CanonicalIngestionResultV1:
        """Report an earlier result as a duplicate without creating anything."""
        return CanonicalIngestionResultV1(
            schema_version=existing.schema_version,
            request_id=existing.request_id,
            status=IngestionStatus.DUPLICATE,
            source_capture_id=existing.source_capture_id,
            source_capture_digest=existing.source_capture_digest,
            policy_version=existing.policy_version,
            completed_at=completed_at,
            document_id=existing.document_id,
            revision_id=existing.revision_id,
            created_new_document=False,
            created_new_revision=False,
            accepted_event_count=existing.accepted_event_count,
            rejected_event_count=existing.rejected_event_count,
            warnings=existing.warnings,
            rejections=existing.rejections,
        )

    def _rejected(
        self,
        request: CanonicalIngestionRequestV1,
        *,
        completed_at: str,
        rejections: tuple[IngestionRejectionV1, ...],
    ) -> CanonicalIngestionResultV1:
        rejected_count = sum(len(r.source_event_ids) for r in rejections)
        return CanonicalIngestionResultV1(
            schema_version=CanonicalIngestionResultV1.SCHEMA_VERSION,
            request_id=request.request_id,
            status=IngestionStatus.REJECTED,
            source_capture_id=request.capture_id,
            source_capture_digest=request.raw_capture_digest,
            policy_version=POLICY_VERSION,
            completed_at=completed_at,
            rejected_event_count=max(rejected_count, 1),
            rejections=rejections,
        )
