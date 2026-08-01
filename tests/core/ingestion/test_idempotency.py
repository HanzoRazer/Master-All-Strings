"""Ingestion service and idempotency (DO-007A A5).

Retry safety is the property that makes ingestion usable from a device that may lose a
response. These tests fix that a repeat is free and a collision is loud.
"""

from __future__ import annotations

import pytest

from conftest import (  # type: ignore[import-not-found]
    METER_4_4,
    MPQ_120,
    NS_PER_QUARTER,
    T0,
    make_request,
    note,
    source_event,
)
from master_all_strings.core.ingestion.contracts import (
    CanonicalIngestionRequestV1,
    SourceMidiEventKind,
)
from master_all_strings.core.ingestion.results import IngestionStatus, RejectionReason
from master_all_strings.core.ingestion.service import (
    CanonicalIngestionService,
    IngestionIdempotencyConflictError,
    fingerprint_fields,
    request_fingerprint,
)
from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.repository import InMemoryCanonicalScoreRepository

LATER = "2026-07-30T11:00:00Z"
METER_3_4 = MeterChangeV1(
    schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=3, denominator=4
)


class TestFirstIngestion:
    def test_a_clean_capture_is_accepted(self, service: CanonicalIngestionService) -> None:
        result = service.ingest(make_request(source_events=note(0)), completed_at=T0)
        assert result.status is IngestionStatus.ACCEPTED
        assert result.created_new_document is True
        assert result.created_new_revision is True

    def test_core_mints_both_identities(self, service: CanonicalIngestionService) -> None:
        result = service.ingest(make_request(source_events=note(0)), completed_at=T0)
        assert result.document_id is not None
        assert result.revision_id is not None
        assert result.revision_id.startswith("rev-")

    def test_the_revision_is_stored(
        self, service: CanonicalIngestionService, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        result = service.ingest(make_request(source_events=note(0)), completed_at=T0)
        assert result.document_id is not None
        revision = repository.get_current_revision(result.document_id)
        assert revision.revision_id == result.revision_id
        assert revision.event_count == 1

    def test_the_capture_is_cited_in_provenance(
        self, service: CanonicalIngestionService, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        result = service.ingest(
            make_request(source_events=note(0), capture_id="capture-xyz"), completed_at=T0
        )
        assert result.document_id is not None
        provenance = repository.get_current_revision(result.document_id).provenance
        assert provenance.source_reference == "capture-xyz"
        assert provenance.policy_version == "DIRECT_EVENT_IMPORT_V1"

    def test_counts_are_reported(self, service: CanonicalIngestionService) -> None:
        events = note(0) + note(1, onset_ns=NS_PER_QUARTER, release_ns=NS_PER_QUARTER * 2)
        result = service.ingest(make_request(source_events=events), completed_at=T0)
        assert result.accepted_event_count == 2
        assert result.rejected_event_count == 0
        assert result.revision_is_complete_for_input is True


class TestPartialAcceptance:
    def test_a_partial_capture_still_produces_a_revision(
        self, service: CanonicalIngestionService
    ) -> None:
        # Forty good notes should not be thrown away because one was never released.
        events = note(0) + (source_event(9, SourceMidiEventKind.NOTE_ON, 0, midi_note=67),)
        result = service.ingest(make_request(source_events=events), completed_at=T0)
        assert result.status is IngestionStatus.ACCEPTED_WITH_REJECTIONS
        assert result.succeeded is True

    def test_a_partial_capture_is_not_reported_complete(
        self, service: CanonicalIngestionService
    ) -> None:
        events = note(0) + (source_event(9, SourceMidiEventKind.NOTE_ON, 0, midi_note=67),)
        result = service.ingest(make_request(source_events=events), completed_at=T0)
        assert result.revision_is_complete_for_input is False
        assert RejectionReason.UNMATCHED_NOTE_ON.value in result.rejection_reasons()

    def test_a_capture_with_nothing_convertible_is_rejected(
        self, service: CanonicalIngestionService
    ) -> None:
        events = (source_event(0, SourceMidiEventKind.NOTE_ON, 0),)
        result = service.ingest(make_request(source_events=events), completed_at=T0)
        assert result.status is IngestionStatus.REJECTED
        assert result.revision_id is None
        assert result.succeeded is False

    def test_an_empty_request_is_rejected_with_a_reason(
        self, service: CanonicalIngestionService
    ) -> None:
        result = service.ingest(make_request(source_events=()), completed_at=T0)
        assert result.status is IngestionStatus.REJECTED
        assert RejectionReason.NO_CONVERTIBLE_EVENTS.value in result.rejection_reasons()

    def test_a_rejected_ingestion_creates_nothing(
        self, service: CanonicalIngestionService, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        service.ingest(make_request(source_events=()), completed_at=T0)
        assert repository.has_document("score-test-0001") is False


class TestIdempotency:
    def test_repeating_a_request_returns_the_existing_result(
        self, service: CanonicalIngestionService
    ) -> None:
        request = make_request(source_events=note(0))
        first = service.ingest(request, completed_at=T0)
        second = service.ingest(request, completed_at=LATER)
        assert second.status is IngestionStatus.DUPLICATE
        assert second.document_id == first.document_id
        assert second.revision_id == first.revision_id

    def test_a_repeat_creates_no_second_revision(
        self, service: CanonicalIngestionService, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        request = make_request(source_events=note(0))
        first = service.ingest(request, completed_at=T0)
        service.ingest(request, completed_at=LATER)
        service.ingest(request, completed_at=LATER)
        assert first.document_id is not None
        assert len(repository.list_revisions(first.document_id)) == 1

    def test_a_duplicate_reports_creating_nothing(
        self, service: CanonicalIngestionService
    ) -> None:
        request = make_request(source_events=note(0))
        service.ingest(request, completed_at=T0)
        repeat = service.ingest(request, completed_at=LATER)
        assert repeat.created_new_document is False
        assert repeat.created_new_revision is False

    def test_a_duplicate_carries_the_new_timestamp(
        self, service: CanonicalIngestionService
    ) -> None:
        request = make_request(source_events=note(0))
        service.ingest(request, completed_at=T0)
        assert service.ingest(request, completed_at=LATER).completed_at == LATER

    def test_a_reused_request_id_with_new_content_is_refused(
        self, service: CanonicalIngestionService
    ) -> None:
        # One name meaning two captures makes the request id useless as a retry key.
        service.ingest(
            make_request(source_events=note(0), digest="sha256:aaa"), completed_at=T0
        )
        with pytest.raises(
            IngestionIdempotencyConflictError, match="INGESTION_IDEMPOTENCY_CONFLICT"
        ):
            service.ingest(
                make_request(source_events=note(0), digest="sha256:bbb"), completed_at=LATER
            )

    def test_distinct_requests_create_distinct_documents(
        self, service: CanonicalIngestionService
    ) -> None:
        first = service.ingest(
            make_request(request_id="req-1", digest="sha256:a", source_events=note(0)),
            completed_at=T0,
        )
        second = service.ingest(
            make_request(request_id="req-2", digest="sha256:b", source_events=note(0)),
            completed_at=T0,
        )
        assert first.document_id != second.document_id

    def test_a_recorded_result_can_be_found(
        self, service: CanonicalIngestionService
    ) -> None:
        request = make_request(source_events=note(0))
        stored = service.ingest(request, completed_at=T0)
        found = service.find_result(
            request_id=request.request_id, raw_capture_digest=request.raw_capture_digest
        )
        assert found is not None
        assert found.revision_id == stored.revision_id

    def test_an_unknown_result_is_none(self, service: CanonicalIngestionService) -> None:
        assert (
            service.find_result(request_id="req-absent", raw_capture_digest="sha256:x") is None
        )


class TestIdempotencyCoversInterpretation:
    """A request id names one *interpretation* of a capture, not just a capture.

    The capture digest says which take was played. Tempo, meter, tick grid, and capture
    origin say what Core was asked to make of it, and each of them changes the revision.
    Keying only on the capture digest meant a corrected tempo came back as a duplicate
    carrying the uncorrected revision — the wrong answer, reported as a success.
    """

    def test_a_different_tempo_is_not_a_duplicate(
        self, service: CanonicalIngestionService
    ) -> None:
        service.ingest(make_request(source_events=note(0), mpq=500_000), completed_at=T0)
        with pytest.raises(
            IngestionIdempotencyConflictError, match="tempo_microseconds_per_quarter"
        ):
            service.ingest(
                make_request(source_events=note(0), mpq=1_000_000), completed_at=LATER
            )

    def test_a_different_meter_is_not_a_duplicate(
        self, service: CanonicalIngestionService
    ) -> None:
        service.ingest(make_request(source_events=note(0)), completed_at=T0)
        with pytest.raises(IngestionIdempotencyConflictError, match="meter"):
            service.ingest(
                make_request(source_events=note(0), meter=METER_3_4), completed_at=LATER
            )

    def test_a_different_tick_grid_is_not_a_duplicate(
        self, service: CanonicalIngestionService
    ) -> None:
        service.ingest(
            make_request(source_events=note(0), ticks_per_quarter=960), completed_at=T0
        )
        with pytest.raises(IngestionIdempotencyConflictError, match="ticks_per_quarter"):
            service.ingest(
                make_request(source_events=note(0), ticks_per_quarter=480),
                completed_at=LATER,
            )

    def test_an_omitted_tick_grid_matches_the_default(
        self, service: CanonicalIngestionService
    ) -> None:
        # 960 is the default, so naming it and omitting it are the same request.
        service.ingest(make_request(source_events=note(0)), completed_at=T0)
        repeat = service.ingest(
            make_request(source_events=note(0), ticks_per_quarter=960), completed_at=LATER
        )
        assert repeat.status is IngestionStatus.DUPLICATE

    def test_a_different_capture_origin_is_not_a_duplicate(
        self, service: CanonicalIngestionService
    ) -> None:
        events = note(0, onset_ns=1_000_000, release_ns=501_000_000)
        service.ingest(
            make_request(source_events=events, capture_origin_ns=0), completed_at=T0
        )
        with pytest.raises(IngestionIdempotencyConflictError, match="capture_origin_ns"):
            service.ingest(
                make_request(source_events=events, capture_origin_ns=1_000_000),
                completed_at=LATER,
            )

    def test_different_source_events_are_not_a_duplicate(
        self, service: CanonicalIngestionService
    ) -> None:
        # The capture digest is asserted by the caller; the events are what Core
        # converts. Identity follows what was actually submitted.
        service.ingest(make_request(source_events=note(0)), completed_at=T0)
        with pytest.raises(IngestionIdempotencyConflictError, match="source_events"):
            service.ingest(
                make_request(source_events=note(0, midi_note=64)), completed_at=LATER
            )

    def test_a_conflict_names_the_field_that_changed(
        self, service: CanonicalIngestionService
    ) -> None:
        service.ingest(make_request(source_events=note(0)), completed_at=T0)
        with pytest.raises(IngestionIdempotencyConflictError) as caught:
            service.ingest(
                make_request(source_events=note(0), mpq=600_000), completed_at=LATER
            )
        message = str(caught.value)
        assert "tempo_microseconds_per_quarter" in message
        assert "meter" not in message

    def test_a_rejected_request_still_reserves_its_id(
        self, service: CanonicalIngestionService
    ) -> None:
        # A rejection creates nothing, but the id has still been spent. Leaving it free
        # would mean the conflict guard only worked on the happy path.
        rejected = service.ingest(
            make_request(source_events=(), digest="sha256:aaa"), completed_at=T0
        )
        assert rejected.status is IngestionStatus.REJECTED
        with pytest.raises(
            IngestionIdempotencyConflictError, match="INGESTION_IDEMPOTENCY_CONFLICT"
        ):
            service.ingest(
                make_request(source_events=note(0), digest="sha256:bbb"), completed_at=LATER
            )

    def test_repeating_a_rejected_request_is_still_rejected(
        self, service: CanonicalIngestionService
    ) -> None:
        request = make_request(source_events=())
        assert service.ingest(request, completed_at=T0).status is IngestionStatus.REJECTED
        assert service.ingest(request, completed_at=LATER).status is IngestionStatus.REJECTED

    def test_a_repeat_under_a_new_request_id_is_a_distinct_ingestion(
        self, service: CanonicalIngestionService
    ) -> None:
        # The escape hatch a caller with a corrected tempo actually wants.
        first = service.ingest(
            make_request(request_id="req-1", source_events=note(0), mpq=500_000),
            completed_at=T0,
        )
        second = service.ingest(
            make_request(request_id="req-2", source_events=note(0), mpq=1_000_000),
            completed_at=LATER,
        )
        assert second.status is IngestionStatus.ACCEPTED
        assert second.revision_id != first.revision_id

    def test_a_result_is_not_found_under_the_wrong_digest(
        self, service: CanonicalIngestionService
    ) -> None:
        request = make_request(source_events=note(0))
        service.ingest(request, completed_at=T0)
        assert (
            service.find_result(
                request_id=request.request_id, raw_capture_digest="sha256:not-this-one"
            )
            is None
        )


class TestFingerprintPolicy:
    """The fingerprint is asserted directly, not re-derived from behaviour."""

    def test_every_field_that_reaches_the_revision_is_fingerprinted(self) -> None:
        fields = set(fingerprint_fields(make_request(source_events=note(0))))
        assert {
            "capture_id",
            "raw_capture_digest",
            "capture_origin_ns",
            "tempo_microseconds_per_quarter",
            "meter",
            "ticks_per_quarter",
            "policy_version",
            "source_events",
        } == fields

    def test_a_retry_may_restamp_requested_at(
        self, service: CanonicalIngestionService
    ) -> None:
        # requested_at is excluded on purpose: a client that restamps a retry must not
        # be told its own retry is a conflict.
        service.ingest(make_request(source_events=note(0)), completed_at=T0)
        restamped = CanonicalIngestionRequestV1(
            schema_version=CanonicalIngestionRequestV1.SCHEMA_VERSION,
            request_id="req-0001",
            capture_id="capture-0001",
            source_session_id="session-0001",
            raw_capture_digest="sha256:abc123",
            capture_origin_ns=0,
            tempo_microseconds_per_quarter=MPQ_120,
            meter=METER_4_4,
            requested_at=LATER,
            source_events=note(0),
            instrument_profile_id="guitar-standard-6",
            tuning_profile_id="standard-e",
        )
        assert service.ingest(restamped, completed_at=LATER).status is (
            IngestionStatus.DUPLICATE
        )

    def test_source_event_order_is_part_of_identity(self) -> None:
        # Equal-timestamp ties are broken by submitted order, so two orderings are not
        # interchangeable and must not share a fingerprint.
        events = note(0) + note(1, onset_ns=0, release_ns=NS_PER_QUARTER, midi_note=64)
        forward = request_fingerprint(make_request(source_events=events))
        reversed_ = request_fingerprint(make_request(source_events=tuple(reversed(events))))
        assert forward != reversed_


class TestRequestValidation:
    def test_an_unsupported_tick_grid_is_refused_at_the_request(self) -> None:
        # The revision contract accepts only the conventional divisions. Catching it at
        # the request turns an unhandled contract error thrown from inside the service
        # into a validation failure, before a document id has been spent.
        with pytest.raises(ScoreContractError, match="ticks_per_quarter must be one of"):
            make_request(source_events=note(0), ticks_per_quarter=1000)

    def test_the_supported_tick_grids_are_accepted(self) -> None:
        for ppq in (96, 120, 192, 240, 384, 480, 960, 1920):
            assert make_request(source_events=note(0), ticks_per_quarter=ppq)

    def test_an_unsupported_tick_grid_never_reaches_the_service(
        self, service: CanonicalIngestionService, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        with pytest.raises(ScoreContractError):
            service.ingest(
                make_request(source_events=note(0), ticks_per_quarter=1000), completed_at=T0
            )
        assert repository.has_document("score-test-0001") is False


class TestDeterminism:
    def test_the_service_reads_no_clock(self) -> None:
        import inspect

        source = inspect.getsource(CanonicalIngestionService)
        for forbidden in ("datetime.now", "time.time", "utcnow", "monotonic"):
            assert forbidden not in source, forbidden

    def test_the_same_capture_yields_the_same_revision_id(self) -> None:
        from master_all_strings.core.score.ids import FixedDocumentIdAuthority
        from master_all_strings.core.score.revision_service import CanonicalRevisionService

        def ingest_once(completed_at: str) -> str | None:
            service = CanonicalIngestionService(
                CanonicalRevisionService(
                    InMemoryCanonicalScoreRepository(), FixedDocumentIdAuthority("score-x")
                )
            )
            return service.ingest(
                make_request(source_events=note(0)), completed_at=completed_at
            ).revision_id

        assert ingest_once(T0) == ingest_once("2030-01-01T00:00:00Z")
