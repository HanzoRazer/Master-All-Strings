"""The real ingestion seam.

Turns a Performance-produced request into a Musical Core document and revision, and
answers with Core-minted identity. This is what replaces the DO-006 test double in the
end-to-end proof.

Idempotency is keyed on a **request fingerprint**: a digest over every field that
changes what the ingestion produces. Repeating an identical request returns the existing
result rather than creating a second document. Reusing a ``request_id`` with any
different result-affecting field is refused: one name meaning two things is a defect,
not a new version, and accepting it would make the request id useless as a retry key.

The fingerprint covers more than the capture digest, and it has to. The capture digest
says which take was played; it says nothing about the tempo, meter, tick grid, or
capture origin the caller asked Core to interpret that take under, and those change the
canonical revision the ingestion produces. Keying on the capture digest alone meant that
replaying one capture under a corrected tempo returned the *first* revision as a
duplicate — silently, with the stale identity, and with no signal that the corrected
tempo had been discarded.

The source events are fingerprinted too, rather than trusted to follow the capture
digest. ``raw_capture_digest`` is a value the caller asserts; the events are what Core
actually converts. Deriving identity from what was submitted keeps the two from
disagreeing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from master_all_strings.core.ingestion.contracts import (
    CanonicalIngestionRequestV1,
    SourceMidiEventV1,
)
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


def _source_events_digest(events: tuple[SourceMidiEventV1, ...]) -> str:
    """Digest the source events exactly as submitted.

    Not sorted first. ``DIRECT_EVENT_IMPORT_V1`` breaks equal-timestamp ties by
    submitted order, so two orderings of the same events can pair differently and are
    not the same request.
    """
    payload = json.dumps(
        [
            [
                event.source_event_id,
                event.kind.value,
                event.capture_time_ns,
                event.channel,
                event.midi_note,
                event.velocity,
                event.observed_source_string,
            ]
            for event in events
        ],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fingerprint_fields(request: CanonicalIngestionRequestV1) -> dict[str, str]:
    """Every field of ``request`` that changes what the ingestion produces.

    Named and returned as a mapping rather than folded straight into a hash so a
    conflict can say *which* field changed, and so a test can assert the policy instead
    of re-deriving it from behaviour.

    Excluded deliberately: ``requested_at``, because a retry may legitimately restamp it
    and letting that split the key would defeat retry safety; ``source_session_id``,
    ``instrument_profile_id``, ``tuning_profile_id``, and
    ``requested_projection_types``, because none of them reach the revision or the
    result. When a profile or a projection request starts affecting what Core stores, it
    belongs in this list on the same day.
    """
    return {
        "capture_id": request.capture_id,
        "raw_capture_digest": request.raw_capture_digest,
        "capture_origin_ns": str(request.capture_origin_ns),
        "tempo_microseconds_per_quarter": str(request.tempo_microseconds_per_quarter),
        "meter": (
            f"{request.meter.tick}:"
            f"{request.meter.numerator}/{request.meter.denominator}"
        ),
        "ticks_per_quarter": str(request.ticks_per_quarter or DEFAULT_TICKS_PER_QUARTER),
        "policy_version": POLICY_VERSION,
        "source_events": _source_events_digest(request.source_events),
    }


def request_fingerprint(request: CanonicalIngestionRequestV1) -> str:
    """Return the digest of a request's result-affecting fields."""
    payload = json.dumps(
        [[name, value] for name, value in fingerprint_fields(request).items()],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _RequestIdentity:
    """What a ``request_id`` was taken to mean the first time it was seen."""

    fingerprint: str
    fields: tuple[tuple[str, str], ...]

    @classmethod
    def of(cls, request: CanonicalIngestionRequestV1) -> _RequestIdentity:
        return cls(
            fingerprint=request_fingerprint(request),
            fields=tuple(fingerprint_fields(request).items()),
        )

    def differing_fields(self, other: _RequestIdentity) -> tuple[str, ...]:
        """The field names on which two identities disagree."""
        theirs = dict(other.fields)
        return tuple(name for name, value in self.fields if theirs.get(name) != value)


class CanonicalIngestionService:
    """Ingests captured performance into canonical revisions.

    ``completed_at`` is supplied by the caller for the same reason the revision service
    takes ``created_at``: reading a clock here would make results irreproducible and
    every test time-dependent.
    """

    def __init__(self, revision_service: CanonicalRevisionService) -> None:
        self._revisions = revision_service
        self._results: dict[str, CanonicalIngestionResultV1] = {}
        self._identities: dict[str, _RequestIdentity] = {}

    def ingest(
        self, request: CanonicalIngestionRequestV1, *, completed_at: str
    ) -> CanonicalIngestionResultV1:
        """Ingest a request, or return the result of an identical earlier one."""
        require_utc_timestamp(completed_at, "completed_at")
        identity = _RequestIdentity.of(request)
        self._require_consistent_request_id(request.request_id, identity)

        existing = self._results.get(request.request_id)
        if existing is not None:
            return self._as_duplicate(existing, completed_at=completed_at)

        # Recorded before the outcome is known, so a rejected request reserves its id
        # too. Otherwise a rejection would leave the id free to be reused for a
        # different capture, and the conflict guard would only work on the happy path.
        self._identities[request.request_id] = identity

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
        self._results[request.request_id] = result
        return result

    def find_result(
        self, *, request_id: str, raw_capture_digest: str
    ) -> CanonicalIngestionResultV1 | None:
        """Return a previously recorded result, or ``None``.

        The digest is matched rather than ignored: a caller asking for a request under
        the wrong capture should get nothing, not somebody else's revision.
        """
        found = self._results.get(request_id)
        if found is None or found.source_capture_digest != raw_capture_digest:
            return None
        return found

    def _require_consistent_request_id(
        self, request_id: str, identity: _RequestIdentity
    ) -> None:
        """Raise unless ``request_id`` still means what it meant the first time."""
        previous = self._identities.get(request_id)
        if previous is None or previous.fingerprint == identity.fingerprint:
            return
        changed = identity.differing_fields(previous)
        raise IngestionIdempotencyConflictError(
            f"INGESTION_IDEMPOTENCY_CONFLICT: request {request_id!r} was already seen "
            f"with different {', '.join(changed)}; a request id names one ingestion "
            "intent, so issue a new id rather than reusing this one"
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
