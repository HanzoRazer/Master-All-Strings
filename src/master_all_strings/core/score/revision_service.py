"""The only sanctioned path for creating documents and revisions.

Every invariant that needs to see more than one object lives here: lineage, contiguous
numbering, parent ownership, digest correctness, and advancing a document's pointer.
The contracts in ``models`` enforce what is visible from a single object; the repository
stores what is already valid; this service is what makes a *history* correct.

Callers never choose a revision number or a revision id. Both are derived — the number
from the document's current count, the id from the content digest — so a caller cannot
fork a document by asserting a number, and cannot claim an identity that does not match
what it stored.
"""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.core.musical_events.models import MusicalEvent
from master_all_strings.core.score.canonicalize import (
    canonicalize_events,
    canonicalize_meter_changes,
    canonicalize_tempo_changes,
)
from master_all_strings.core.score.digest import (
    compute_revision_digest,
    derive_revision_id,
)
from master_all_strings.core.score.errors import ScoreContractError, require_identifier
from master_all_strings.core.score.ids import DocumentIdAuthority
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.models import (
    FIRST_REVISION_NUMBER,
    CanonicalScoreRevisionV1,
    ScoreDocumentV1,
)
from master_all_strings.core.score.provenance import RevisionProvenanceV1
from master_all_strings.core.score.repository import CanonicalScoreRepositoryPort
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.core.score.timing import DEFAULT_TICKS_PER_QUARTER


class RevisionServiceError(ScoreContractError):
    """Raised when a revision would violate a history invariant."""


class RevisionDocumentMismatchError(RevisionServiceError):
    """REVISION_DOCUMENT_MISMATCH."""


class ParentRevisionMismatchError(RevisionServiceError):
    """PARENT_REVISION_MISMATCH."""


class NoncontiguousRevisionError(RevisionServiceError):
    """NONCONTIGUOUS_REVISION."""


@dataclass(frozen=True)
class RevisionCreation:
    """A newly created revision and the document state that now points at it."""

    document: ScoreDocumentV1
    revision: CanonicalScoreRevisionV1

    @property
    def is_origin(self) -> bool:
        """Whether this created a document's first revision."""
        return self.revision.is_origin


class CanonicalRevisionService:
    """Creates documents and revisions under Musical Core's authority.

    ``created_at`` is supplied by the caller rather than read from a clock here, so the
    service is deterministic and a test does not have to freeze time. It never affects
    identity — the digest excludes it.
    """

    def __init__(
        self,
        repository: CanonicalScoreRepositoryPort,
        id_authority: DocumentIdAuthority,
    ) -> None:
        self._repository = repository
        self._id_authority = id_authority

    def create_document_with_revision(
        self,
        *,
        created_at: str,
        provenance: RevisionProvenanceV1,
        events: tuple[MusicalEvent, ...] = (),
        tempo_changes: tuple[TempoChangeV1, ...],
        meter_changes: tuple[MeterChangeV1, ...],
        ticks_per_quarter: int = DEFAULT_TICKS_PER_QUARTER,
        title: str | None = None,
        description: str | None = None,
        external_reference: str | None = None,
    ) -> RevisionCreation:
        """Create a new document and its origin revision as one act.

        A document without a revision would be a work with no state, and every
        consumer would have to handle that. The two are created together so the
        condition never exists.
        """
        document_id = self._id_authority.next_document_id()
        require_identifier(document_id, "document_id")

        revision = self._build_revision(
            document_id=document_id,
            revision_number=FIRST_REVISION_NUMBER,
            parent_revision_id=None,
            created_at=created_at,
            ticks_per_quarter=ticks_per_quarter,
            events=events,
            tempo_changes=tempo_changes,
            meter_changes=meter_changes,
            provenance=provenance,
        )
        document = ScoreDocumentV1(
            schema_version=ScoreDocumentV1.SCHEMA_VERSION,
            document_id=document_id,
            created_at=created_at,
            current_revision_id=revision.revision_id,
            revision_count=1,
            title=title,
            description=description,
            external_reference=external_reference,
        )
        # One call, because no ordering of two calls is correct here. The document is
        # built already pointing at its origin revision, so creating it first publishes
        # a pointer to a revision that is not stored yet, and saving the revision first
        # is refused because its document does not exist. The port owns the atomicity.
        stored_document, stored_revision = (
            self._repository.create_document_with_origin_revision(document, revision)
        )
        return RevisionCreation(document=stored_document, revision=stored_revision)

    def create_child_revision(
        self,
        *,
        document_id: str,
        created_at: str,
        provenance: RevisionProvenanceV1,
        events: tuple[MusicalEvent, ...] = (),
        tempo_changes: tuple[TempoChangeV1, ...],
        meter_changes: tuple[MeterChangeV1, ...],
        ticks_per_quarter: int | None = None,
    ) -> RevisionCreation:
        """Append a revision to an existing document.

        The parent and the revision number both come from the document's current
        state, never from the caller. A caller-chosen number could skip, repeat, or
        fork the history.
        """
        document = self._repository.get_document(document_id)
        parent = self._repository.get_revision(document.current_revision_id)
        self._require_parent_belongs(parent, document_id)

        revision = self._build_revision(
            document_id=document_id,
            revision_number=parent.revision_number + 1,
            parent_revision_id=parent.revision_id,
            created_at=created_at,
            ticks_per_quarter=(
                parent.ticks_per_quarter if ticks_per_quarter is None else ticks_per_quarter
            ),
            events=events,
            tempo_changes=tempo_changes,
            meter_changes=meter_changes,
            provenance=provenance,
        )
        self.verify_lineage(revision, parent)

        advanced = document.with_revision(
            current_revision_id=revision.revision_id,
            revision_count=document.revision_count + 1,
        )
        # Revision first here: the document pointer must never name a revision that is
        # not yet stored, or a reader between the two writes would get a dangling id.
        self._repository.save_revision(revision)
        self._repository.save_document(advanced)
        return RevisionCreation(document=advanced, revision=revision)

    def resolve_current_revision(self, document_id: str) -> CanonicalScoreRevisionV1:
        """Return the revision a document currently points at."""
        return self._repository.get_current_revision(document_id)

    def verify_lineage(
        self, revision: CanonicalScoreRevisionV1, parent: CanonicalScoreRevisionV1
    ) -> None:
        """Raise unless ``revision`` is a well-formed child of ``parent``."""
        if revision.document_id != parent.document_id:
            raise RevisionDocumentMismatchError(
                "REVISION_DOCUMENT_MISMATCH: "
                f"{revision.document_id!r} is not {parent.document_id!r}"
            )
        if revision.parent_revision_id != parent.revision_id:
            raise ParentRevisionMismatchError(
                "PARENT_REVISION_MISMATCH: "
                f"{revision.parent_revision_id!r} is not {parent.revision_id!r}"
            )
        if revision.revision_number != parent.revision_number + 1:
            raise NoncontiguousRevisionError(
                "NONCONTIGUOUS_REVISION: "
                f"{revision.revision_number} does not follow {parent.revision_number}"
            )

    def _require_parent_belongs(
        self, parent: CanonicalScoreRevisionV1, document_id: str
    ) -> None:
        if parent.document_id != document_id:
            raise RevisionDocumentMismatchError(
                "REVISION_DOCUMENT_MISMATCH: current revision "
                f"{parent.revision_id!r} belongs to {parent.document_id!r}"
            )

    def _build_revision(
        self,
        *,
        document_id: str,
        revision_number: int,
        parent_revision_id: str | None,
        created_at: str,
        ticks_per_quarter: int,
        events: tuple[MusicalEvent, ...],
        tempo_changes: tuple[TempoChangeV1, ...],
        meter_changes: tuple[MeterChangeV1, ...],
        provenance: RevisionProvenanceV1,
    ) -> CanonicalScoreRevisionV1:
        ordered_events = canonicalize_events(events)
        ordered_tempo = canonicalize_tempo_changes(tempo_changes)
        ordered_meter = canonicalize_meter_changes(meter_changes)

        digest = compute_revision_digest(
            document_id=document_id,
            revision_number=revision_number,
            parent_revision_id=parent_revision_id,
            ticks_per_quarter=ticks_per_quarter,
            events=ordered_events,
            tempo_changes=ordered_tempo,
            meter_changes=ordered_meter,
        )
        return CanonicalScoreRevisionV1(
            schema_version=CanonicalScoreRevisionV1.SCHEMA_VERSION,
            revision_id=derive_revision_id(digest),
            document_id=document_id,
            revision_number=revision_number,
            parent_revision_id=parent_revision_id,
            created_at=created_at,
            ticks_per_quarter=ticks_per_quarter,
            content_digest=digest,
            provenance=provenance,
            events=ordered_events,
            tempo_changes=ordered_tempo,
            meter_changes=ordered_meter,
        )
