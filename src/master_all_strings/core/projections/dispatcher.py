"""Generic projection dispatch (DO-013).

Materializes the boundary governance already describes: a caller asks for a
projection of an existing revision, Core answers with the typed payload wrapped
in the registered envelope.

The dispatcher owns no musical logic. Its whole job is to route a request to the
one builder that can answer it and to refuse requests it cannot satisfy — which
is why the interesting code here is validation rather than computation.
"""

from __future__ import annotations

from collections.abc import Mapping

from master_all_strings.core.projections.contracts import (
    PROJECTION_SCHEMA_VERSION,
    NotationDisplayPolicy,
    NotationProjectionV1,
    ProjectionKind,
    ProjectionRequestV1,
    ProjectionResultV1,
    TabProjectionV1,
)
from master_all_strings.core.projections.notation import build_notation_projection
from master_all_strings.core.projections.serialization import canonical_projection_digest
from master_all_strings.core.projections.tab import (
    SelectedSpatialRealizationV1,
    build_tab_projection,
)
from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.models import CanonicalScoreRevisionV1

__all__ = ["project"]


def project(
    request: ProjectionRequestV1,
    *,
    revision: CanonicalScoreRevisionV1,
    selected: Mapping[str, SelectedSpatialRealizationV1] | None = None,
    display_policy: NotationDisplayPolicy = NotationDisplayPolicy.SHARP_PREFERRED_V1,
) -> ProjectionResultV1:
    """Answer one projection request against one canonical revision.

    The revision is passed in rather than looked up: this tranche deliberately
    ships no persistent score repository, and a dispatcher that resolved ids
    itself would be the beginning of one.
    """

    if not isinstance(request, ProjectionRequestV1):
        raise ScoreContractError("expected ProjectionRequestV1")
    if not isinstance(revision, CanonicalScoreRevisionV1):
        raise ScoreContractError("expected CanonicalScoreRevisionV1")
    # A request naming one revision answered from another would produce a result
    # whose citation is simply false.
    if request.canonical_revision_id != revision.revision_id:
        raise ScoreContractError(
            f"request cites revision {request.canonical_revision_id} but was given "
            f"{revision.revision_id}"
        )

    payload: TabProjectionV1 | NotationProjectionV1
    if request.projection_kind is ProjectionKind.TAB:
        if request.instrument_profile_id is None:  # pragma: no cover - contract enforces
            raise ScoreContractError("a TAB request requires an instrument_profile_id")
        payload = build_tab_projection(
            revision,
            instrument_profile_id=request.instrument_profile_id,
            selected=selected or {},
        )
    else:
        # Notation takes no instrument profile. Silently ignoring one that was
        # supplied would let a caller believe fingering reached the notation.
        if request.instrument_profile_id is not None:
            raise ScoreContractError(
                "a notation request must not carry an instrument_profile_id: "
                "notation is independent of fingering"
            )
        payload = build_notation_projection(revision, display_policy=display_policy)

    return ProjectionResultV1(
        schema_version=PROJECTION_SCHEMA_VERSION,
        projection_id=f"{request.projection_kind.value}:{revision.revision_id}",
        canonical_revision_id=revision.revision_id,
        projection_kind=request.projection_kind,
        payload=payload,
        digest=canonical_projection_digest(payload),
        unsupported_features=payload.unsupported_features,
    )
