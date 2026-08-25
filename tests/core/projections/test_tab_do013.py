"""TAB projection (DO-013).

TAB is the projection that could most easily start deciding things, because it
is the one that needs a string and a fret. The tests that matter are the ones
proving it never chooses: candidate order must not reach the output, a missing
selection must stay missing, and a selection that contradicts the canonical pitch
must be refused rather than drawn.
"""

from __future__ import annotations

import pytest

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.projections.contracts import TabEventStatus
from master_all_strings.core.projections.tab import (
    SelectedSpatialRealizationV1,
    build_tab_projection,
    validate_tab_spatial_identity,
)
from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.spatial_mapping import generate_candidates
from master_all_strings.lesson.canonicalization import build_authored_lesson_revision
from master_all_strings.lesson.resolver import resolve_lesson_assignment
from master_all_strings.mvp.application import load_default_instrument_catalog
from master_all_strings.mvp.demo_library import load_demo_assignment, load_demo_manifest

GOLDEN = "half_steps_one_string"
PROFILE = "guitar-standard-6"


def _revision(demo_id: str = GOLDEN):
    assignment = load_demo_assignment(demo_id)
    return build_authored_lesson_revision(
        resolve_lesson_assignment(assignment),
        created_at=assignment.provenance.created_at_utc,
    ).revision


def _profile():
    return load_default_instrument_catalog()[PROFILE]


def _candidates(event: MusicalEvent):
    return generate_candidates(event, _profile())


def _selection_for(revision, *, chooser=lambda cands: cands[0]):
    return {
        event.event_id: SelectedSpatialRealizationV1(
            canonical_event_id=event.event_id, position=chooser(_candidates(event))
        )
        for event in revision.events
        if _candidates(event)
    }


def _demo_ids() -> list[str]:
    return [entry.demo_id for entry in load_demo_manifest()]


# --- the selection rule ------------------------------------------------------


def test_tab_uses_the_selected_realization() -> None:
    revision = _revision()
    selected = _selection_for(revision)
    projection = build_tab_projection(
        revision, instrument_profile_id=PROFILE, selected=selected
    )
    for event in projection.events:
        chosen = selected[event.canonical_event_id].position
        assert chosen is not None
        assert event.string_id == chosen.string_id
        assert event.fret == chosen.physical_fret_number


def test_candidate_order_does_not_reach_the_output() -> None:
    """The invariant that proves TAB is not ranking anything.

    Two different selections over the same candidates produce two different TABs,
    and reordering the candidate list under a fixed selection changes nothing.
    """

    revision = _revision()
    first = _selection_for(revision, chooser=lambda c: c[0])
    last = _selection_for(revision, chooser=lambda c: c[-1])

    tab_first = build_tab_projection(revision, instrument_profile_id=PROFILE, selected=first)
    tab_last = build_tab_projection(revision, instrument_profile_id=PROFILE, selected=last)

    # Selection drives the output...
    assert [e.string_id for e in tab_first.events] != [e.string_id for e in tab_last.events] or all(
        len(_candidates(ev)) == 1 for ev in revision.events
    )

    # ...and reversing the candidate list while keeping the same chosen position
    # leaves the output untouched.
    reversed_same = {
        event.event_id: SelectedSpatialRealizationV1(
            canonical_event_id=event.event_id,
            position=list(reversed(_candidates(event)))[-1],
        )
        for event in revision.events
        if _candidates(event)
    }
    tab_reversed = build_tab_projection(
        revision, instrument_profile_id=PROFILE, selected=reversed_same
    )
    assert [(e.string_id, e.fret) for e in tab_reversed.events] == [
        (e.string_id, e.fret) for e in tab_first.events
    ]


def test_a_missing_selection_is_unresolved_not_guessed() -> None:
    """No candidate-zero fallback. An absent decision stays absent."""

    revision = _revision()
    projection = build_tab_projection(revision, instrument_profile_id=PROFILE, selected={})
    assert projection.events
    for event in projection.events:
        assert event.status is TabEventStatus.UNRESOLVED
        assert event.string_id is None
        assert event.fret is None


def test_a_partially_selected_lesson_reports_per_event() -> None:
    revision = _revision()
    full = _selection_for(revision)
    dropped = next(iter(full))
    partial = {key: value for key, value in full.items() if key != dropped}
    projection = build_tab_projection(
        revision, instrument_profile_id=PROFILE, selected=partial
    )
    by_id = {event.canonical_event_id: event for event in projection.events}
    assert by_id[dropped].status is TabEventStatus.UNRESOLVED
    assert all(
        by_id[key].status is TabEventStatus.PLAYABLE for key in partial
    )


def test_an_explicitly_unplayable_event_stays_represented() -> None:
    """The note is still in the score; TAB says it cannot be played, not nothing."""

    revision = _revision()
    target = revision.events[0].event_id
    selected = _selection_for(revision)
    selected[target] = SelectedSpatialRealizationV1(
        canonical_event_id=target, unplayable_reason="no_playable_position"
    )
    projection = build_tab_projection(
        revision, instrument_profile_id=PROFILE, selected=selected
    )
    by_id = {event.canonical_event_id: event for event in projection.events}
    assert by_id[target].status is TabEventStatus.UNPLAYABLE
    assert by_id[target].midi_note == revision.events[0].midi_note
    assert by_id[target].string_id is None


def test_a_realization_cannot_be_both_playable_and_unplayable() -> None:
    revision = _revision()
    position = _candidates(revision.events[0])[0]
    with pytest.raises(ScoreContractError, match="not both"):
        SelectedSpatialRealizationV1(
            canonical_event_id=revision.events[0].event_id,
            position=position,
            unplayable_reason="no_playable_position",
        )


def test_a_realization_keyed_to_another_event_is_refused() -> None:
    revision = _revision()
    position = _candidates(revision.events[0])[0]
    mismatched = {
        revision.events[0].event_id: SelectedSpatialRealizationV1(
            canonical_event_id="some-other-event", position=position
        )
    }
    with pytest.raises(ScoreContractError, match="different canonical event"):
        build_tab_projection(revision, instrument_profile_id=PROFILE, selected=mismatched)


# --- pitch consistency -------------------------------------------------------


def test_a_selection_that_sounds_the_wrong_pitch_is_refused() -> None:
    """Two authorities disagreeing is not something TAB may resolve quietly."""

    revision = _revision()
    event = revision.events[0]
    wrong = _candidates(event)[0]
    with pytest.raises(ScoreContractError, match="does not sound the canonical pitch"):
        validate_tab_spatial_identity(
            canonical_midi_note=event.midi_note + 1, position=wrong
        )


def test_the_builder_validates_every_playable_event() -> None:
    revision = _revision()
    other = next(e for e in revision.events if e.midi_note != revision.events[0].midi_note)
    selected = _selection_for(revision)
    # Point the first event at a realization that sounds a different pitch.
    selected[revision.events[0].event_id] = SelectedSpatialRealizationV1(
        canonical_event_id=revision.events[0].event_id, position=_candidates(other)[0]
    )
    with pytest.raises(ScoreContractError, match="canonical pitch"):
        build_tab_projection(revision, instrument_profile_id=PROFILE, selected=selected)


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_selected_realizations_reproduce_canonical_pitch(demo_id: str) -> None:
    revision = _revision(demo_id)
    projection = build_tab_projection(
        revision, instrument_profile_id=PROFILE, selected=_selection_for(revision)
    )
    canonical = {event.event_id: event.midi_note for event in revision.events}
    for event in projection.events:
        assert event.midi_note == canonical[event.canonical_event_id]


# --- projection shape --------------------------------------------------------


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_every_canonical_event_is_represented(demo_id: str) -> None:
    revision = _revision(demo_id)
    projection = build_tab_projection(
        revision, instrument_profile_id=PROFILE, selected=_selection_for(revision)
    )
    assert sorted(e.canonical_event_id for e in projection.events) == sorted(
        e.event_id for e in revision.events
    )


def test_events_are_ordered_by_start_tick() -> None:
    revision = _revision()
    projection = build_tab_projection(
        revision, instrument_profile_id=PROFILE, selected=_selection_for(revision)
    )
    ticks = [event.start_tick for event in projection.events]
    assert ticks == sorted(ticks)


def test_tab_cites_the_revision_it_rendered() -> None:
    revision = _revision()
    projection = build_tab_projection(
        revision, instrument_profile_id=PROFILE, selected=_selection_for(revision)
    )
    assert projection.canonical_revision_id == revision.revision_id


def test_tab_is_deterministic() -> None:
    revision = _revision()
    selected = _selection_for(revision)
    assert build_tab_projection(
        revision, instrument_profile_id=PROFILE, selected=selected
    ) == build_tab_projection(revision, instrument_profile_id=PROFILE, selected=selected)


def test_a_foreign_object_is_refused() -> None:
    with pytest.raises(ScoreContractError, match="CanonicalScoreRevisionV1"):
        build_tab_projection({"x": 1}, instrument_profile_id=PROFILE, selected={})  # type: ignore[arg-type]
