"""Authored lesson -> canonical score revision (DO-013).

Musical Core already knows how to mint a revision. What it did not have was a
path for *authored* content: the ingestion service describes music that was
observed being played, and its request demands ``capture_id``,
``source_session_id``, ``raw_capture_digest``, and ``capture_origin_ns``. A
lesson someone wrote has none of those, and inventing them to satisfy the shape
would produce a genuine revision carrying a false account of where the music came
from -- worse than having no revision, because it would look verified.

So authored lessons take the other door Core already provides:
``create_document_with_revision`` with ``MANUAL_CONSTRUCTION`` provenance. Same
authority, honest origin.

This module is a translator, not a second score model. It reads a
``ResolvedLessonV1`` and hands Core the inputs it asks for; every musical value
crossing it is passed through unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.core.score.ids import LessonDocumentIdAuthority
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.models import CanonicalScoreRevisionV1
from master_all_strings.core.score.provenance import RevisionProvenanceV1, ScoreSourceKind
from master_all_strings.core.score.repository import InMemoryCanonicalScoreRepository
from master_all_strings.core.score.revision_service import CanonicalRevisionService
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.lesson.errors import LessonValidationError
from master_all_strings.lesson.resolver import ResolvedLessonV1

__all__ = [
    "AUTHORED_LESSON_POLICY_VERSION",
    "AuthoredLessonRevisionV1",
    "build_authored_lesson_revision",
]

#: Names the translation this module performs, so a revision's provenance says
#: which policy produced it rather than only that a human wrote the music.
AUTHORED_LESSON_POLICY_VERSION = "AUTHORED_LESSON_REVISION_V1"


@dataclass(frozen=True)
class AuthoredLessonRevisionV1:
    """A lesson's canonical revision plus the document identity that holds it."""

    document_id: str
    revision: CanonicalScoreRevisionV1

    @property
    def revision_id(self) -> str:
        return self.revision.revision_id


def _tempo_changes(resolved: ResolvedLessonV1) -> tuple[TempoChangeV1, ...]:
    """Canonical tempo map for the lesson.

    ``PlaybackRequestV1`` carries the resolved tempo the transport will use, which
    may be a teacher override. The canonical revision records the music as
    authored, so the *source* tempo is what belongs here; an override is a
    playback instruction, not a change to the work.
    """

    bpm = resolved.playback.source_tempo_bpm or resolved.playback.tempo_bpm
    if bpm is None:
        raise LessonValidationError(
            "authored lesson has no tempo; refusing to assume one for a canonical "
            "revision",
            code="missing_tempo",
        )
    from master_all_strings.core.score.tempo import tempo_from_bpm

    return (tempo_from_bpm(bpm, tick=0),)


def _meter_changes(resolved: ResolvedLessonV1) -> tuple[MeterChangeV1, ...]:
    """Canonical meter map, defaulting only where the corpus declares nothing.

    A lesson with no declared meter is not a lesson in no meter; it is a lesson
    whose author left the common case implicit. 4/4 at tick 0 is recorded
    explicitly so the revision never carries an empty meter map that downstream
    measure partitioning would have to guess about.
    """

    if resolved.meter_changes:
        return resolved.meter_changes
    return (
        MeterChangeV1(
            schema_version=MeterChangeV1.SCHEMA_VERSION,
            tick=0,
            numerator=4,
            denominator=4,
        ),
    )


def build_authored_lesson_revision(
    resolved: ResolvedLessonV1,
    *,
    created_at: str,
) -> AuthoredLessonRevisionV1:
    """Mint the canonical revision for one authored lesson.

    Deterministic by construction: the document id comes from the lesson's stable
    ``content_id``, and Core derives the revision id from that plus the canonical
    musical content. The same lesson therefore yields the same revision id on
    every export, and editing its music yields a new one under the same document.

    ``created_at`` is required and has no default. Core excludes it from the
    content digest, so it cannot move the revision id -- but it is written into
    the exported artifact, and a default would let a caller ship a timestamp it
    never chose. Bundled lessons pass their own
    ``provenance.created_at_utc``; synthetic fixtures pass an explicitly
    synthetic stamp of their own. Neither may read a wall clock, which would make
    a checked-in artifact differ on every export for a reason that has nothing to
    do with the lesson.

    A fresh in-memory repository is used per call. The revision's *identity* is
    what survives -- carried into the projections and written to the exported
    artifact -- so nothing here needs to outlive the call. Persistence is a
    separate concern this tranche deliberately does not take on.
    """

    if not isinstance(resolved, ResolvedLessonV1):
        raise LessonValidationError(
            "expected ResolvedLessonV1", code="invalid_resolved_lesson"
        )

    authority = LessonDocumentIdAuthority(resolved.content_id)
    service = CanonicalRevisionService(InMemoryCanonicalScoreRepository(), authority)

    provenance = RevisionProvenanceV1(
        schema_version=RevisionProvenanceV1.SCHEMA_VERSION,
        # Authored, not captured. This is the field that would have had to lie if
        # the lesson had been pushed through performance ingestion.
        source_kind=ScoreSourceKind.MANUAL_CONSTRUCTION,
        policy_version=AUTHORED_LESSON_POLICY_VERSION,
        source_reference=resolved.content_id,
    )

    creation = service.create_document_with_revision(
        created_at=created_at,
        provenance=provenance,
        events=resolved.events,
        tempo_changes=_tempo_changes(resolved),
        meter_changes=_meter_changes(resolved),
        ticks_per_quarter=resolved.playback.ticks_per_quarter,
        title=resolved.title,
    )
    return AuthoredLessonRevisionV1(
        document_id=creation.document.document_id, revision=creation.revision
    )
