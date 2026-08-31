"""Assemble one lesson's canonical revision and its score projections (DO-013).

One revision per lesson, built once and handed to both builders. Building it
twice would risk two projections citing two revisions of the same lesson, and the
whole point of the citation is that TAB and notation are two views of one thing.

This module carries no musical logic. It mints the revision through Core, turns
the orchestrator's selection record into the shape TAB requires, and asks the
dispatcher for both projections.
"""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.core.projections.contracts import (
    PROJECTION_SCHEMA_VERSION,
    NotationProjectionV1,
    ProjectionKind,
    ProjectionRequestV1,
    ProjectionResultV1,
    TabProjectionV1,
)
from master_all_strings.core.projections.dispatcher import project
from master_all_strings.core.projections.tab import SelectedSpatialRealizationV1
from master_all_strings.core.score.models import CanonicalScoreRevisionV1
from master_all_strings.lesson.canonicalization import build_authored_lesson_revision
from master_all_strings.lesson.resolver import ResolvedLessonV1
from master_all_strings.mvp.projection.builder import SelectedNoteInput

__all__ = ["ScoreProjectionBundleV1", "build_score_projection_bundle"]


@dataclass(frozen=True)
class ScoreProjectionBundleV1:
    """One lesson's canonical revision and the two projections of it."""

    document_id: str
    revision: CanonicalScoreRevisionV1
    tab: ProjectionResultV1
    notation: ProjectionResultV1

    @property
    def revision_id(self) -> str:
        return self.revision.revision_id

    @property
    def tab_payload(self) -> TabProjectionV1:
        payload = self.tab.payload
        assert isinstance(payload, TabProjectionV1)
        return payload

    @property
    def notation_payload(self) -> NotationProjectionV1:
        payload = self.notation.payload
        assert isinstance(payload, NotationProjectionV1)
        return payload


def _realizations(
    selected_notes: tuple[SelectedNoteInput, ...],
) -> dict[str, SelectedSpatialRealizationV1]:
    """Translate the orchestrator's selection record for TAB.

    A pass-through, not a decision: whatever selection concluded -- a position, or
    a reason there is none -- is what TAB receives.
    """

    realizations: dict[str, SelectedSpatialRealizationV1] = {}
    for item in selected_notes:
        realizations[item.event.event_id] = SelectedSpatialRealizationV1(
            canonical_event_id=item.event.event_id,
            position=item.position,
            unplayable_reason=item.unresolved_reason if item.position is None else None,
        )
    return realizations


def build_score_projection_bundle(
    resolved: ResolvedLessonV1,
    *,
    instrument_profile_id: str,
    selected_notes: tuple[SelectedNoteInput, ...],
    created_at: str,
) -> ScoreProjectionBundleV1:
    """Mint the lesson's revision and project it as TAB and notation.

    ``created_at`` is passed through rather than defaulted here: the lesson's own
    provenance stamp lives on the assignment, which the orchestrator holds and
    this module does not.
    """

    authored = build_authored_lesson_revision(resolved, created_at=created_at)
    revision = authored.revision

    tab = project(
        ProjectionRequestV1(
            schema_version=PROJECTION_SCHEMA_VERSION,
            request_id=f"tab:{revision.revision_id}",
            canonical_revision_id=revision.revision_id,
            projection_kind=ProjectionKind.TAB,
            instrument_profile_id=instrument_profile_id,
        ),
        revision=revision,
        selected=_realizations(selected_notes),
    )
    notation = project(
        ProjectionRequestV1(
            schema_version=PROJECTION_SCHEMA_VERSION,
            request_id=f"notation:{revision.revision_id}",
            canonical_revision_id=revision.revision_id,
            projection_kind=ProjectionKind.NOTATION,
        ),
        revision=revision,
    )
    return ScoreProjectionBundleV1(
        document_id=authored.document_id, revision=revision, tab=tab, notation=notation
    )
