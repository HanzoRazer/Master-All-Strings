"""In-memory repository behaviour (DO-007A A4).

The repository stores already-valid objects and rejects only what storage itself can
see. These tests fix that boundary in both directions: duplicate and missing keys are
its business, lineage and digests are not.
"""

from __future__ import annotations

import inspect

import pytest

from conftest import DOCUMENT_ID, make_event, make_revision  # type: ignore[import-not-found]
from master_all_strings.core.score.models import CanonicalScoreRevisionV1, ScoreDocumentV1
from master_all_strings.core.score.repository import (
    CanonicalScoreRepositoryPort,
    DocumentNotFoundError,
    DuplicateDocumentError,
    DuplicateRevisionError,
    InMemoryCanonicalScoreRepository,
    RevisionNotFoundError,
    ScoreRepositoryError,
)


@pytest.fixture
def repository() -> InMemoryCanonicalScoreRepository:
    return InMemoryCanonicalScoreRepository()


@pytest.fixture
def stored(
    repository: InMemoryCanonicalScoreRepository,
    document: ScoreDocumentV1,
    origin_revision: CanonicalScoreRevisionV1,
) -> InMemoryCanonicalScoreRepository:
    repository.create_document(document)
    repository.save_revision(origin_revision)
    return repository


class TestPortConformance:
    def test_the_in_memory_repository_satisfies_the_port(
        self, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        assert isinstance(repository, CanonicalScoreRepositoryPort)

    def test_every_port_operation_exists(
        self, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        for name in (
            "create_document",
            "save_document",
            "save_revision",
            "get_document",
            "get_revision",
            "get_current_revision",
            "list_revisions",
            "has_document",
        ):
            assert callable(getattr(repository, name)), name


class TestDocuments:
    def test_create_and_retrieve(
        self, repository: InMemoryCanonicalScoreRepository, document: ScoreDocumentV1
    ) -> None:
        repository.create_document(document)
        assert repository.get_document(DOCUMENT_ID) == document

    def test_duplicate_document_rejected(
        self, repository: InMemoryCanonicalScoreRepository, document: ScoreDocumentV1
    ) -> None:
        repository.create_document(document)
        with pytest.raises(DuplicateDocumentError, match="already exists"):
            repository.create_document(document)

    def test_missing_document_has_a_named_error(
        self, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        with pytest.raises(DocumentNotFoundError, match="DOCUMENT_NOT_FOUND"):
            repository.get_document("score-absent")

    def test_saving_an_unknown_document_is_rejected(
        self, repository: InMemoryCanonicalScoreRepository, document: ScoreDocumentV1
    ) -> None:
        with pytest.raises(DocumentNotFoundError, match="DOCUMENT_NOT_FOUND"):
            repository.save_document(document)

    def test_save_updates_an_existing_document(
        self, stored: InMemoryCanonicalScoreRepository, document: ScoreDocumentV1
    ) -> None:
        advanced = document.with_revision(
            current_revision_id="rev-" + "a" * 24, revision_count=2
        )
        stored.save_document(advanced)
        assert stored.get_document(DOCUMENT_ID).revision_count == 2

    def test_has_document(
        self, stored: InMemoryCanonicalScoreRepository
    ) -> None:
        assert stored.has_document(DOCUMENT_ID) is True
        assert stored.has_document("score-absent") is False

    def test_wrong_type_rejected(
        self, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        with pytest.raises(ScoreRepositoryError, match="ScoreDocumentV1"):
            repository.create_document("not-a-document")  # type: ignore[arg-type]
        with pytest.raises(ScoreRepositoryError, match="ScoreDocumentV1"):
            repository.save_document(42)  # type: ignore[arg-type]


class TestRevisions:
    def test_save_and_retrieve(
        self, stored: InMemoryCanonicalScoreRepository, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        assert stored.get_revision(origin_revision.revision_id) == origin_revision

    def test_missing_revision_has_a_named_error(
        self, stored: InMemoryCanonicalScoreRepository
    ) -> None:
        with pytest.raises(RevisionNotFoundError, match="REVISION_NOT_FOUND"):
            stored.get_revision("rev-" + "f" * 24)

    def test_a_revision_needs_its_document(
        self, repository: InMemoryCanonicalScoreRepository,
        origin_revision: CanonicalScoreRevisionV1,
    ) -> None:
        # A revision stored against a document that does not exist would be
        # unreachable through every documented access path.
        with pytest.raises(DocumentNotFoundError, match="DOCUMENT_NOT_FOUND"):
            repository.save_revision(origin_revision)

    def test_resaving_an_identical_revision_is_accepted(
        self, stored: InMemoryCanonicalScoreRepository, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        # Identity is content-addressed, so the same id necessarily means the same
        # content. Making retries harmless is what allows idempotent ingestion in A5.
        assert stored.save_revision(origin_revision) == origin_revision
        assert len(stored.list_revisions(DOCUMENT_ID)) == 1

    def test_same_id_with_different_content_is_refused(
        self, stored: InMemoryCanonicalScoreRepository, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        import dataclasses

        impostor = dataclasses.replace(origin_revision, created_at="2099-01-01T00:00:00Z")
        with pytest.raises(DuplicateRevisionError, match="different content"):
            stored.save_revision(impostor)

    def test_wrong_type_rejected(
        self, stored: InMemoryCanonicalScoreRepository
    ) -> None:
        with pytest.raises(ScoreRepositoryError, match="CanonicalScoreRevisionV1"):
            stored.save_revision("not-a-revision")  # type: ignore[arg-type]


class TestCurrentRevisionAndHistory:
    def test_current_revision_resolves(
        self, stored: InMemoryCanonicalScoreRepository, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        assert stored.get_current_revision(DOCUMENT_ID) == origin_revision

    def test_current_revision_of_a_missing_document_is_named(
        self, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        with pytest.raises(DocumentNotFoundError, match="DOCUMENT_NOT_FOUND"):
            repository.get_current_revision("score-absent")

    def test_history_is_ordered_by_revision_number(
        self, stored: InMemoryCanonicalScoreRepository, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        third = make_revision(
            revision_number=3, parent_revision_id="rev-" + "b" * 24, digest_label="r3"
        )
        second = make_revision(
            revision_number=2, parent_revision_id=origin_revision.revision_id, digest_label="r2"
        )
        stored.save_revision(third)
        stored.save_revision(second)
        assert [r.revision_number for r in stored.list_revisions(DOCUMENT_ID)] == [1, 2, 3]

    def test_history_of_a_missing_document_is_named(
        self, repository: InMemoryCanonicalScoreRepository
    ) -> None:
        with pytest.raises(DocumentNotFoundError, match="DOCUMENT_NOT_FOUND"):
            repository.list_revisions("score-absent")

    def test_history_of_a_new_document_is_empty(
        self, repository: InMemoryCanonicalScoreRepository, document: ScoreDocumentV1
    ) -> None:
        repository.create_document(document)
        assert repository.list_revisions(DOCUMENT_ID) == ()


class TestReturnedObjectsCannotBeMutated:
    def test_returned_revisions_are_frozen(
        self, stored: InMemoryCanonicalScoreRepository, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        import dataclasses

        retrieved = stored.get_revision(origin_revision.revision_id)
        with pytest.raises(dataclasses.FrozenInstanceError):
            retrieved.revision_number = 99  # type: ignore[misc]

    def test_returned_collections_are_tuples(
        self, stored: InMemoryCanonicalScoreRepository, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        # Returning stored objects directly is safe only because every stored type is
        # frozen with tuple collections.
        retrieved = stored.get_revision(origin_revision.revision_id)
        assert isinstance(retrieved.events, tuple)
        assert isinstance(stored.list_revisions(DOCUMENT_ID), tuple)

    def test_mutating_a_returned_history_does_not_affect_storage(
        self, stored: InMemoryCanonicalScoreRepository
    ) -> None:
        history = stored.list_revisions(DOCUMENT_ID)
        assert isinstance(history, tuple)
        assert len(stored.list_revisions(DOCUMENT_ID)) == len(history)


class TestRepositoryIsNotTheInvariantAuthority:
    def test_it_does_not_validate_lineage(
        self, stored: InMemoryCanonicalScoreRepository
    ) -> None:
        # A revision numbered 9 with an arbitrary parent stores fine. Contiguity is the
        # service's job, and duplicating it here would force every future persistent
        # adapter to reimplement domain policy.
        orphan = make_revision(
            revision_number=9, parent_revision_id="rev-" + "c" * 24, digest_label="orphan"
        )
        assert stored.save_revision(orphan).revision_number == 9

    def test_it_does_not_verify_digests(
        self, stored: InMemoryCanonicalScoreRepository
    ) -> None:
        # The fixture digest is a stand-in and does not match the content; the
        # repository stores it regardless.
        from master_all_strings.core.score.digest import verify_revision_digest

        revision = make_revision(events=(make_event(0),), digest_label="unverified")
        stored.save_revision(revision)
        assert verify_revision_digest(revision) is False

    def test_it_contains_no_lineage_vocabulary(self) -> None:
        from master_all_strings.core.score import repository as module

        source = inspect.getsource(module)
        for term in ("revision_number + 1", "NONCONTIGUOUS", "PARENT_REVISION_MISMATCH"):
            assert term not in source, term
