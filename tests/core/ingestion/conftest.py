"""Fixtures for canonical ingestion tests. Deterministic throughout."""

from __future__ import annotations

import pytest

from master_all_strings.core.ingestion.contracts import (
    CanonicalIngestionRequestV1,
    SourceMidiEventKind,
    SourceMidiEventV1,
)
from master_all_strings.core.ingestion.service import CanonicalIngestionService
from master_all_strings.core.score.ids import DeterministicDocumentIdAuthority
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.repository import InMemoryCanonicalScoreRepository
from master_all_strings.core.score.revision_service import CanonicalRevisionService

T0 = "2026-07-30T10:00:00Z"
MPQ_120 = 500_000
NS_PER_QUARTER = 500_000_000
METER_4_4 = MeterChangeV1(
    schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=4, denominator=4
)


def source_event(
    index: int,
    kind: SourceMidiEventKind,
    time_ns: int,
    *,
    channel: int = 0,
    midi_note: int = 60,
    velocity: int = 90,
    observed_source_string: int | None = None,
) -> SourceMidiEventV1:
    return SourceMidiEventV1(
        schema_version=SourceMidiEventV1.SCHEMA_VERSION,
        source_event_id=f"src-{index:04d}",
        kind=kind,
        capture_time_ns=time_ns,
        channel=channel,
        midi_note=midi_note,
        velocity=velocity,
        observed_source_string=observed_source_string,
    )


def note(
    index: int,
    *,
    onset_ns: int = 0,
    release_ns: int = NS_PER_QUARTER,
    midi_note: int = 60,
    velocity: int = 90,
    channel: int = 0,
    observed_source_string: int | None = None,
) -> tuple[SourceMidiEventV1, SourceMidiEventV1]:
    """A matched note-on/note-off pair."""
    return (
        source_event(
            index * 2,
            SourceMidiEventKind.NOTE_ON,
            onset_ns,
            channel=channel,
            midi_note=midi_note,
            velocity=velocity,
            observed_source_string=observed_source_string,
        ),
        source_event(
            index * 2 + 1,
            SourceMidiEventKind.NOTE_OFF,
            release_ns,
            channel=channel,
            midi_note=midi_note,
            velocity=0,
            observed_source_string=observed_source_string,
        ),
    )


def make_request(
    *,
    request_id: str = "req-0001",
    capture_id: str = "capture-0001",
    digest: str = "sha256:abc123",
    source_events: tuple[SourceMidiEventV1, ...] = (),
    capture_origin_ns: int = 0,
    mpq: int = MPQ_120,
    ticks_per_quarter: int | None = None,
) -> CanonicalIngestionRequestV1:
    return CanonicalIngestionRequestV1(
        schema_version=CanonicalIngestionRequestV1.SCHEMA_VERSION,
        request_id=request_id,
        capture_id=capture_id,
        source_session_id="session-0001",
        raw_capture_digest=digest,
        capture_origin_ns=capture_origin_ns,
        tempo_microseconds_per_quarter=mpq,
        meter=METER_4_4,
        requested_at=T0,
        source_events=source_events,
        instrument_profile_id="guitar-standard-6",
        tuning_profile_id="standard-e",
        ticks_per_quarter=ticks_per_quarter,
    )


@pytest.fixture
def repository() -> InMemoryCanonicalScoreRepository:
    return InMemoryCanonicalScoreRepository()


@pytest.fixture
def service(repository: InMemoryCanonicalScoreRepository) -> CanonicalIngestionService:
    return CanonicalIngestionService(
        CanonicalRevisionService(repository, DeterministicDocumentIdAuthority())
    )
