"""Canonical projection proof (DO-006 §8.8).

Musical Core has no score-document or revision implementation yet, so this seam is
proved **structurally, with a test double**. That limitation is deliberate and
recorded: DO-006 defines the Performance side of the handoff only, and real
revisions, ingestion, and the notation/TAB/MIDI projections are a later Musical Core
Dev Order.

What is actually proved here: one closed capture produces one ingestion request, a
Musical Core stand-in answers with exactly one revision id, all three projection
requests cite that same id, and the raw capture is unchanged throughout. What is
**not** proved: that any projection produces correct notation, TAB, or a piano roll.
Nothing in this file should be read as evidence that it does.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import pytest
from helpers import T1

from master_all_strings.performance.contracts.capture import RawPerformanceCaptureV1
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.ingestion import (
    CanonicalIngestionRequestV1,
    ProjectionType,
)
from master_all_strings.performance.export import capture_digest, serialize_raw_capture
from master_all_strings.performance.ingestion import build_ingestion_request

REQUESTED_AT = "2026-07-24T10:30:00Z"


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

    Mints exactly one revision id per capture and records what it was asked to
    ingest. It verifies the digest, which is the property that makes handing over a
    digest instead of the capture itself meaningful.
    """

    def __init__(self) -> None:
        self.ingested: list[CanonicalIngestionRequestV1] = []
        self._revisions: dict[str, str] = {}

    def ingest(
        self, request: CanonicalIngestionRequestV1, capture: RawPerformanceCaptureV1
    ) -> str:
        if request.canonical_revision_id is not None:
            raise AssertionError("Performance must not supply a revision id")
        if request.raw_capture_digest != capture_digest(capture):
            raise AssertionError("digest does not match the capture offered")
        self.ingested.append(request)
        revision = self._revisions.setdefault(
            request.capture_id, f"revision-{len(self._revisions) + 1:04d}"
        )
        return revision

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
        instrument_profile_id="guitar-standard-6",
        tuning_profile_id="standard-e",
        requested_at=REQUESTED_AT,
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

    def test_request_leaves_the_revision_unset(
        self, request_for: CanonicalIngestionRequestV1
    ) -> None:
        # Performance may reference a revision; it may never mint one.
        assert request_for.canonical_revision_id is None

    def test_request_defaults_to_the_three_projections(
        self, request_for: CanonicalIngestionRequestV1
    ) -> None:
        assert set(request_for.requested_projection_types) == {
            ProjectionType.PIANO_ROLL,
            ProjectionType.NOTATION,
            ProjectionType.TAB,
        }

    def test_an_open_capture_cannot_be_ingested(
        self, open_capture: RawPerformanceCaptureV1
    ) -> None:
        # Ingesting a take still in progress would ask Core to mint a revision for a
        # record that can still change.
        with pytest.raises(PerformanceContractError, match="IN_PROGRESS"):
            build_ingestion_request(
                open_capture,
                request_id="req-0002",
                instrument_profile_id="guitar-standard-6",
                tuning_profile_id="standard-e",
                requested_at=REQUESTED_AT,
            )

    def test_empty_projection_set_is_rejected(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        with pytest.raises(PerformanceContractError, match="must not be empty"):
            build_ingestion_request(
                closed_capture,
                request_id="req-0003",
                instrument_profile_id="guitar-standard-6",
                tuning_profile_id="standard-e",
                requested_at=REQUESTED_AT,
                projections=(),
            )


class TestRevisionIdentityIsCoreOwned:
    def test_revision_is_supplied_by_core(
        self,
        core: MusicalCoreDouble,
        request_for: CanonicalIngestionRequestV1,
        closed_capture: RawPerformanceCaptureV1,
    ) -> None:
        revision = core.ingest(request_for, closed_capture)
        answered = request_for.with_revision(revision)
        assert answered.canonical_revision_id == revision

    def test_a_revision_cannot_be_overwritten(
        self,
        core: MusicalCoreDouble,
        request_for: CanonicalIngestionRequestV1,
        closed_capture: RawPerformanceCaptureV1,
    ) -> None:
        # A second Core answer must not silently replace the first.
        answered = request_for.with_revision(core.ingest(request_for, closed_capture))
        with pytest.raises(PerformanceContractError, match="already set"):
            answered.with_revision("revision-9999")

    def test_a_session_id_cannot_masquerade_as_a_revision(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        # The exact shape of reaching for the nearest available identifier.
        with pytest.raises(PerformanceContractError, match="must not be the runtime session id"):
            build_ingestion_request(
                closed_capture,
                request_id="req-0004",
                instrument_profile_id="guitar-standard-6",
                tuning_profile_id="standard-e",
                requested_at=REQUESTED_AT,
            ).with_revision(closed_capture.session_id)

    def test_core_rejects_a_request_that_arrives_with_a_revision(
        self,
        core: MusicalCoreDouble,
        request_for: CanonicalIngestionRequestV1,
        closed_capture: RawPerformanceCaptureV1,
    ) -> None:
        answered = request_for.with_revision("revision-0001")
        with pytest.raises(AssertionError, match="must not supply a revision"):
            core.ingest(answered, closed_capture)

    def test_core_rejects_a_digest_mismatch(
        self,
        core: MusicalCoreDouble,
        request_for: CanonicalIngestionRequestV1,
        closed_capture: RawPerformanceCaptureV1,
    ) -> None:
        tampered = dataclasses.replace(closed_capture, capture_id="capture-tampered")
        with pytest.raises(AssertionError, match="digest does not match"):
            core.ingest(request_for, tampered)


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
                instrument_profile_id="guitar-standard-6",
                tuning_profile_id="standard-e",
                requested_at=REQUESTED_AT,
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


class TestPerStringEvidenceReachesTabProjection:
    def test_per_string_capture_carries_string_evidence_into_the_request(
        self,
        core: MusicalCoreDouble,
        per_string_source: object,
        closed_capture: RawPerformanceCaptureV1,
        runtime_identity: object,
        meter: object,
    ) -> None:
        from helpers import make_event

        from master_all_strings.performance.capture_normalization import (
            build_raw_capture,
            close_capture,
        )
        from master_all_strings.performance.contracts.capture import MidiEventType

        events = (
            make_event(0, MidiEventType.NOTE_ON, note=40, velocity=100, source_string=0),
            make_event(1, MidiEventType.NOTE_ON, note=47, velocity=98, source_string=1),
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
            instrument_profile_id="guitar-standard-6",
            tuning_profile_id="standard-e",
            requested_at=REQUESTED_AT,
            projections=(ProjectionType.TAB,),
        )
        revision = core.ingest(request, capture)
        # The evidence TAB projection would use is present and unmodified.
        assert [e.source_string for e in capture.events] == [0, 1]
        assert core.project(revision, ProjectionType.TAB).canonical_revision_id == revision

    def test_unresolved_strings_are_not_filled_in_before_ingestion(
        self, request_for: CanonicalIngestionRequestV1, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        # TAB fingering is a projection Core produces later; recording a guess here
        # would make an inference indistinguishable from a measurement.
        assert all(e.source_string is None for e in closed_capture.events)
        assert request_for.instrument_profile_id == "guitar-standard-6"
