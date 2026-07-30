"""Revision service invariants (DO-007A A4).

The service is the only sanctioned path for creating documents and revisions, so these
tests are about what a caller *cannot* do: choose a revision number, claim an identity,
fork a history, or leave a document pointing at a revision that was never stored.
"""

from __future__ import annotations

import inspect

import pytest

from conftest import T0, make_event  # type: ignore[import-not-found]
from master_all_strings.core.score.digest import verify_revision_digest
from master_all_strings.core.score.ids import (
    DeterministicDocumentIdAuthority,
    FixedDocumentIdAuthority,
)
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.provenance import (
    RevisionProvenanceV1,
    ScoreSourceKind,
)
from master_all_strings.core.score.repository import (
    DocumentNotFoundError,
    InMemoryCanonicalScoreRepository,
)
from master_all_strings.core.score.revision_service import (
    CanonicalRevisionService,
    NoncontiguousRevisionError,
    ParentRevisionMismatchError,
    RevisionDocumentMismatchError,
)
from master_all_strings.core.score.tempo import tempo_from_bpm

METER_4_4 = MeterChangeV1(
    schema_version=MeterChangeV1.SCHEMA_VERSION, tick=0, numerator=4, denominator=4
)
TEMPO_120 = tempo_from_bpm(120.0)
MANUAL = RevisionProvenanceV1(
    schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
    source_kind=ScoreSourceKind.MANUAL_CONSTRUCTION,
    policy_version="manual-1",
)


@pytest.fixture
def repository() -> InMemoryCanonicalScoreRepository:
    return InMemoryCanonicalScoreRepository()


@pytest.fixture
def service(repository: InMemoryCanonicalScoreRepository) -> CanonicalRevisionService:
    return CanonicalRevisionService(repository, DeterministicDocumentIdAuthority())


def create(service: CanonicalRevisionService, **overrides: object) -> object:
    payload: dict[str, object] = {
        "created_at": T0,
        "provenance": MANUAL,
        "events": (make_event(0),),
        "tempo_changes": (TEMPO_120,),
        "meter_changes": (METER_4_4,),
    }
    payload.update(overrides)
    return service.create_document_with_revision(**payload)  # type: ignore[arg-type]


class TestDocumentCreation:
    def test_document_and_origin_revision_are_created_together(
        self, service: CanonicalRevisionService
    ) -> None:
        # A document without a revision would be a work with no state, and every
        # consumer would have to handle that condition.
        result = create(service)
        assert result.document.revision_count == 1  # type: ignore[attr-defined]
        assert result.revision.revision_number == 1  # type: ignore[attr-defined]
        assert result.is_origin is True  # type: ignore[attr-defined]

    def test_document_points_at_its_origin(self, service: CanonicalRevisionService) -> None:
        result = create(service)
        assert (
            result.document.current_revision_id  # type: ignore[attr-defined]
            == result.revision.revision_id  # type: ignore[attr-defined]
        )

    def test_the_id_comes_from_the_injected_authority(
        self, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        service = CanonicalRevisionService(repository, FixedDocumentIdAuthority("score-fixed"))
        assert create(service).document.document_id == "score-fixed"  # type: ignore[attr-defined]

    def test_two_documents_get_distinct_ids(self, service: CanonicalRevisionService) -> None:
        first = create(service)
        second = create(service)
        assert (
            first.document.document_id != second.document.document_id  # type: ignore[attr-defined]
        )

    def test_both_are_persisted(
        self, service: CanonicalRevisionService, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        result = create(service)
        document_id = result.document.document_id  # type: ignore[attr-defined]
        assert repository.has_document(document_id)
        assert repository.get_current_revision(document_id) == result.revision  # type: ignore[attr-defined]

    def test_an_empty_score_is_allowed(self, service: CanonicalRevisionService) -> None:
        assert create(service, events=()).revision.event_count == 0  # type: ignore[attr-defined]

    def test_optional_metadata_is_carried(self, service: CanonicalRevisionService) -> None:
        result = create(service, title="Etude", description="take 1")
        assert result.document.title == "Etude"  # type: ignore[attr-defined]


class TestIdentityIsDerivedNotChosen:
    def test_the_service_takes_no_revision_number(self) -> None:
        # A caller-chosen number could skip, repeat, or fork the history.
        signature = inspect.signature(CanonicalRevisionService.create_child_revision)
        assert "revision_number" not in signature.parameters
        assert "revision_id" not in signature.parameters
        assert "parent_revision_id" not in signature.parameters

    def test_the_service_takes_no_document_id_on_creation(self) -> None:
        signature = inspect.signature(CanonicalRevisionService.create_document_with_revision)
        assert "document_id" not in signature.parameters

    def test_the_digest_matches_the_content(self, service: CanonicalRevisionService) -> None:
        assert verify_revision_digest(create(service).revision) is True  # type: ignore[attr-defined]

    def test_the_revision_id_derives_from_the_digest(
        self, service: CanonicalRevisionService
    ) -> None:
        revision = create(service).revision  # type: ignore[attr-defined]
        assert revision.revision_id == "rev-" + revision.content_digest[:24]

    def test_input_order_does_not_change_identity(
        self, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        events = (make_event(0), make_event(1, start_tick=480), make_event(2, start_tick=960))
        forward = CanonicalRevisionService(
            InMemoryCanonicalScoreRepository(), FixedDocumentIdAuthority("score-x")
        )
        reversed_service = CanonicalRevisionService(
            InMemoryCanonicalScoreRepository(), FixedDocumentIdAuthority("score-x")
        )
        left = create(forward, events=events)
        right = create(reversed_service, events=tuple(reversed(events)))
        assert left.revision.revision_id == right.revision.revision_id  # type: ignore[attr-defined]

    def test_events_are_stored_canonicalized(
        self, service: CanonicalRevisionService
    ) -> None:
        unordered = (make_event(1, start_tick=960), make_event(0, start_tick=0))
        revision = create(service, events=unordered).revision  # type: ignore[attr-defined]
        assert [e.start_tick for e in revision.events] == [0, 960]


class TestChildRevisions:
    def test_a_child_follows_its_parent(self, service: CanonicalRevisionService) -> None:
        origin = create(service)
        document_id = origin.document.document_id  # type: ignore[attr-defined]
        child = service.create_child_revision(
            document_id=document_id,
            created_at=T0,
            provenance=MANUAL,
            events=(make_event(0), make_event(1, start_tick=480)),
            tempo_changes=(TEMPO_120,),
            meter_changes=(METER_4_4,),
        )
        assert child.revision.revision_number == 2
        assert child.revision.parent_revision_id == origin.revision.revision_id  # type: ignore[attr-defined]
        assert child.document.revision_count == 2

    def test_the_document_pointer_advances(
        self, service: CanonicalRevisionService, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        origin = create(service)
        document_id = origin.document.document_id  # type: ignore[attr-defined]
        child = service.create_child_revision(
            document_id=document_id,
            created_at=T0,
            provenance=MANUAL,
            events=(make_event(5),),
            tempo_changes=(TEMPO_120,),
            meter_changes=(METER_4_4,),
        )
        assert repository.get_current_revision(document_id) == child.revision

    def test_history_stays_ordered_and_complete(
        self, service: CanonicalRevisionService, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        origin = create(service)
        document_id = origin.document.document_id  # type: ignore[attr-defined]
        for index in range(1, 4):
            service.create_child_revision(
                document_id=document_id,
                created_at=T0,
                provenance=MANUAL,
                events=tuple(make_event(i, start_tick=i * 480) for i in range(index + 1)),
                tempo_changes=(TEMPO_120,),
                meter_changes=(METER_4_4,),
            )
        numbers = [r.revision_number for r in repository.list_revisions(document_id)]
        assert numbers == [1, 2, 3, 4]

    def test_ppq_is_inherited_by_default(self, service: CanonicalRevisionService) -> None:
        origin = create(service)
        child = service.create_child_revision(
            document_id=origin.document.document_id,  # type: ignore[attr-defined]
            created_at=T0,
            provenance=MANUAL,
            events=(make_event(0),),
            tempo_changes=(TEMPO_120,),
            meter_changes=(METER_4_4,),
        )
        assert child.revision.ticks_per_quarter == origin.revision.ticks_per_quarter  # type: ignore[attr-defined]

    def test_an_unknown_document_is_named(self, service: CanonicalRevisionService) -> None:
        with pytest.raises(DocumentNotFoundError, match="DOCUMENT_NOT_FOUND"):
            service.create_child_revision(
                document_id="score-absent",
                created_at=T0,
                provenance=MANUAL,
                events=(),
                tempo_changes=(TEMPO_120,),
                meter_changes=(METER_4_4,),
            )


class TestLineageVerification:
    def test_a_mismatched_document_is_named(self, service: CanonicalRevisionService) -> None:
        left = create(service).revision  # type: ignore[attr-defined]
        right = create(service).revision  # type: ignore[attr-defined]
        with pytest.raises(RevisionDocumentMismatchError, match="REVISION_DOCUMENT_MISMATCH"):
            service.verify_lineage(right, left)

    def test_a_mismatched_parent_is_named(
        self, service: CanonicalRevisionService
    ) -> None:
        import dataclasses

        origin = create(service)
        child = service.create_child_revision(
            document_id=origin.document.document_id,  # type: ignore[attr-defined]
            created_at=T0,
            provenance=MANUAL,
            events=(make_event(7),),
            tempo_changes=(TEMPO_120,),
            meter_changes=(METER_4_4,),
        )
        impostor = dataclasses.replace(child.revision, parent_revision_id="rev-" + "e" * 24)
        with pytest.raises(ParentRevisionMismatchError, match="PARENT_REVISION_MISMATCH"):
            service.verify_lineage(impostor, origin.revision)  # type: ignore[attr-defined]

    def test_a_noncontiguous_number_is_named(
        self, service: CanonicalRevisionService
    ) -> None:
        import dataclasses

        origin = create(service)
        child = service.create_child_revision(
            document_id=origin.document.document_id,  # type: ignore[attr-defined]
            created_at=T0,
            provenance=MANUAL,
            events=(make_event(7),),
            tempo_changes=(TEMPO_120,),
            meter_changes=(METER_4_4,),
        )
        skipped = dataclasses.replace(child.revision, revision_number=9)
        with pytest.raises(NoncontiguousRevisionError, match="NONCONTIGUOUS_REVISION"):
            service.verify_lineage(skipped, origin.revision)  # type: ignore[attr-defined]

    def test_a_well_formed_child_verifies(self, service: CanonicalRevisionService) -> None:
        origin = create(service)
        child = service.create_child_revision(
            document_id=origin.document.document_id,  # type: ignore[attr-defined]
            created_at=T0,
            provenance=MANUAL,
            events=(make_event(7),),
            tempo_changes=(TEMPO_120,),
            meter_changes=(METER_4_4,),
        )
        service.verify_lineage(child.revision, origin.revision)  # type: ignore[attr-defined]


class TestResolution:
    def test_current_revision_resolves(self, service: CanonicalRevisionService) -> None:
        origin = create(service)
        assert (
            service.resolve_current_revision(origin.document.document_id)  # type: ignore[attr-defined]
            == origin.revision  # type: ignore[attr-defined]
        )

    def test_current_revision_of_a_missing_document_is_named(
        self, service: CanonicalRevisionService
    ) -> None:
        with pytest.raises(DocumentNotFoundError, match="DOCUMENT_NOT_FOUND"):
            service.resolve_current_revision("score-absent")


class TestDeterminism:
    def test_created_at_is_supplied_not_read(self) -> None:
        # Reading a clock inside the service would make every revision id
        # irreproducible and every test time-dependent.
        source = inspect.getsource(CanonicalRevisionService)
        for forbidden in ("datetime.now", "time.time", "utcnow"):
            assert forbidden not in source, forbidden

    def test_created_at_does_not_affect_identity(
        self, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        early = CanonicalRevisionService(
            InMemoryCanonicalScoreRepository(), FixedDocumentIdAuthority("score-x")
        )
        late = CanonicalRevisionService(
            InMemoryCanonicalScoreRepository(), FixedDocumentIdAuthority("score-x")
        )
        left = create(early, created_at="2026-01-01T00:00:00Z")
        right = create(late, created_at="2030-12-31T23:59:59Z")
        assert left.revision.revision_id == right.revision.revision_id  # type: ignore[attr-defined]
