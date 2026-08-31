"""Meter must survive lesson resolution (DO-013).

The assignment declared meter and resolution dropped it. Nothing downstream
noticed, because nothing downstream needed measures until notation did — at
which point the tempting fix is to let notation reach past ``ResolvedLessonV1``
into the raw assignment while every other consumer reads the resolved contract.
That would leave two different answers to "what is this lesson", so the meter is
carried through instead.

These tests also pin the part that matters more than the feature: adding a field
must not disturb the events, playback, or spatial output that already existed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.lesson.models import LessonAssignmentV1
from master_all_strings.lesson.resolver import resolve_lesson_assignment
from master_all_strings.mvp.demo_library import load_demo_assignment, load_demo_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _assignment(demo_id: str) -> LessonAssignmentV1:
    # The repository's own loader, so this test cannot drift from how the demo
    # corpus is actually addressed.
    return load_demo_assignment(demo_id)


def _demo_ids() -> list[str]:
    return [entry.demo_id for entry in load_demo_manifest()]


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_declared_meter_reaches_the_resolved_lesson(demo_id: str) -> None:
    assignment = _assignment(demo_id)
    resolved = resolve_lesson_assignment(assignment)
    declared = assignment.musical_content.meter_changes
    assert len(resolved.meter_changes) == len({c.tick for c in declared})
    for change in resolved.meter_changes:
        assert isinstance(change, MeterChangeV1)


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_meter_values_are_carried_not_reinterpreted(demo_id: str) -> None:
    assignment = _assignment(demo_id)
    resolved = resolve_lesson_assignment(assignment)
    declared = {
        c.tick: (c.numerator, c.denominator)
        for c in assignment.musical_content.meter_changes
    }
    carried = {c.tick: (c.numerator, c.denominator) for c in resolved.meter_changes}
    assert carried == declared


def test_meter_changes_are_sorted_by_tick() -> None:
    resolved = resolve_lesson_assignment(_assignment("half_steps_one_string"))
    ticks = [c.tick for c in resolved.meter_changes]
    assert ticks == sorted(ticks)


def test_a_lesson_without_declared_meter_resolves_to_an_empty_map() -> None:
    """Absent is absent. Defaulting here would hide the omission from the caller."""

    for demo_id in _demo_ids():
        assignment = _assignment(demo_id)
        resolved = resolve_lesson_assignment(assignment)
        if not assignment.musical_content.meter_changes:
            assert resolved.meter_changes == ()
            return
    pytest.skip("every bundled lesson declares a meter")


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_adding_meter_left_the_rest_of_resolution_untouched(demo_id: str) -> None:
    """The additive claim, checked field by field rather than asserted."""

    resolved = resolve_lesson_assignment(_assignment(demo_id))
    assert resolved.events, "resolution must still produce events"
    assert resolved.playback.ticks_per_quarter > 0
    assert resolved.spatial.instrument_profile_id
    # Events carry no meter and must not have acquired any.
    for event in resolved.events:
        assert not hasattr(event, "meter")


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_exported_musical_output_is_unchanged(demo_id: str) -> None:
    """The checked-in projections are the real regression surface.

    If meter preservation had perturbed event generation, these digests would
    move -- which is exactly the failure the additive claim is about.
    """

    payload = json.loads(
        (REPO_ROOT / "web" / "mvp1" / "projections" / f"{demo_id}.json").read_text(
            encoding="utf-8"
        )
    )
    resolved = resolve_lesson_assignment(_assignment(demo_id))
    exported_onsets = [note["onset_tick"] for note in payload["projection"]["notes"]]
    resolved_onsets = [event.start_tick for event in resolved.events]
    # Unplayable notes still appear in the projection, so the exported set is the
    # full canonical set in canonical order.
    assert sorted(resolved_onsets) == sorted(exported_onsets)


def test_duplicate_meter_declarations_at_one_tick_resolve_to_one() -> None:
    """Two meters at the same tick is a contradiction, not a pair to keep."""

    from master_all_strings.lesson.resolver import _resolve_meter_changes

    assignment = _assignment("half_steps_one_string")
    doubled = assignment.musical_content.meter_changes
    if not doubled:
        pytest.skip("lesson declares no meter to duplicate")
    resolved = _resolve_meter_changes(assignment)
    assert len({c.tick for c in resolved}) == len(resolved)
