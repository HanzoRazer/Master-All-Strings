"""The Python half of the cross-language interpolation contract.

`resources/presentation/examples/interpolation_vectors.json` is read by both
this suite and `web/mvp1/tests/teaching_timeline.test.js`. Python proves the
vectors still describe Musical Core's mapping; Node proves the browser
reproduces them. Neither side can drift without one of them failing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from master_all_strings.core.score.musical_timeline import ticks_to_seconds
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.presentation.serialization import from_dict
from master_all_strings.presentation.timeline import (
    TimelineAnchorV1,
    seconds_at_tick,
    tick_at_seconds,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS = REPO_ROOT / "resources" / "presentation" / "examples" / "interpolation_vectors.json"


def _load() -> dict[str, Any]:
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def _cases() -> list[dict[str, Any]]:
    return _load()["cases"]


def _anchors(case: dict[str, Any]) -> tuple[TimelineAnchorV1, ...]:
    return tuple(from_dict(TimelineAnchorV1, entry) for entry in case["anchors"])


def test_vector_file_is_present_and_populated() -> None:
    data = _load()
    assert data["schema_version"] == "1.0.0"
    assert len(data["cases"]) >= 3


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["case_id"])
def test_seconds_at_tick_matches_the_recorded_vector(case: dict[str, Any]) -> None:
    anchors = _anchors(case)
    for probe in case["seconds_at_tick"]:
        assert seconds_at_tick(anchors, probe["tick"]) == pytest.approx(
            probe["seconds"], abs=1e-9
        )


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["case_id"])
def test_tick_at_seconds_matches_the_recorded_vector(case: dict[str, Any]) -> None:
    anchors = _anchors(case)
    for probe in case["tick_at_seconds"]:
        assert tick_at_seconds(anchors, probe["seconds"]) == probe["tick"]


def test_recorded_anchors_still_agree_with_musical_core() -> None:
    """The vectors are only meaningful while they match Core's own conversion."""

    case = next(c for c in _cases() if c["case_id"] == "tempo_change_120_to_90")
    tempo = (
        TempoChangeV1(schema_version="1.0.0", tick=0, microseconds_per_quarter=500_000),
        TempoChangeV1(schema_version="1.0.0", tick=1920, microseconds_per_quarter=666_667),
    )
    for entry in case["anchors"]:
        expected = ticks_to_seconds(
            entry["tick"], ticks_per_quarter=960, tempo_changes=tempo
        )
        assert entry["seconds"] == pytest.approx(expected, abs=1e-9)


def test_every_case_probes_both_directions() -> None:
    for case in _cases():
        assert case["seconds_at_tick"], f"{case['case_id']} has no tick probes"
        assert case["tick_at_seconds"], f"{case['case_id']} has no seconds probes"
