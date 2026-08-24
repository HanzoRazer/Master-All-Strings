"""Authored lesson -> canonical revision (DO-013).

The invariants here are the ones that decide whether the revision seam is real
or theatre. A revision that is minted honestly but whose identity churns on every
export is useless; one whose identity is stable but whose provenance is invented
is worse than useless, because it looks verified.
"""

from __future__ import annotations

import pytest

from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.ids import LessonDocumentIdAuthority
from master_all_strings.core.score.models import CanonicalScoreRevisionV1
from master_all_strings.core.score.provenance import ScoreSourceKind
from master_all_strings.lesson.canonicalization import (
    AUTHORED_LESSON_CREATED_AT,
    AUTHORED_LESSON_POLICY_VERSION,
    build_authored_lesson_revision,
)
from master_all_strings.lesson.errors import LessonValidationError
from master_all_strings.lesson.resolver import resolve_lesson_assignment
from master_all_strings.mvp.demo_library import load_demo_assignment, load_demo_manifest

GOLDEN = "half_steps_one_string"


def _resolved(demo_id: str = GOLDEN):
    return resolve_lesson_assignment(load_demo_assignment(demo_id))


def _demo_ids() -> list[str]:
    return [entry.demo_id for entry in load_demo_manifest()]


# --- provenance --------------------------------------------------------------


def test_authored_lessons_are_manual_construction_not_capture() -> None:
    """The field that would have had to lie if ingestion had been used."""

    revision = build_authored_lesson_revision(_resolved()).revision
    assert revision.provenance.source_kind is ScoreSourceKind.MANUAL_CONSTRUCTION
    assert revision.provenance.source_kind is not ScoreSourceKind.PERFORMANCE_CAPTURE


def test_no_capture_evidence_is_fabricated() -> None:
    """Nothing in the revision claims a performance that never happened."""

    revision = build_authored_lesson_revision(_resolved()).revision
    assert revision.provenance.event_provenance == ()
    assert revision.provenance.policy_version == AUTHORED_LESSON_POLICY_VERSION
    assert revision.provenance.source_reference == GOLDEN


# --- document identity -------------------------------------------------------


def test_document_id_derives_from_lesson_identity() -> None:
    assert LessonDocumentIdAuthority(GOLDEN).document_id == f"score-{GOLDEN}"


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_document_id_is_stable_across_builds(demo_id: str) -> None:
    resolved = _resolved(demo_id)
    first = build_authored_lesson_revision(resolved).document_id
    second = build_authored_lesson_revision(resolved).document_id
    assert first == second == f"score-{demo_id}"


def test_document_id_is_not_the_content_digest() -> None:
    """The identity of a work is not the identity of its current state.

    Deriving the document id from musical bytes would collapse "which work is
    this" into "which state is it in", and every edit would become a new work.
    """

    built = build_authored_lesson_revision(_resolved())
    assert built.document_id != built.revision.content_digest
    assert built.document_id != built.revision_id
    assert built.revision.content_digest not in built.document_id


def test_editing_the_music_keeps_the_document_and_moves_the_revision() -> None:
    """The central invariant: same work, new state."""

    from dataclasses import replace

    resolved = _resolved()
    original = build_authored_lesson_revision(resolved)

    edited_events = (replace(resolved.events[0], midi_note=resolved.events[0].midi_note + 1),)
    edited = build_authored_lesson_revision(
        replace(resolved, events=edited_events + resolved.events[1:])
    )

    assert edited.document_id == original.document_id
    assert edited.revision_id != original.revision_id


def test_a_lesson_id_that_cannot_form_a_document_id_is_refused() -> None:
    """A path or a title reaching this authority means the caller passed the wrong thing."""

    for bad in ("bad/id.json", "has spaces", "UPPER/lower"):
        with pytest.raises(ScoreContractError):
            LessonDocumentIdAuthority(bad)


def test_the_authority_serves_a_lesson_more_than_once() -> None:
    """Re-export is not an error; the test-only fixed authority refuses a second call."""

    authority = LessonDocumentIdAuthority(GOLDEN)
    assert authority.next_document_id() == authority.next_document_id()


# --- revision identity -------------------------------------------------------


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_revision_id_is_deterministic(demo_id: str) -> None:
    resolved = _resolved(demo_id)
    assert (
        build_authored_lesson_revision(resolved).revision_id
        == build_authored_lesson_revision(resolved).revision_id
    )


def test_created_at_does_not_perturb_identity() -> None:
    """Core excludes created_at from the digest; this proves we rely on that."""

    resolved = _resolved()
    default = build_authored_lesson_revision(resolved)
    other = build_authored_lesson_revision(resolved, created_at="2099-12-31T23:59:59Z")
    assert other.revision_id == default.revision_id
    assert other.revision.created_at != default.revision.created_at


def test_created_at_is_fixed_so_the_exported_artifact_does_not_churn() -> None:
    revision = build_authored_lesson_revision(_resolved()).revision
    assert revision.created_at == AUTHORED_LESSON_CREATED_AT


def test_different_lessons_produce_different_revisions() -> None:
    ids = {
        build_authored_lesson_revision(_resolved(demo_id)).revision_id
        for demo_id in _demo_ids()
    }
    assert len(ids) == len(_demo_ids())


# --- musical content is carried, not reinterpreted ---------------------------


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_canonical_events_are_passed_through_unchanged(demo_id: str) -> None:
    resolved = _resolved(demo_id)
    revision = build_authored_lesson_revision(resolved).revision
    assert revision.events == resolved.events


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_ppq_and_meter_reach_the_revision(demo_id: str) -> None:
    resolved = _resolved(demo_id)
    revision = build_authored_lesson_revision(resolved).revision
    assert revision.ticks_per_quarter == resolved.playback.ticks_per_quarter
    assert revision.meter_changes, "a revision must carry a meter map"


def test_the_revision_records_source_tempo_not_a_playback_override() -> None:
    """A teacher slowing playback did not rewrite the work."""

    from dataclasses import replace

    resolved = _resolved()
    slowed = replace(resolved, playback=replace(resolved.playback, tempo_bpm=40.0))
    assert (
        build_authored_lesson_revision(slowed).revision_id
        == build_authored_lesson_revision(resolved).revision_id
    )


def test_a_lesson_with_no_tempo_is_refused_rather_than_defaulted() -> None:
    from dataclasses import replace

    resolved = _resolved()
    tempo_less = replace(
        resolved,
        playback=replace(resolved.playback, tempo_bpm=None, source_tempo_bpm=None),
    )
    with pytest.raises(LessonValidationError, match="refusing to assume"):
        build_authored_lesson_revision(tempo_less)


def test_an_absent_meter_map_becomes_an_explicit_common_time() -> None:
    """Implicit 4/4 is recorded explicitly rather than left for measures to guess."""

    from dataclasses import replace

    resolved = replace(_resolved(), meter_changes=())
    revision = build_authored_lesson_revision(resolved).revision
    assert [(m.numerator, m.denominator, m.tick) for m in revision.meter_changes] == [(4, 4, 0)]


def test_a_foreign_object_is_refused() -> None:
    with pytest.raises(LessonValidationError, match="ResolvedLessonV1"):
        build_authored_lesson_revision({"content_id": GOLDEN})  # type: ignore[arg-type]


def test_the_result_is_a_core_revision() -> None:
    revision = build_authored_lesson_revision(_resolved()).revision
    assert isinstance(revision, CanonicalScoreRevisionV1)
