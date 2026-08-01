"""The conformance suite every ``CanonicalScoreRepositoryPort`` adapter must pass.

`test_repository.py` tests the in-memory adapter's own behaviour. This file tests the
**port**: the behaviour `CanonicalRevisionService` relies on regardless of which adapter
is underneath. A future persistent adapter adds itself to ``ADAPTERS`` and inherits every
assertion here.

That indirection exists because the obvious check does not work. ``isinstance(adapter,
CanonicalScoreRepositoryPort)`` passes for any class with the right method *names* — a
``runtime_checkable`` Protocol does not compare signatures, let alone behaviour — so a
half-written adapter satisfies it while violating every rule below. The service assumes
those rules; something has to actually check them.

Two are the ones an adapter is most likely to get wrong, because both are invisible
until they have already caused damage:

* **Atomicity.** ``create_document_with_origin_revision`` writes two objects. A refusal
  must leave neither. An adapter that inserts the document and then fails on the revision
  is left holding a ``current_revision_id`` that resolves to nothing, which is exactly
  the condition the single method exists to prevent.
* **First write wins.** A retry that differs only in ``created_at`` or ``provenance`` is
  the same revision, because the digest excludes both. The stored one is kept and
  returned. An adapter that overwrites would make the recorded timestamp depend on how
  many times a client retried.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

import pytest

from conftest import (  # type: ignore[import-not-found]
    DOCUMENT_ID,
    make_event,
    make_revision,
)
from master_all_strings.core.score.models import CanonicalScoreRevisionV1, ScoreDocumentV1
from master_all_strings.core.score.repository import (
    CanonicalScoreRepositoryPort,
    DocumentNotFoundError,
    DuplicateDocumentError,
    InMemoryCanonicalScoreRepository,
    RevisionIdCollisionError,
    RevisionNotFoundError,
    ScoreRepositoryError,
)

# Every adapter of the port. A new one is added here and inherits the whole suite.
ADAPTERS: list[Callable[[], CanonicalScoreRepositoryPort]] = [
    InMemoryCanonicalScoreRepository,
]


@pytest.fixture(params=ADAPTERS, ids=lambda factory: factory.__name__)
def adapter(request: pytest.FixtureRequest) -> CanonicalScoreRepositoryPort:
    return request.param()  # type: ignore[no-any-return]


@pytest.fixture
def created(
    adapter: CanonicalScoreRepositoryPort,
    document: ScoreDocumentV1,
    origin_revision: CanonicalScoreRevisionV1,
) -> CanonicalScoreRepositoryPort:
    adapter.create_document_with_origin_revision(document, origin_revision)
    return adapter


class TestOriginCreationIsAtomic:
    def test_both_objects_are_readable_afterwards(
        self, created: CanonicalScoreRepositoryPort, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        assert created.get_document(DOCUMENT_ID).document_id == DOCUMENT_ID
        assert created.get_revision(origin_revision.revision_id) == origin_revision
        assert created.get_current_revision(DOCUMENT_ID) == origin_revision

    def test_the_document_pointer_always_resolves(
        self, created: CanonicalScoreRepositoryPort
    ) -> None:
        # The invariant the whole method exists for: whatever a document points at can
        # be fetched. An adapter that writes in two steps can violate this between them.
        document = created.get_document(DOCUMENT_ID)
        assert created.get_revision(document.current_revision_id) is not None

    @pytest.mark.parametrize("case", ["foreign_revision", "misdirected_pointer"])
    def test_a_refusal_writes_nothing_at_all(
        self,
        adapter: CanonicalScoreRepositoryPort,
        document: ScoreDocumentV1,
        origin_revision: CanonicalScoreRevisionV1,
        case: str,
    ) -> None:
        if case == "foreign_revision":
            doc, rev = document, make_revision(document_id="score-elsewhere")
        else:
            doc = dataclasses.replace(document, current_revision_id="rev-" + "c" * 24)
            rev = origin_revision

        with pytest.raises(ScoreRepositoryError):
            adapter.create_document_with_origin_revision(doc, rev)

        # Neither half may survive. A partially applied write is the failure mode.
        assert adapter.has_document(doc.document_id) is False
        with pytest.raises(DocumentNotFoundError):
            adapter.get_document(doc.document_id)
        with pytest.raises(RevisionNotFoundError):
            adapter.get_revision(rev.revision_id)

    def test_a_duplicate_document_is_refused(
        self,
        created: CanonicalScoreRepositoryPort,
        document: ScoreDocumentV1,
        origin_revision: CanonicalScoreRevisionV1,
    ) -> None:
        with pytest.raises(DuplicateDocumentError):
            created.create_document_with_origin_revision(document, origin_revision)


class TestRevisionSamenessIsDigestBased:
    def test_a_retry_differing_only_in_created_at_is_the_same_revision(
        self, created: CanonicalScoreRepositoryPort, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        retried = dataclasses.replace(origin_revision, created_at="2099-01-01T00:00:00Z")
        assert created.save_revision(retried) == origin_revision
        assert len(created.list_revisions(DOCUMENT_ID)) == 1

    def test_first_write_wins_and_the_stored_object_is_returned(
        self, created: CanonicalScoreRepositoryPort, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        # Otherwise the recorded timestamp would depend on how many times a client
        # retried, which is not something a client should be able to decide.
        retried = dataclasses.replace(origin_revision, created_at="2099-01-01T00:00:00Z")
        returned = created.save_revision(retried)
        assert returned.created_at == origin_revision.created_at
        assert created.get_revision(origin_revision.revision_id).created_at == (
            origin_revision.created_at
        )

    def test_both_write_paths_resolve_a_retry_the_same_way(
        self,
        adapter: CanonicalScoreRepositoryPort,
        document: ScoreDocumentV1,
        origin_revision: CanonicalScoreRevisionV1,
    ) -> None:
        # The two entry points must not disagree. If one kept the stored revision and
        # the other replaced it, which created_at survived would depend on which method
        # a caller happened to reach.
        adapter.save_revision  # noqa: B018 - documents the pair under test
        first = adapter.create_document_with_origin_revision(document, origin_revision)[1]
        retried = dataclasses.replace(origin_revision, created_at="2099-01-01T00:00:00Z")
        assert first.created_at == origin_revision.created_at
        assert adapter.save_revision(retried).created_at == origin_revision.created_at

    def test_a_differing_digest_under_one_id_is_a_named_collision(
        self, created: CanonicalScoreRepositoryPort, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        import copy

        collided = copy.deepcopy(origin_revision)
        object.__setattr__(
            collided, "content_digest", origin_revision.content_digest[:24] + "0" * 40
        )
        with pytest.raises(RevisionIdCollisionError):
            created.save_revision(collided)


class TestStorageOnlyRejectsWhatStorageCanSee:
    def test_a_revision_needs_its_document(
        self, adapter: CanonicalScoreRepositoryPort, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        with pytest.raises(DocumentNotFoundError):
            adapter.save_revision(origin_revision)

    def test_updating_an_unknown_document_is_refused(
        self, adapter: CanonicalScoreRepositoryPort, document: ScoreDocumentV1
    ) -> None:
        with pytest.raises(DocumentNotFoundError):
            adapter.save_document(document)

    def test_missing_keys_are_named(self, adapter: CanonicalScoreRepositoryPort) -> None:
        with pytest.raises(DocumentNotFoundError):
            adapter.get_document("score-absent")
        with pytest.raises(RevisionNotFoundError):
            adapter.get_revision("rev-" + "f" * 24)

    def test_history_is_ordered_by_revision_number(
        self, created: CanonicalScoreRepositoryPort, origin_revision: CanonicalScoreRevisionV1
    ) -> None:
        second = make_revision(
            revision_number=2,
            parent_revision_id=origin_revision.revision_id,
            events=(make_event(2),),
            digest_label="second",
        )
        created.save_revision(second)
        numbers = [r.revision_number for r in created.list_revisions(DOCUMENT_ID)]
        assert numbers == sorted(numbers)

    def test_has_document_answers_both_ways(
        self, created: CanonicalScoreRepositoryPort
    ) -> None:
        assert created.has_document(DOCUMENT_ID) is True
        assert created.has_document("score-absent") is False


class TestProtocolCheckIsNotEnough:
    def test_isinstance_passes_for_a_behaviourally_wrong_adapter(self) -> None:
        # The reason this file exists. A runtime_checkable Protocol compares method
        # names only, so this hollow class satisfies isinstance while implementing none
        # of the semantics above. Adding an adapter to ADAPTERS is the real check.
        class Hollow:
            def create_document(self) -> None: ...
            def create_document_with_origin_revision(self) -> None: ...
            def save_document(self) -> None: ...
            def save_revision(self) -> None: ...
            def get_document(self) -> None: ...
            def get_revision(self) -> None: ...
            def get_current_revision(self) -> None: ...
            def list_revisions(self) -> None: ...
            def has_document(self) -> None: ...

        assert isinstance(Hollow(), CanonicalScoreRepositoryPort)

    def test_every_port_method_is_exercised_by_this_suite(self) -> None:
        # Keeps the suite honest as the port grows: a method added to the port without
        # a conformance test here fails, rather than being covered only by whichever
        # adapter happened to implement it.
        source = __import__("pathlib").Path(__file__).read_text(encoding="utf-8")
        port_methods = {
            name
            for name in dir(CanonicalScoreRepositoryPort)
            if not name.startswith("_")
        }
        untested = {m for m in port_methods if f".{m}(" not in source}
        assert untested == set(), f"port methods with no conformance test: {untested}"
