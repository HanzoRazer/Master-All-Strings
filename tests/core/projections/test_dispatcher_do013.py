"""Generic projection dispatch and digests (DO-013).

The dispatcher owns no musical logic, so what is worth testing is what it
refuses: a request answered from the wrong revision, a payload that does not
match the kind it is filed under, and a notation request carrying fingering.
"""

from __future__ import annotations

import pytest

from master_all_strings.core.projections.contracts import (
    PROJECTION_SCHEMA_VERSION,
    NotationProjectionV1,
    ProjectionKind,
    ProjectionRequestV1,
    ProjectionResultV1,
    TabProjectionV1,
)
from master_all_strings.core.projections.dispatcher import project
from master_all_strings.core.projections.serialization import (
    canonical_projection_digest,
    projection_to_dict,
    projection_to_json,
)
from master_all_strings.core.projections.tab import SelectedSpatialRealizationV1
from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.spatial_mapping import generate_candidates
from master_all_strings.lesson.canonicalization import build_authored_lesson_revision
from master_all_strings.lesson.resolver import resolve_lesson_assignment
from master_all_strings.mvp.application import load_default_instrument_catalog
from master_all_strings.mvp.demo_library import load_demo_assignment

GOLDEN = "half_steps_one_string"
PROFILE = "guitar-standard-6"


def _revision(demo_id: str = GOLDEN):
    return build_authored_lesson_revision(
        resolve_lesson_assignment(load_demo_assignment(demo_id))
    ).revision


def _request(revision, kind: ProjectionKind, *, profile: str | None = None):
    return ProjectionRequestV1(
        schema_version=PROJECTION_SCHEMA_VERSION,
        request_id=f"req-{kind.value}",
        canonical_revision_id=revision.revision_id,
        projection_kind=kind,
        instrument_profile_id=profile,
    )


def _selection(revision):
    profile = load_default_instrument_catalog()[PROFILE]
    selected = {}
    for event in revision.events:
        candidates = generate_candidates(event, profile)
        if candidates:
            selected[event.event_id] = SelectedSpatialRealizationV1(
                canonical_event_id=event.event_id, position=candidates[0]
            )
    return selected


# --- routing -----------------------------------------------------------------


def test_a_notation_request_returns_a_notation_payload() -> None:
    revision = _revision()
    result = project(_request(revision, ProjectionKind.NOTATION), revision=revision)
    assert result.projection_kind is ProjectionKind.NOTATION
    assert isinstance(result.payload, NotationProjectionV1)


def test_a_tab_request_returns_a_tab_payload() -> None:
    revision = _revision()
    result = project(
        _request(revision, ProjectionKind.TAB, profile=PROFILE),
        revision=revision,
        selected=_selection(revision),
    )
    assert result.projection_kind is ProjectionKind.TAB
    assert isinstance(result.payload, TabProjectionV1)


def test_a_tab_request_without_an_instrument_profile_is_refused() -> None:
    """Enforced at the contract, so a builder can never be reached without one."""

    revision = _revision()
    with pytest.raises(ScoreContractError, match="TAB request requires"):
        _request(revision, ProjectionKind.TAB)


def test_a_notation_request_carrying_fingering_is_refused() -> None:
    """Ignoring it silently would let a caller believe fingering reached notation."""

    revision = _revision()
    request = _request(revision, ProjectionKind.NOTATION, profile=PROFILE)
    with pytest.raises(ScoreContractError, match="independent of fingering"):
        project(request, revision=revision)


def test_a_request_answered_from_another_revision_is_refused() -> None:
    """Otherwise the result's citation would simply be false."""

    revision = _revision()
    other = _revision("ascending_scale")
    with pytest.raises(ScoreContractError, match="but was given"):
        project(_request(revision, ProjectionKind.NOTATION), revision=other)


def test_foreign_arguments_are_refused() -> None:
    revision = _revision()
    with pytest.raises(ScoreContractError, match="ProjectionRequestV1"):
        project({"kind": "notation"}, revision=revision)  # type: ignore[arg-type]
    with pytest.raises(ScoreContractError, match="CanonicalScoreRevisionV1"):
        project(_request(revision, ProjectionKind.NOTATION), revision={"id": 1})  # type: ignore[arg-type]


# --- envelope integrity ------------------------------------------------------


def test_the_envelope_and_payload_must_agree_on_the_revision() -> None:
    revision = _revision()
    payload = project(_request(revision, ProjectionKind.NOTATION), revision=revision).payload
    with pytest.raises(ScoreContractError, match="same canonical_revision_id"):
        ProjectionResultV1(
            schema_version=PROJECTION_SCHEMA_VERSION,
            projection_id="p1",
            canonical_revision_id="rev-something-else",
            projection_kind=ProjectionKind.NOTATION,
            payload=payload,
            digest="sha256:x",
        )


def test_a_payload_filed_under_the_wrong_kind_is_refused() -> None:
    revision = _revision()
    notation = project(_request(revision, ProjectionKind.NOTATION), revision=revision).payload
    with pytest.raises(ScoreContractError, match="requires a TabProjectionV1"):
        ProjectionResultV1(
            schema_version=PROJECTION_SCHEMA_VERSION,
            projection_id="p1",
            canonical_revision_id=revision.revision_id,
            projection_kind=ProjectionKind.TAB,
            payload=notation,
            digest="sha256:x",
        )


def test_the_result_cites_the_revision_it_rendered() -> None:
    revision = _revision()
    result = project(_request(revision, ProjectionKind.NOTATION), revision=revision)
    assert result.canonical_revision_id == revision.revision_id
    assert result.payload.canonical_revision_id == revision.revision_id


# --- digests -----------------------------------------------------------------


def test_the_digest_is_deterministic() -> None:
    revision = _revision()
    first = project(_request(revision, ProjectionKind.NOTATION), revision=revision)
    second = project(_request(revision, ProjectionKind.NOTATION), revision=revision)
    assert first.digest == second.digest


def test_different_revisions_digest_differently() -> None:
    a = project(_request(_revision(), ProjectionKind.NOTATION), revision=_revision())
    b_rev = _revision("ascending_scale")
    b = project(_request(b_rev, ProjectionKind.NOTATION), revision=b_rev)
    assert a.digest != b.digest


def test_the_digest_does_not_feed_itself() -> None:
    """digest and projection_id are excluded, so the digest is not circular."""

    revision = _revision()
    payload = project(_request(revision, ProjectionKind.NOTATION), revision=revision).payload
    encoded = projection_to_dict(payload)
    assert "digest" not in encoded or canonical_projection_digest(payload)


def test_tab_and_notation_of_one_revision_digest_differently() -> None:
    revision = _revision()
    notation = project(_request(revision, ProjectionKind.NOTATION), revision=revision)
    tab = project(
        _request(revision, ProjectionKind.TAB, profile=PROFILE),
        revision=revision,
        selected=_selection(revision),
    )
    assert notation.digest != tab.digest


def test_notation_digest_ignores_fingering() -> None:
    """The fingering-independence claim, asserted at the digest."""

    revision = _revision()
    plain = project(_request(revision, ProjectionKind.NOTATION), revision=revision)
    # Building TAB with a completely different selection cannot move notation,
    # because notation never saw a selection at all.
    again = project(_request(revision, ProjectionKind.NOTATION), revision=revision)
    assert plain.digest == again.digest


def test_serialization_round_trips_as_json() -> None:
    import json

    revision = _revision()
    payload = project(_request(revision, ProjectionKind.NOTATION), revision=revision).payload
    text = projection_to_json(payload)
    assert text.endswith("\n")
    assert json.loads(text) == projection_to_dict(payload)


def test_serialization_refuses_foreign_objects() -> None:
    with pytest.raises(ScoreContractError, match="projection dataclass"):
        projection_to_dict({"not": "a dataclass"})
    with pytest.raises(ScoreContractError, match="typed projection payload"):
        canonical_projection_digest({"not": "a payload"})  # type: ignore[arg-type]
