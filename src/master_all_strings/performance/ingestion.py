"""Building the Musical Core ingestion request from a closed capture.

Performance's whole job at this seam is to restate what it observed in the Core-owned
neutral form and hand it over. It does not create a document, a revision, or an
identity of any kind, and after DO-007 the request has no revision field it could
populate even by accident.

Only note-on and note-off events cross. Controller, pitch-bend, program-change, and
channel-pressure events stay in the raw capture, which is untouched: ``DIRECT_EVENT_IMPORT_V1``
has no canonical representation for them, and silently dropping them into a
"converted" pile would misreport what was ingested.
"""

from __future__ import annotations

from master_all_strings.core.ingestion.contracts import (
    CanonicalIngestionRequestV1,
    ProjectionType,
    SourceMidiEventKind,
    SourceMidiEventV1,
)
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.tempo import tempo_from_bpm
from master_all_strings.performance.contracts.capture import (
    MidiEventType,
    RawPerformanceCaptureV1,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.export import capture_digest

DEFAULT_PROJECTIONS = (
    ProjectionType.PIANO_ROLL,
    ProjectionType.NOTATION,
    ProjectionType.TAB,
)

_PAIRABLE = {
    MidiEventType.NOTE_ON: SourceMidiEventKind.NOTE_ON,
    MidiEventType.NOTE_OFF: SourceMidiEventKind.NOTE_OFF,
}


def build_source_events(
    capture: RawPerformanceCaptureV1,
) -> tuple[SourceMidiEventV1, ...]:
    """Restate a capture's note events in the Core-owned neutral form.

    The raw capture is read, never modified. Observed string identity is carried
    through unchanged and is never inferred where the source did not report it.
    """
    events: list[SourceMidiEventV1] = []
    for event in capture.events:
        kind = _PAIRABLE.get(event.event_type)
        if kind is None or event.note is None:
            continue
        events.append(
            SourceMidiEventV1(
                schema_version=SourceMidiEventV1.SCHEMA_VERSION,
                source_event_id=event.event_id,
                kind=kind,
                capture_time_ns=event.capture_time_ns,
                channel=event.channel,
                midi_note=event.note,
                velocity=event.velocity if event.velocity is not None else 0,
                observed_source_string=event.source_string,
            )
        )
    return tuple(events)


def build_ingestion_request(
    capture: RawPerformanceCaptureV1,
    *,
    request_id: str,
    requested_at: str,
    beats_per_minute: float,
    beats_per_bar: int = 4,
    beat_unit: int = 4,
    instrument_profile_id: str | None = None,
    tuning_profile_id: str | None = None,
    projections: tuple[ProjectionType, ...] = DEFAULT_PROJECTIONS,
    capture_origin_ns: int | None = None,
) -> CanonicalIngestionRequestV1:
    """Build the request for a closed capture.

    Requires a closed capture: ingesting one still in progress would ask Core to mint a
    revision for a record that can still change.

    ``capture_origin_ns`` defaults to the earliest event timestamp. ``RawPerformanceCaptureV1``
    records ``started_at`` as ISO wall clock and carries no monotonic origin, so the
    first event is the only origin the capture actually evidences; a caller with a real
    recorded origin should pass it.
    """
    if not capture.is_closed:
        raise PerformanceContractError(
            f"capture {capture.capture_id!r} is still IN_PROGRESS; "
            "close it before requesting canonical ingestion"
        )
    source_events = build_source_events(capture)
    if capture_origin_ns is None:
        capture_origin_ns = min(
            (event.capture_time_ns for event in source_events), default=0
        )
    return CanonicalIngestionRequestV1(
        schema_version=CanonicalIngestionRequestV1.SCHEMA_VERSION,
        request_id=request_id,
        capture_id=capture.capture_id,
        source_session_id=capture.session_id,
        raw_capture_digest=capture_digest(capture),
        capture_origin_ns=capture_origin_ns,
        tempo_microseconds_per_quarter=tempo_from_bpm(
            beats_per_minute
        ).microseconds_per_quarter,
        meter=MeterChangeV1(
            schema_version=MeterChangeV1.SCHEMA_VERSION,
            tick=0,
            numerator=beats_per_bar,
            denominator=beat_unit,
        ),
        requested_at=requested_at,
        source_events=source_events,
        instrument_profile_id=instrument_profile_id,
        tuning_profile_id=tuning_profile_id,
        requested_projection_types=projections,
    )
