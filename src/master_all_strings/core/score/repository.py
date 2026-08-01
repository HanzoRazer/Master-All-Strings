"""Storage boundary for canonical scores.

A port with an in-memory implementation behind it, and deliberately nothing else in
DO-007: no database, ORM, filesystem authority, or network service. Choosing storage
before the model is settled would fix the wrong constraint first.

**The repository is not the invariant authority.** It stores objects that are already
valid and rejects only what storage itself can see — a duplicate key, a missing key, a
pointer that would not resolve. Lineage, contiguity, digest correctness, and
next-revision issuance belong to ``CanonicalRevisionService``. Putting domain policy
here would force every future persistent adapter to reimplement it, and adapters
reimplementing policy is how two storage backends come to disagree about what a valid
revision is.

**Atomicity is the port's problem, not the caller's.** Creating a document and its
origin revision is one act, so it is one method. Leaving the caller to sequence two
writes cannot be made correct in any order, and the requirement would then be invisible
to whoever writes the first persistent adapter.

There is deliberately **no bare ``create_document``**. ``ScoreDocumentV1`` requires a
``current_revision_id``, so a document cannot exist before the revision it points at —
which means a lone create could only ever store a dangling pointer. Keeping it as a
convenience would have left the exact failure the paired method exists to prevent
sitting one call away, reachable by any adapter author or caller who did not read this
paragraph. A document is always created with its origin.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from master_all_strings.core.score.errors import ScoreContractError, require_identifier
from master_all_strings.core.score.models import CanonicalScoreRevisionV1, ScoreDocumentV1


class ScoreRepositoryError(ScoreContractError):
    """Raised for storage-level failures, with a named reason."""


class DocumentNotFoundError(ScoreRepositoryError):
    """DOCUMENT_NOT_FOUND."""


class RevisionNotFoundError(ScoreRepositoryError):
    """REVISION_NOT_FOUND."""


class DuplicateDocumentError(ScoreRepositoryError):
    """A document id was created twice."""


class DuplicateRevisionError(ScoreRepositoryError):
    """A revision id was saved twice with different content."""


class RevisionIdCollisionError(DuplicateRevisionError):
    """REVISION_ID_COLLISION.

    Two different contents produced one revision id. ``revision_id`` carries the first
    24 hex characters of the digest — 96 bits — so this is vanishingly unlikely, but it
    is the one failure the shortening could cause and storage is the only place that can
    observe it. Named separately so it can never be read as an ordinary retry.
    """


@runtime_checkable
class CanonicalScoreRepositoryPort(Protocol):
    """What Musical Core needs from storage."""

    def create_document_with_origin_revision(
        self, document: ScoreDocumentV1, revision: CanonicalScoreRevisionV1
    ) -> tuple[ScoreDocumentV1, CanonicalScoreRevisionV1]:
        """Store a new document and its origin revision as one indivisible act.

        Two calls cannot express this. A document is born already pointing at its origin
        revision, so creating the document first opens a window where its
        ``current_revision_id`` names a revision that does not exist; and saving the
        revision first is refused, because ``save_revision`` requires its document to be
        there. Either order leaves a reader between the two writes able to observe a
        document that cannot be resolved.

        Every adapter must make this atomic -- a persistent one inside a transaction,
        the in-memory one by validating fully before it writes anything. On refusal an
        adapter must leave storage exactly as it found it: no document, no revision. An
        adapter that writes the document and then fails on the revision reintroduces the
        dangling ``current_revision_id`` this method exists to prevent.

        Revision sameness and first-write-wins follow ``save_revision``.

        ``tests/core/score/test_repository_contract.py`` is the conformance suite. Any
        new adapter runs it -- ``isinstance`` against this Protocol proves only that the
        method *names* exist, not that they behave.
        """
        ...

    def save_document(self, document: ScoreDocumentV1) -> ScoreDocumentV1:
        """Store an updated document. Fails if the id does not exist."""
        ...

    def save_revision(self, revision: CanonicalScoreRevisionV1) -> CanonicalScoreRevisionV1:
        """Store a revision. Fails if the id exists with a different digest.

        Sameness is decided by ``content_digest``, not by whole-object equality: the
        digest excludes ``created_at`` and ``provenance``, so a retry differing only in
        those is the same revision. First write wins, and the **stored** revision is
        returned, which may not be the one submitted.
        """
        ...

    def get_document(self, document_id: str) -> ScoreDocumentV1:
        """Return a document or raise ``DocumentNotFoundError``."""
        ...

    def get_revision(self, revision_id: str) -> CanonicalScoreRevisionV1:
        """Return a revision or raise ``RevisionNotFoundError``."""
        ...

    def get_current_revision(self, document_id: str) -> CanonicalScoreRevisionV1:
        """Return the revision a document currently points at."""
        ...

    def list_revisions(self, document_id: str) -> tuple[CanonicalScoreRevisionV1, ...]:
        """Return a document's revisions ordered by revision number."""
        ...

    def has_document(self, document_id: str) -> bool:
        """Whether a document exists."""
        ...


class InMemoryCanonicalScoreRepository:
    """A dict-backed repository. The only implementation in DO-007.

    Returns the stored objects directly rather than copies, which is safe precisely
    because every stored type is a frozen dataclass with tuple collections — a caller
    cannot mutate what it receives.
    """

    def __init__(self) -> None:
        self._documents: dict[str, ScoreDocumentV1] = {}
        self._revisions: dict[str, CanonicalScoreRevisionV1] = {}
        self._by_document: dict[str, list[str]] = {}

    def create_document_with_origin_revision(
        self, document: ScoreDocumentV1, revision: CanonicalScoreRevisionV1
    ) -> tuple[ScoreDocumentV1, CanonicalScoreRevisionV1]:
        """Store a new document and its origin revision atomically.

        Everything that could refuse the write is checked before the first mutation, so
        a rejection leaves the repository exactly as it was rather than holding a
        document whose ``current_revision_id`` resolves to nothing.
        """
        if not isinstance(document, ScoreDocumentV1):
            raise ScoreRepositoryError(
                "create_document_with_origin_revision requires a ScoreDocumentV1"
            )
        if not isinstance(revision, CanonicalScoreRevisionV1):
            raise ScoreRepositoryError(
                "create_document_with_origin_revision requires a CanonicalScoreRevisionV1"
            )
        if document.document_id in self._documents:
            raise DuplicateDocumentError(f"document {document.document_id!r} already exists")
        if revision.document_id != document.document_id:
            raise ScoreRepositoryError(
                f"revision {revision.revision_id!r} belongs to {revision.document_id!r}, "
                f"not to the document being created ({document.document_id!r})"
            )
        if document.current_revision_id != revision.revision_id:
            raise ScoreRepositoryError(
                f"document {document.document_id!r} points at "
                f"{document.current_revision_id!r}, not at the origin revision "
                f"{revision.revision_id!r} it is being created with"
            )
        existing = self._revisions.get(revision.revision_id)
        if existing is not None and existing.content_digest != revision.content_digest:
            raise RevisionIdCollisionError(
                f"REVISION_ID_COLLISION: revision {revision.revision_id!r} already "
                f"exists with digest {existing.content_digest!r}, and is now offered "
                f"with {revision.content_digest!r}"
            )

        self._documents[document.document_id] = document
        self._by_document.setdefault(document.document_id, [])
        # First write wins, exactly as in ``save_revision``. Overwriting here instead
        # would make two methods resolve the identical situation in opposite directions
        # -- one keeping the stored revision, the other replacing it -- so which
        # ``created_at`` survived a retry would depend on which entry point ran.
        stored = existing if existing is not None else revision
        self._revisions[revision.revision_id] = stored
        if revision.revision_id not in self._by_document[document.document_id]:
            self._by_document[document.document_id].append(revision.revision_id)
        return document, stored

    def save_document(self, document: ScoreDocumentV1) -> ScoreDocumentV1:
        """Store an updated document."""
        if not isinstance(document, ScoreDocumentV1):
            raise ScoreRepositoryError("save_document requires a ScoreDocumentV1")
        if document.document_id not in self._documents:
            raise DocumentNotFoundError(
                f"DOCUMENT_NOT_FOUND: {document.document_id!r}"
            )
        self._documents[document.document_id] = document
        return document

    def save_revision(self, revision: CanonicalScoreRevisionV1) -> CanonicalScoreRevisionV1:
        """Store a revision.

        Re-saving a revision whose digest matches the stored one is accepted, which is
        what makes ingestion retries harmless. A differing digest under the same id is
        refused as a collision.

        **First write wins, and the stored revision is what comes back.** The digest
        excludes ``created_at`` and ``provenance``, so a retry may differ in those and
        still be the same revision — and when it does, the earlier values are kept. A
        caller that needs its own ``created_at`` to be the one recorded is not retrying;
        it is trying to change a revision, which is what a new revision is for. Read the
        returned object rather than assuming the submitted one was stored.
        """
        if not isinstance(revision, CanonicalScoreRevisionV1):
            raise ScoreRepositoryError("save_revision requires a CanonicalScoreRevisionV1")
        if revision.document_id not in self._documents:
            raise DocumentNotFoundError(
                f"DOCUMENT_NOT_FOUND: {revision.document_id!r}"
            )
        existing = self._revisions.get(revision.revision_id)
        if existing is not None:
            # Compared by digest, not by dataclass equality. The id is derived from the
            # digest, and the digest deliberately excludes ``created_at`` and
            # ``provenance`` -- so the same music re-ingested a second later is the same
            # revision with a different ``created_at``, and whole-object equality called
            # that corruption. That rejected exactly the retry this method claims to
            # make harmless. A digest that genuinely differs under one id is the
            # shortened id colliding, which is a different failure and says so.
            if existing.content_digest != revision.content_digest:
                raise RevisionIdCollisionError(
                    f"REVISION_ID_COLLISION: revision {revision.revision_id!r} already "
                    f"exists with digest {existing.content_digest!r}, and is now offered "
                    f"with {revision.content_digest!r}"
                )
            return existing
        self._revisions[revision.revision_id] = revision
        self._by_document[revision.document_id].append(revision.revision_id)
        return revision

    def get_document(self, document_id: str) -> ScoreDocumentV1:
        """Return a document."""
        require_identifier(document_id, "document_id")
        document = self._documents.get(document_id)
        if document is None:
            raise DocumentNotFoundError(f"DOCUMENT_NOT_FOUND: {document_id!r}")
        return document

    def get_revision(self, revision_id: str) -> CanonicalScoreRevisionV1:
        """Return a revision."""
        require_identifier(revision_id, "revision_id")
        revision = self._revisions.get(revision_id)
        if revision is None:
            raise RevisionNotFoundError(f"REVISION_NOT_FOUND: {revision_id!r}")
        return revision

    def get_current_revision(self, document_id: str) -> CanonicalScoreRevisionV1:
        """Return the revision a document currently points at."""
        return self.get_revision(self.get_document(document_id).current_revision_id)

    def list_revisions(self, document_id: str) -> tuple[CanonicalScoreRevisionV1, ...]:
        """Return a document's revisions ordered by revision number."""
        self.get_document(document_id)
        revisions = [self._revisions[rid] for rid in self._by_document[document_id]]
        return tuple(sorted(revisions, key=lambda r: r.revision_number))

    def has_document(self, document_id: str) -> bool:
        """Whether a document exists."""
        require_identifier(document_id, "document_id")
        return document_id in self._documents
