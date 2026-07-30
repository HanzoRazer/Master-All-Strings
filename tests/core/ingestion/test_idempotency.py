"""Ingestion service and idempotency (DO-007A A5).

Retry safety is the property that makes ingestion usable from a device that may lose a
response. These tests fix that a repeat is free and a collision is loud.
"""

from __future__ import annotations

import pytest

from conftest import (  # type: ignore[import-not-found]
    NS_PER_QUARTER,
    T0,
    make_request,
    note,
    source_event,
)
from master_all_strings.core.ingestion.contracts import SourceMidiEventKind
from master_all_strings.core.ingestion.results import IngestionStatus, RejectionReason
from master_all_strings.core.ingestion.service import (
    CanonicalIngestionService,
    IngestionIdempotencyConflictError,
)
from master_all_strings.core.score.repository import InMemoryCanonicalScoreRepository

LATER = "2026-07-30T11:00:00Z"


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
