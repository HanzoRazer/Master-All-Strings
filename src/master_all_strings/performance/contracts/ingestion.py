"""The Performance-to-Musical-Core handoff.

``CanonicalIngestionRequestV1`` is **owned by Musical Core and produced by
Performance**. That asymmetry is deliberate and mirrors ``ScoreEditCommandSet``,
which Creative produces and Core owns: the engine that owns the canonical model owns
the vocabulary for changing it, even when another engine speaks it.

The rule this module exists to enforce (ADR-0007 D5):

* Performance **may** reference a ``canonical_revision_id`` after Musical Core
  supplies one.
* Performance **may not** mint one.
* Performance **may not** treat a runtime session id as one.
* Performance **may not** implement a competing revision model.

Musical Core has no score-document or revision implementation yet, so this contract
is the whole of the seam in this tranche. The request carries a capture digest rather
than the capture itself: Core is told what to ingest and can verify it received the
record it was promised, without Performance handing over a mutable structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.performance.contracts.errors import (
    PerformanceContractError,
    require_identifier,
    require_schema_version,
    require_tuple,
    require_unique,
    require_utc_timestamp,
)
from master_all_strings.performance.contracts.session import MeterV1


class ProjectionType(StrEnum):
    """Which Musical Core projections the requester wants from the revision.

    Piano roll sits beside notation and TAB because it is the same kind of thing: a
    projection of one canonical revision, not a second score model (ADR-0007 D8).
    """

    PIANO_ROLL = "piano_roll"
    NOTATION = "notation"
    TAB = "tab"
    MIDI = "midi"


@dataclass(frozen=True)
class CanonicalIngestionRequestV1:
    """Ask Musical Core to ingest a closed capture.

    ``canonical_revision_id`` is ``None`` on the outbound request and populated only
    from Core's answer. A request that arrives with one already set is either a replay
    or a Performance component minting identity it does not own, and both are refused.
    """

    schema_version: str
    request_id: str
    capture_id: str
    source_session_id: str
    raw_capture_digest: str
    instrument_profile_id: str
    tuning_profile_id: str
    tempo_context: float
    meter_context: MeterV1
    requested_projection_types: tuple[ProjectionType, ...]
    requested_at: str
    canonical_revision_id: str | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.request_id, "request_id")
        require_identifier(self.capture_id, "capture_id")
        require_identifier(self.source_session_id, "source_session_id")
        require_identifier(self.raw_capture_digest, "raw_capture_digest")
        require_identifier(self.instrument_profile_id, "instrument_profile_id")
        require_identifier(self.tuning_profile_id, "tuning_profile_id")
        require_utc_timestamp(self.requested_at, "requested_at")

        if isinstance(self.tempo_context, bool) or not isinstance(
            self.tempo_context, (int, float)
        ):
            raise PerformanceContractError("tempo_context must be a number")
        if not isinstance(self.meter_context, MeterV1):
            raise PerformanceContractError("meter_context must be a MeterV1")

        require_tuple(self.requested_projection_types, "requested_projection_types")
        if not self.requested_projection_types:
            raise PerformanceContractError("requested_projection_types must not be empty")
        for projection in self.requested_projection_types:
            if not isinstance(projection, ProjectionType):
                raise PerformanceContractError(
                    "requested_projection_types must contain ProjectionType values"
                )
        require_unique(self.requested_projection_types, "requested_projection_types")

        if self.canonical_revision_id is not None:
            require_identifier(self.canonical_revision_id, "canonical_revision_id")
            # A revision id equal to the session id means someone reached for the
            # nearest available identifier instead of asking Core for one.
            if self.canonical_revision_id == self.source_session_id:
                raise PerformanceContractError(
                    "canonical_revision_id must not be the runtime session id; "
                    "Performance may reference a revision but never mint one"
                )

    def with_revision(self, canonical_revision_id: str) -> CanonicalIngestionRequestV1:
        """Return a copy carrying the revision id Musical Core supplied.

        The only sanctioned way for a revision id to enter a Performance record.
        Refuses to overwrite an existing id, so a second Core answer cannot silently
        replace the first.
        """
        require_identifier(canonical_revision_id, "canonical_revision_id")
        if self.canonical_revision_id is not None:
            raise PerformanceContractError(
                "canonical_revision_id is already set and may not be replaced"
            )
        return CanonicalIngestionRequestV1(
            schema_version=self.schema_version,
            request_id=self.request_id,
            capture_id=self.capture_id,
            source_session_id=self.source_session_id,
            raw_capture_digest=self.raw_capture_digest,
            instrument_profile_id=self.instrument_profile_id,
            tuning_profile_id=self.tuning_profile_id,
            tempo_context=self.tempo_context,
            meter_context=self.meter_context,
            requested_projection_types=self.requested_projection_types,
            requested_at=self.requested_at,
            canonical_revision_id=canonical_revision_id,
        )
