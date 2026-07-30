"""The DO-006 seam, proved against real Musical Core (DO-007A A5).

DO-006 proved this seam structurally with a test double and said so. This is the same
flow with the double removed:

    RawPerformanceCaptureV1
        -> CanonicalIngestionRequestV1
        -> CanonicalIngestionService
        -> ScoreDocumentV1
        -> CanonicalScoreRevisionV1

The isolated Performance tests keep their fake — nothing here removes it. Only this
proof crosses into real Core, and it depends on Core by design: if the ingestion seam
breaks, this test should fail. That dependency is the evidence, not an accident.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from master_all_strings.core.ingestion.results import IngestionStatus
from master_all_strings.core.ingestion.service import CanonicalIngestionService
from master_all_strings.core.score.digest import verify_revision_digest
from master_all_strings.core.score.ids import DeterministicDocumentIdAuthority
from master_all_strings.core.score.provenance import ScoreSourceKind
from master_all_strings.core.score.repository import InMemoryCanonicalScoreRepository
from master_all_strings.core.score.revision_service import CanonicalRevisionService
from master_all_strings.performance.capture_normalization import (
    build_raw_capture,
    close_capture,
    normalize_midi_event,
)
from master_all_strings.performance.contracts.capture import (
    CaptureSourceV1,
    MidiEventType,
    RawPerformanceCaptureV1,
)
from master_all_strings.performance.contracts.runtime import RuntimeIdentityV1, RuntimeKind
from master_all_strings.performance.export import serialize_raw_capture
from master_all_strings.performance.ingestion import build_ingestion_request

T0 = "2026-07-30T10:00:00Z"
T1 = "2026-07-30T10:00:30Z"
NS_PER_QUARTER = 500_000_000

RUNTIME = RuntimeIdentityV1(
    schema_version=RuntimeIdentityV1.SCHEMA_VERSION,
    runtime_id="fake",
    runtime_kind=RuntimeKind.FAKE,
    reported_version="1.0.0",
    version_policy="1.0.0",
    version_supported=True,
)
PLAIN_SOURCE = CaptureSourceV1(
    schema_version=CaptureSourceV1.SCHEMA_VERSION,
    source_id="midi-in-0",
    port="port-0",
    device="generic-midi-guitar",
    supplies_string_identity=False,
)
PER_STRING_SOURCE = CaptureSourceV1(
    schema_version=CaptureSourceV1.SCHEMA_VERSION,
    source_id="midi-in-0",
    port="port-0",
    device="divided-pickup-6",
    supplies_string_identity=True,
)


def capture_event(
    index: int,
    event_type: MidiEventType,
    time_ns: int,
    *,
    note: int = 64,
    velocity: int = 96,
    channel: int = 0,
    source_string: int | None = None,
) -> object:
    return normalize_midi_event(
        event_id=f"evt-{index:04d}",
        sequence_number=index,
        event_type=event_type,
        capture_time_ns=time_ns,
        channel=channel,
        source_port="port-0",
        source_device="generic-midi-guitar",
        note=note,
        velocity=velocity,
        source_string=source_string,
    )


def make_capture(
    events: tuple[object, ...], *, source: CaptureSourceV1 = PLAIN_SOURCE
) -> RawPerformanceCaptureV1:
    from master_all_strings.core.score.meter import MeterChangeV1

    del MeterChangeV1  # meter lives on the request, not the capture
    from master_all_strings.performance.contracts.session import MeterV1

    return close_capture(
        build_raw_capture(
            capture_id="capture-0001",
            session_id="session-0001",
            runtime_identity=RUNTIME,
            source_identity=source,
            started_at=T0,
            tempo_context=120.0,
            meter_context=MeterV1(
                schema_version=MeterV1.SCHEMA_VERSION, beats_per_bar=4, beat_unit=4
            ),
            events=events,  # type: ignore[arg-type]
        ),
        ended_at=T1,
    )


@pytest.fixture
def repository() -> InMemoryCanonicalScoreRepository:
    return InMemoryCanonicalScoreRepository()


@pytest.fixture
def service(repository: InMemoryCanonicalScoreRepository) -> CanonicalIngestionService:
    return CanonicalIngestionService(
        CanonicalRevisionService(repository, DeterministicDocumentIdAuthority())
    )


@pytest.fixture
def two_note_capture() -> RawPerformanceCaptureV1:
    return make_capture(
        (
            capture_event(0, MidiEventType.NOTE_ON, 0, note=64),
            capture_event(1, MidiEventType.NOTE_OFF, NS_PER_QUARTER, note=64, velocity=0),
            capture_event(2, MidiEventType.NOTE_ON, NS_PER_QUARTER, note=67),
            capture_event(
                3, MidiEventType.NOTE_OFF, NS_PER_QUARTER * 2, note=67, velocity=0
            ),
        )
    )


class TestEndToEndSeam:
    def test_a_capture_becomes_a_canonical_revision(
        self,
        service: CanonicalIngestionService,
        repository: InMemoryCanonicalScoreRepository,
        two_note_capture: RawPerformanceCaptureV1,
    ) -> None:
        request = build_ingestion_request(
            two_note_capture,
            request_id="req-0001",
            requested_at=T1,
            beats_per_minute=120.0,
        )
        result = service.ingest(request, completed_at=T1)

        assert result.status is IngestionStatus.ACCEPTED
        assert result.document_id is not None
        revision = repository.get_current_revision(result.document_id)
        assert revision.event_count == 2
        assert revision.revision_number == 1
        assert revision.parent_revision_id is None

    def test_performance_never_supplies_the_revision_id(
        self, two_note_capture: RawPerformanceCaptureV1
    ) -> None:
        # The request has no such field, so there is nothing to populate by mistake.
        request = build_ingestion_request(
            two_note_capture,
            request_id="req-0001",
            requested_at=T1,
            beats_per_minute=120.0,
        )
        assert not hasattr(request, "canonical_revision_id")
        assert not hasattr(request, "document_id")

    def test_core_mints_both_identities(
        self,
        service: CanonicalIngestionService,
        two_note_capture: RawPerformanceCaptureV1,
    ) -> None:
        request = build_ingestion_request(
            two_note_capture,
            request_id="req-0001",
            requested_at=T1,
            beats_per_minute=120.0,
        )
        result = service.ingest(request, completed_at=T1)
        assert result.document_id == "score-test-0001"
        assert result.revision_id is not None
        assert result.revision_id.startswith("rev-")

    def test_the_raw_capture_is_unchanged(
        self,
        service: CanonicalIngestionService,
        two_note_capture: RawPerformanceCaptureV1,
    ) -> None:
        before = serialize_raw_capture(two_note_capture)
        request = build_ingestion_request(
            two_note_capture,
            request_id="req-0001",
            requested_at=T1,
            beats_per_minute=120.0,
        )
        service.ingest(request, completed_at=T1)
        assert serialize_raw_capture(two_note_capture) == before
        assert two_note_capture.completion_state.value == "complete"

    def test_the_revision_digest_verifies(
        self,
        service: CanonicalIngestionService,
        repository: InMemoryCanonicalScoreRepository,
        two_note_capture: RawPerformanceCaptureV1,
    ) -> None:
        request = build_ingestion_request(
            two_note_capture,
            request_id="req-0001",
            requested_at=T1,
            beats_per_minute=120.0,
        )
        result = service.ingest(request, completed_at=T1)
        assert result.document_id is not None
        assert verify_revision_digest(repository.get_current_revision(result.document_id))

    def test_timing_survives_the_crossing(
        self,
        service: CanonicalIngestionService,
        repository: InMemoryCanonicalScoreRepository,
        two_note_capture: RawPerformanceCaptureV1,
    ) -> None:
        request = build_ingestion_request(
            two_note_capture,
            request_id="req-0001",
            requested_at=T1,
            beats_per_minute=120.0,
        )
        result = service.ingest(request, completed_at=T1)
        assert result.document_id is not None
        revision = repository.get_current_revision(result.document_id)
        assert [e.start_tick for e in revision.events] == [0, 960]
        assert [e.duration_ticks for e in revision.events] == [960, 960]

    def test_an_open_capture_cannot_be_ingested(self) -> None:
        from master_all_strings.performance.contracts.errors import PerformanceContractError

        open_capture = build_raw_capture(
            capture_id="capture-open",
            session_id="session-0001",
            runtime_identity=RUNTIME,
            source_identity=PLAIN_SOURCE,
            started_at=T0,
            tempo_context=120.0,
            meter_context=__import__(
                "master_all_strings.performance.contracts.session",
                fromlist=["MeterV1"],
            ).MeterV1(schema_version="1.0.0", beats_per_bar=4, beat_unit=4),
        )
        with pytest.raises(PerformanceContractError, match="IN_PROGRESS"):
            build_ingestion_request(
                open_capture, request_id="r", requested_at=T1, beats_per_minute=120.0
            )


class TestEvidenceCrossesTheSeam:
    def test_source_nanoseconds_remain_auditable(
        self,
        service: CanonicalIngestionService,
        repository: InMemoryCanonicalScoreRepository,
        two_note_capture: RawPerformanceCaptureV1,
    ) -> None:
        request = build_ingestion_request(
            two_note_capture,
            request_id="req-0001",
            requested_at=T1,
            beats_per_minute=120.0,
        )
        result = service.ingest(request, completed_at=T1)
        assert result.document_id is not None
        provenance = repository.get_current_revision(result.document_id).provenance
        assert provenance.source_kind is ScoreSourceKind.PERFORMANCE_CAPTURE
        assert provenance.source_reference == "capture-0001"
        first = provenance.event_provenance[0]
        assert first.source_capture_time_ns == 0
        assert first.source_release_time_ns == NS_PER_QUARTER

    def test_conversion_metadata_is_present(
        self,
        service: CanonicalIngestionService,
        repository: InMemoryCanonicalScoreRepository,
        two_note_capture: RawPerformanceCaptureV1,
    ) -> None:
        request = build_ingestion_request(
            two_note_capture,
            request_id="req-0001",
            requested_at=T1,
            beats_per_minute=120.0,
        )
        result = service.ingest(request, completed_at=T1)
        assert result.document_id is not None
        record = (
            repository.get_current_revision(result.document_id).provenance.event_provenance[0]
        )
        assert record.ticks_per_quarter == 960
        assert record.microseconds_per_quarter == 500_000
        assert record.rounding_policy is not None
        assert record.converted_start_tick == 0
        assert record.converted_duration_ticks == 960

    def test_channel_stays_provenance_and_never_becomes_voice(
        self,
        service: CanonicalIngestionService,
        repository: InMemoryCanonicalScoreRepository,
    ) -> None:
        capture = make_capture(
            (
                capture_event(0, MidiEventType.NOTE_ON, 0, note=64, channel=3),
                capture_event(
                    1, MidiEventType.NOTE_OFF, NS_PER_QUARTER, note=64, velocity=0, channel=3
                ),
            )
        )
        request = build_ingestion_request(
            capture, request_id="req-ch", requested_at=T1, beats_per_minute=120.0
        )
        result = service.ingest(request, completed_at=T1)
        assert result.document_id is not None
        revision = repository.get_current_revision(result.document_id)
        assert revision.events[0].voice_id is None
        assert revision.provenance.event_provenance[0].source_channel == 3

    def test_observed_string_crosses_into_provenance(
        self,
        service: CanonicalIngestionService,
        repository: InMemoryCanonicalScoreRepository,
    ) -> None:
        capture = make_capture(
            (
                capture_event(0, MidiEventType.NOTE_ON, 0, note=40, source_string=0),
                capture_event(
                    1,
                    MidiEventType.NOTE_OFF,
                    NS_PER_QUARTER,
                    note=40,
                    velocity=0,
                    source_string=0,
                ),
            ),
            source=PER_STRING_SOURCE,
        )
        request = build_ingestion_request(
            capture, request_id="req-str", requested_at=T1, beats_per_minute=120.0
        )
        result = service.ingest(request, completed_at=T1)
        assert result.document_id is not None
        record = (
            repository.get_current_revision(result.document_id).provenance.event_provenance[0]
        )
        assert record.observed_source_string == 0
        assert record.string_identity_observed is True

    def test_an_unresolved_string_stays_unresolved(
        self,
        service: CanonicalIngestionService,
        repository: InMemoryCanonicalScoreRepository,
        two_note_capture: RawPerformanceCaptureV1,
    ) -> None:
        request = build_ingestion_request(
            two_note_capture,
            request_id="req-0001",
            requested_at=T1,
            beats_per_minute=120.0,
        )
        result = service.ingest(request, completed_at=T1)
        assert result.document_id is not None
        records = (
            repository.get_current_revision(result.document_id).provenance.event_provenance
        )
        assert all(r.observed_source_string is None for r in records)

    def test_non_note_events_stay_in_the_capture(
        self,
        service: CanonicalIngestionService,
        repository: InMemoryCanonicalScoreRepository,
    ) -> None:
        # DIRECT_EVENT_IMPORT_V1 has no canonical representation for a controller
        # event, so it is not carried across and the capture keeps it.
        controller = normalize_midi_event(
            event_id="evt-0099",
            sequence_number=1,
            event_type=MidiEventType.CONTROL_CHANGE,
            capture_time_ns=10,
            channel=0,
            source_port="port-0",
            source_device="generic-midi-guitar",
            controller=64,
            controller_value=127,
        )
        capture = make_capture(
            (
                capture_event(0, MidiEventType.NOTE_ON, 0, note=64),
                controller,
                capture_event(2, MidiEventType.NOTE_OFF, NS_PER_QUARTER, note=64, velocity=0),
            )
        )
        request = build_ingestion_request(
            capture, request_id="req-cc", requested_at=T1, beats_per_minute=120.0
        )
        result = service.ingest(request, completed_at=T1)
        assert result.accepted_event_count == 1
        assert any(e.event_type is MidiEventType.CONTROL_CHANGE for e in capture.events)


class TestRetrySafety:
    def test_reingesting_the_same_capture_creates_no_second_revision(
        self,
        service: CanonicalIngestionService,
        repository: InMemoryCanonicalScoreRepository,
        two_note_capture: RawPerformanceCaptureV1,
    ) -> None:
        request = build_ingestion_request(
            two_note_capture,
            request_id="req-0001",
            requested_at=T1,
            beats_per_minute=120.0,
        )
        first = service.ingest(request, completed_at=T1)
        repeat = service.ingest(request, completed_at="2026-07-30T12:00:00Z")
        assert repeat.status is IngestionStatus.DUPLICATE
        assert first.document_id is not None
        assert len(repository.list_revisions(first.document_id)) == 1


class TestDependencyDirection:
    def test_core_ingestion_imports_nothing_from_performance(self) -> None:
        from master_all_strings.core.ingestion import contracts, policies, results, service

        for module in (contracts, results, policies, service):
            tree = ast.parse(textwrap.dedent(inspect.getsource(module)))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "performance" not in node.module, module.__name__

    def test_the_request_contract_lives_in_musical_core(self) -> None:
        # The registry has always said MUSICAL_CORE owns it; DO-006 placed the class in
        # the Performance package, which only became load-bearing once Core consumed it.
        from master_all_strings.performance.contracts.ingestion import (
            CanonicalIngestionRequestV1,
        )

        assert CanonicalIngestionRequestV1.__module__.startswith(
            "master_all_strings.core.ingestion"
        )

    def test_performance_still_re_exports_it(self) -> None:
        from master_all_strings.core.ingestion.contracts import (
            CanonicalIngestionRequestV1 as CoreRequest,
        )
        from master_all_strings.performance.contracts.ingestion import (
            CanonicalIngestionRequestV1 as PerformanceRequest,
        )

        assert CoreRequest is PerformanceRequest


class TestTheDoubleIsStillAvailable:
    def test_the_isolated_performance_proof_still_uses_a_double(self) -> None:
        # The ruling: keep the double for isolated Performance tests; only the
        # integration proof crosses into real Core.
        from pathlib import Path

        proof = (
            Path(__file__).resolve().parents[2]
            / "performance"
            / "test_projection_proof.py"
        )
        text = proof.read_text(encoding="utf-8")
        assert "MusicalCoreDouble" in text
        assert "from master_all_strings.core.ingestion" not in text
