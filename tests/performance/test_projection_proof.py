"""The Performance side of the Musical Core seam, in isolation (DO-006, revised by DO-007A).

This suite keeps a Musical Core **test double** on purpose. Its job is to prove what the
*Performance Engine* does at the seam without depending on Core's implementation, so a
Core regression shows up in the Core integration proof
(``tests/core/ingestion/test_do006_integration.py``) rather than here.

DO-007A changed the seam's shape and this file follows it. The old
``CanonicalIngestionRequestV1`` carried an optional ``canonical_revision_id`` that Core
would fill in, and Performance had a ``with_revision`` helper. That was the wrong model:
a request is what Performance *asks*, and a revision id is what Core *answers*. The
request now has no revision field at all — the strongest possible form of "Performance
may not mint one", since there is nothing to populate — and Core's answer arrives on
``CanonicalIngestionResultV1``.

What is proved here: the request cites its capture, carries a digest rather than the
capture itself, carries no identity, and preserves observed string evidence. What is not
proved here: that any projection produces correct notation, TAB, or a piano roll.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import pytest
from helpers import T1, make_event

from master_all_strings.core.score.errors import require_prefixed_digest
from master_all_strings.performance.capture_normalization import (
    build_raw_capture,
    close_capture,
)
from master_all_strings.performance.contracts.capture import (
    MidiEventType,
    RawPerformanceCaptureV1,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.ingestion import (
    CanonicalIngestionRequestV1,
    ProjectionType,
)
from master_all_strings.performance.export import capture_digest, serialize_raw_capture
from master_all_strings.performance.ingestion import build_ingestion_request

REQUESTED_AT = "2026-07-24T10:30:00Z"
BPM = 120.0


@dataclass(frozen=True)
class ProjectionRequestDouble:
    """Stands in for a Musical Core projection request.

    Defined in the test, not in ``src``, because Musical Core owns this contract and
    Performance must not pre-empt its design.
    """

    projection_type: ProjectionType
    canonical_revision_id: str


class MusicalCoreDouble:
    """A stand-in for Musical Core's ingestion endpoint.

    Mints exactly one revision id per capture and verifies the digest, which is the
    property that makes handing over a digest instead of the capture meaningful.
    """

    def __init__(self) -> None:
        self.ingested: list[CanonicalIngestionRequestV1] = []
        self._revisions: dict[str, str] = {}

    def ingest(
        self, request: CanonicalIngestionRequestV1, capture: RawPerformanceCaptureV1
    ) -> str:
        if hasattr(request, "canonical_revision_id"):
            raise AssertionError("a request must not carry a revision id")
        if request.raw_capture_digest != capture_digest(capture):
            raise AssertionError("digest does not match the capture offered")
        self.ingested.append(request)
        return self._revisions.setdefault(
            request.capture_id, f"revision-{len(self._revisions) + 1:04d}"
        )

    def project(
        self, revision_id: str, projection_type: ProjectionType
    ) -> ProjectionRequestDouble:
        return ProjectionRequestDouble(
            projection_type=projection_type, canonical_revision_id=revision_id
        )


@pytest.fixture
def core() -> MusicalCoreDouble:
    return MusicalCoreDouble()


@pytest.fixture
def request_for(closed_capture: RawPerformanceCaptureV1) -> CanonicalIngestionRequestV1:
    return build_ingestion_request(
        closed_capture,
        request_id="req-0001",
        requested_at=REQUESTED_AT,
        beats_per_minute=BPM,
        instrument_profile_id="guitar-standard-6",
        tuning_profile_id="standard-e",
    )


class TestIngestionRequest:
    def test_request_cites_the_capture(
        self, request_for: CanonicalIngestionRequestV1, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        assert request_for.capture_id == closed_capture.capture_id
        assert request_for.source_session_id == closed_capture.session_id

    def test_request_carries_a_digest_not_the_capture(
        self, request_for: CanonicalIngestionRequestV1, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        assert request_for.raw_capture_digest == capture_digest(closed_capture)
        assert request_for.raw_capture_digest.startswith("sha256:")

    def test_the_digest_performance_produces_satisfies_the_contract_core_enforces(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        # Core validates this field's shape rather than accepting any string. The two
        # sides of the seam have to agree on that shape, so the producer is checked
        # against the consumer's rule here rather than both being asserted separately.
        require_prefixed_digest(capture_digest(closed_capture), "raw_capture_digest")

    def test_request_has_no_revision_field_at_all(
        self, request_for: CanonicalIngestionRequestV1
    ) -> None:
        # The strongest form of "Performance may not mint one": there is nothing to
        # populate, by mistake or otherwise.
        names = {f.name for f in dataclasses.fields(request_for)}
        assert "canonical_revision_id" not in names
        assert "document_id" not in names
        assert "revision_id" not in names

    def test_request_defaults_to_the_three_projections(
        self, request_for: CanonicalIngestionRequestV1
    ) -> None:
        assert set(request_for.requested_projection_types) == {
            ProjectionType.PIANO_ROLL,
            ProjectionType.NOTATION,
            ProjectionType.TAB,
        }

    def test_request_carries_an_authoritative_tempo(
        self, request_for: CanonicalIngestionRequestV1
    ) -> None:
        # Integer microseconds-per-quarter, not float BPM: a float would let two tempo
        # maps a musician considers identical produce different content digests.
        assert request_for.tempo_microseconds_per_quarter == 500_000

    def test_request_carries_a_capture_origin(
        self, request_for: CanonicalIngestionRequestV1
    ) -> None:
        # Elapsed time needs an origin, and the capture has only an ISO wall clock.
        assert request_for.capture_origin_ns == 0

    def test_an_open_capture_cannot_be_ingested(
        self, open_capture: RawPerformanceCaptureV1
    ) -> None:
        # Ingesting a take still in progress would ask Core to mint a revision for a
        # record that can still change.
        with pytest.raises(PerformanceContractError, match="IN_PROGRESS"):
            build_ingestion_request(
                open_capture,
                request_id="req-0002",
                requested_at=REQUESTED_AT,
                beats_per_minute=BPM,
            )

    def test_only_note_events_cross_the_seam(
        self, closed_capture: RawPerformanceCaptureV1, request_for: CanonicalIngestionRequestV1
    ) -> None:
        # DIRECT_EVENT_IMPORT_V1 has no canonical representation for controller or
        # pitch-bend events, so they stay in the capture rather than being dropped
        # into a "converted" pile.
        assert request_for.event_count == closed_capture.event_count


class TestRevisionIdentityIsCoreOwned:
    def test_the_revision_is_supplied_by_core(
        self,
        core: MusicalCoreDouble,
        request_for: CanonicalIngestionRequestV1,
        closed_capture: RawPerformanceCaptureV1,
    ) -> None:
        revision = core.ingest(request_for, closed_capture)
        assert revision.startswith("revision-")

    def test_core_rejects_a_digest_mismatch(
        self,
        core: MusicalCoreDouble,
        request_for: CanonicalIngestionRequestV1,
        closed_capture: RawPerformanceCaptureV1,
    ) -> None:
        tampered = dataclasses.replace(closed_capture, capture_id="capture-tampered")
        with pytest.raises(AssertionError, match="digest does not match"):
            core.ingest(request_for, tampered)

    def test_performance_defines_no_revision_minting_helper(self) -> None:
        # DO-006 had `with_revision`. It is gone: the answer belongs on Core's result.
        from master_all_strings.performance import ingestion

        assert not hasattr(ingestion, "with_revision")
        public = [n for n in dir(ingestion) if not n.startswith("_")]
        assert not any("revision" in name.lower() for name in public)


class TestThreeProjectionsCiteOneRevision:
    def test_all_three_projections_cite_the_same_revision(
        self,
        core: MusicalCoreDouble,
        request_for: CanonicalIngestionRequestV1,
        closed_capture: RawPerformanceCaptureV1,
    ) -> None:
        revision = core.ingest(request_for, closed_capture)
        projections = [
            core.project(revision, projection)
            for projection in request_for.requested_projection_types
        ]
        assert {p.canonical_revision_id for p in projections} == {revision}
        assert len(projections) == 3

    def test_each_projection_type_is_distinct(
        self,
        core: MusicalCoreDouble,
        request_for: CanonicalIngestionRequestV1,
        closed_capture: RawPerformanceCaptureV1,
    ) -> None:
        revision = core.ingest(request_for, closed_capture)
        projections = [
            core.project(revision, projection)
            for projection in request_for.requested_projection_types
        ]
        assert {p.projection_type for p in projections} == {
            ProjectionType.PIANO_ROLL,
            ProjectionType.NOTATION,
            ProjectionType.TAB,
        }

    def test_one_capture_yields_one_revision(
        self,
        core: MusicalCoreDouble,
        request_for: CanonicalIngestionRequestV1,
        closed_capture: RawPerformanceCaptureV1,
    ) -> None:
        first = core.ingest(request_for, closed_capture)
        second = core.ingest(
            build_ingestion_request(
                closed_capture,
                request_id="req-0005",
                requested_at=REQUESTED_AT,
                beats_per_minute=BPM,
            ),
            closed_capture,
        )
        assert first == second


class TestRawCaptureSurvivesProjection:
    def test_raw_capture_is_unchanged_by_ingestion(
        self,
        core: MusicalCoreDouble,
        request_for: CanonicalIngestionRequestV1,
        closed_capture: RawPerformanceCaptureV1,
    ) -> None:
        before = serialize_raw_capture(closed_capture)
        revision = core.ingest(request_for, closed_capture)
        for projection in request_for.requested_projection_types:
            core.project(revision, projection)
        assert serialize_raw_capture(closed_capture) == before

    def test_digest_is_stable_across_the_whole_flow(
        self,
        core: MusicalCoreDouble,
        request_for: CanonicalIngestionRequestV1,
        closed_capture: RawPerformanceCaptureV1,
    ) -> None:
        before = capture_digest(closed_capture)
        core.ingest(request_for, closed_capture)
        assert capture_digest(closed_capture) == before

    def test_no_projection_writes_into_the_capture(
        self,
        core: MusicalCoreDouble,
        request_for: CanonicalIngestionRequestV1,
        closed_capture: RawPerformanceCaptureV1,
    ) -> None:
        revision = core.ingest(request_for, closed_capture)
        projection = core.project(revision, ProjectionType.TAB)
        assert not hasattr(projection, "events")
        assert closed_capture.is_closed

    def test_projection_failure_does_not_invalidate_the_capture(
        self,
        core: MusicalCoreDouble,
        request_for: CanonicalIngestionRequestV1,
        closed_capture: RawPerformanceCaptureV1,
    ) -> None:
        revision = core.ingest(request_for, closed_capture)
        before = serialize_raw_capture(closed_capture)
        with pytest.raises(ValueError):
            core.project(revision, ProjectionType("not-a-projection"))
        assert serialize_raw_capture(closed_capture) == before
        assert closed_capture.completion_state.value == "complete"


class TestPerStringEvidenceReachesTheSeam:
    def test_per_string_capture_carries_string_evidence_into_the_request(
        self,
        core: MusicalCoreDouble,
        per_string_source: object,
        runtime_identity: object,
        meter: object,
    ) -> None:
        events = (
            make_event(0, MidiEventType.NOTE_ON, note=40, velocity=100, source_string=0),
            make_event(1, MidiEventType.NOTE_OFF, note=40, velocity=0, source_string=0),
        )
        capture = close_capture(
            build_raw_capture(
                capture_id="capture-strings",
                session_id="session-001",
                runtime_identity=runtime_identity,  # type: ignore[arg-type]
                source_identity=per_string_source,  # type: ignore[arg-type]
                started_at="2026-07-24T10:00:00Z",
                tempo_context=120.0,
                meter_context=meter,  # type: ignore[arg-type]
                events=events,
            ),
            ended_at=T1,
        )
        request = build_ingestion_request(
            capture,
            request_id="req-strings",
            requested_at=REQUESTED_AT,
            beats_per_minute=BPM,
            projections=(ProjectionType.TAB,),
        )
        # The observed string survives the crossing without being inferred anywhere.
        assert [e.observed_source_string for e in request.source_events] == [0, 0]
        assert [e.source_string for e in capture.events] == [0, 0]
        assert core.ingest(request, capture).startswith("revision-")

    def test_unresolved_strings_are_not_filled_in_before_ingestion(
        self, request_for: CanonicalIngestionRequestV1, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        # TAB fingering is a projection Core produces later; recording a guess here
        # would make an inference indistinguishable from a measurement.
        assert all(e.source_string is None for e in closed_capture.events)
        assert all(e.observed_source_string is None for e in request_for.source_events)
        assert request_for.instrument_profile_id == "guitar-standard-6"
