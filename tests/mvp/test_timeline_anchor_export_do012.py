"""DO-012 timeline anchors in the static projection export.

Anchors ship beside the projection, never inside it. That placement is the
whole point of this suite: adding a field to FretboardScrollProjectionV1 would
move behavior_digest and break frozen DO-008 and DO-009 evidence for a
presentation concern that carries no musical content.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from master_all_strings.core.score.musical_timeline import ticks_to_seconds
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.mvp.application import MvpApplication
from master_all_strings.mvp.demo_library import load_demo_manifest
from master_all_strings.mvp.projection.serialization import (
    compute_projection_digest,
    deserialize_fretboard_projection,
)
from master_all_strings.mvp.web_export import projection_timeline_anchors
from master_all_strings.presentation.contracts import PRESENTATION_SCHEMA_VERSION
from master_all_strings.presentation.timeline import (
    TimelineAnchorV1,
    seconds_to_tick_from_anchors,
    tick_to_seconds_from_anchors,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECTIONS = REPO_ROOT / "web" / "mvp1" / "projections"


def _demo_ids() -> list[str]:
    return [entry.demo_id for entry in load_demo_manifest()]


def _payload(demo_id: str) -> dict:
    return json.loads((PROJECTIONS / f"{demo_id}.json").read_text(encoding="utf-8"))


def _anchors(payload: dict) -> tuple[TimelineAnchorV1, ...]:
    """The export shape is deliberately lean: {tick, seconds} and nothing else.

    Schema noise would be repeated on every anchor of every lesson for no
    reader's benefit, so the version is reattached here rather than shipped.
    """

    return tuple(
        TimelineAnchorV1(
            schema_version=PRESENTATION_SCHEMA_VERSION,
            tick=entry["tick"],
            seconds=entry["seconds"],
        )
        for entry in payload["timeline_anchors"]
    )


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_every_exported_projection_carries_anchors(demo_id: str) -> None:
    anchors = _payload(demo_id)["timeline_anchors"]
    assert anchors, f"{demo_id} exported no timeline anchors"
    assert anchors[0]["tick"] == 0, "the anchor table must begin at the origin"


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_anchors_are_strictly_increasing_and_monotonic(demo_id: str) -> None:
    anchors = _payload(demo_id)["timeline_anchors"]
    ticks = [a["tick"] for a in anchors]
    seconds = [a["seconds"] for a in anchors]
    assert ticks == sorted(set(ticks))
    assert seconds == sorted(seconds)


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_anchors_reproduce_musical_core_timing(demo_id: str) -> None:
    """Interpolating the exported table must equal Core's own conversion."""

    payload = _payload(demo_id)
    projection = deserialize_fretboard_projection(payload["projection"])
    tempo = tuple(
        TempoChangeV1(
            schema_version=TempoChangeV1.SCHEMA_VERSION,
            tick=change.tick,
            microseconds_per_quarter=change.microseconds_per_quarter,
        )
        for change in projection.tempo_changes
    )
    anchors = _anchors(payload)
    ppq = projection.timeline.ticks_per_quarter

    # Probe every note onset: those are the positions the playhead must resolve.
    for note in projection.notes:
        expected = ticks_to_seconds(note.onset_tick, ticks_per_quarter=ppq, tempo_changes=tempo)
        actual = tick_to_seconds_from_anchors(anchors, note.onset_tick)
        assert actual == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_note_onsets_round_trip_through_the_anchor_table(demo_id: str) -> None:
    payload = _payload(demo_id)
    projection = deserialize_fretboard_projection(payload["projection"])
    anchors = _anchors(payload)
    for note in projection.notes:
        assert seconds_to_tick_from_anchors(anchors, note.onset_seconds) == note.onset_tick


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_anchors_do_not_touch_the_projection_digest(demo_id: str) -> None:
    """The musical projection and its identity are unchanged by DO-012."""

    payload = _payload(demo_id)
    projection = deserialize_fretboard_projection(payload["projection"])
    assert compute_projection_digest(projection) == projection.projection_digest
    assert "timeline_anchors" not in payload["projection"]


def test_anchors_are_derived_not_stored_on_the_projection(app: MvpApplication) -> None:
    """Regenerating from the live application produces the same table."""

    entry = load_demo_manifest()[0]
    response = app.run_demo(entry.demo_id, instrument_profile_id=entry.instrument_profile_id)
    assert projection_timeline_anchors(response.projection) == _payload(entry.demo_id)[
        "timeline_anchors"
    ]


def test_the_golden_lesson_anchors_span_its_declared_duration() -> None:
    payload = _payload("half_steps_one_string")
    projection = deserialize_fretboard_projection(payload["projection"])
    anchors = payload["timeline_anchors"]
    assert anchors[-1]["tick"] == projection.timeline.total_ticks
    assert anchors[-1]["seconds"] == pytest.approx(projection.timeline.total_seconds, abs=1e-6)


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_exported_anchor_entries_carry_only_tick_and_seconds(demo_id: str) -> None:
    for entry in _payload(demo_id)["timeline_anchors"]:
        assert set(entry) == {"tick", "seconds"}


@pytest.mark.parametrize("demo_id", _demo_ids())
def test_the_anchor_table_declares_its_own_version(demo_id: str) -> None:
    """The leanest contract in the tranche still has to be identifiable.

    Anchor entries carry only ``tick`` and ``seconds`` so the version is not
    repeated on every row, but a payload that never states its version leaves the
    browser to infer the shape by convention. The version sits beside the table.
    """

    payload = _payload(demo_id)
    assert payload["timeline_anchors_schema_version"] == PRESENTATION_SCHEMA_VERSION


def test_the_export_is_byte_identical_across_platforms() -> None:
    """No CRLF from a Windows exporter: these files are digest-verified."""

    raw = (PROJECTIONS / "half_steps_one_string.json").read_bytes()
    assert b"\r\n" not in raw
