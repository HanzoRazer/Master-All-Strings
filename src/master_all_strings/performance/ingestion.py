"""Building the Performance-to-Musical-Core handoff.

The whole of the seam in this tranche. Musical Core has no score-document or revision
implementation yet, so this module produces the request and stops. It never produces
a revision, and there is deliberately no function here that could.
"""

from __future__ import annotations

from master_all_strings.performance.contracts.capture import RawPerformanceCaptureV1
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.ingestion import (
    CanonicalIngestionRequestV1,
    ProjectionType,
)
from master_all_strings.performance.export import capture_digest

DEFAULT_PROJECTIONS = (
    ProjectionType.PIANO_ROLL,
    ProjectionType.NOTATION,
    ProjectionType.TAB,
)


def build_ingestion_request(
    capture: RawPerformanceCaptureV1,
    *,
    request_id: str,
    instrument_profile_id: str,
    tuning_profile_id: str,
    requested_at: str,
    projections: tuple[ProjectionType, ...] = DEFAULT_PROJECTIONS,
) -> CanonicalIngestionRequestV1:
    """Build the ingestion request for a closed capture.

    Requires a closed capture: ingesting a take still in progress would ask Musical
    Core to mint a revision for a record that can still change.

    The request carries a content digest rather than the capture itself, so Core can
    verify it received the record it was promised and Performance keeps the evidence.
    """
    if not capture.is_closed:
        raise PerformanceContractError(
            f"capture {capture.capture_id!r} is still IN_PROGRESS; "
            "close it before requesting canonical ingestion"
        )
    return CanonicalIngestionRequestV1(
        schema_version=CanonicalIngestionRequestV1.SCHEMA_VERSION,
        request_id=request_id,
        capture_id=capture.capture_id,
        source_session_id=capture.session_id,
        raw_capture_digest=capture_digest(capture),
        instrument_profile_id=instrument_profile_id,
        tuning_profile_id=tuning_profile_id,
        tempo_context=capture.tempo_context,
        meter_context=capture.meter_context,
        requested_projection_types=projections,
        requested_at=requested_at,
        canonical_revision_id=None,
    )
