"""The Python half of the cross-language interpolation contract.

`resources/presentation/examples/interpolation_vectors.json` is read by both
this suite and `web/mvp1/tests/teaching_timeline.test.js`. Python proves the
vectors still describe Musical Core's mapping; Node proves the browser
reproduces them. Neither side can drift without one of them failing.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from master_all_strings.core.score.musical_timeline import ticks_to_seconds
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.presentation.serialization import from_dict
from master_all_strings.presentation.timeline import (
    TimelineAnchorV1,
    seconds_to_tick_from_anchors,
    tick_to_seconds_from_anchors,
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
def test_tick_to_seconds_from_anchors_matches_the_recorded_vector(case: dict[str, Any]) -> None:
    anchors = _anchors(case)
    for probe in case["tick_to_seconds_from_anchors"]:
        assert tick_to_seconds_from_anchors(anchors, probe["tick"]) == pytest.approx(
            probe["seconds"], abs=1e-9
        )


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["case_id"])
def test_seconds_to_tick_from_anchors_matches_the_recorded_vector(case: dict[str, Any]) -> None:
    anchors = _anchors(case)
    for probe in case["seconds_to_tick_from_anchors"]:
        assert seconds_to_tick_from_anchors(anchors, probe["seconds"]) == probe["tick"]


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
        assert case["tick_to_seconds_from_anchors"], f"{case['case_id']} has no tick probes"
        assert case["seconds_to_tick_from_anchors"], f"{case['case_id']} has no seconds probes"


def test_the_golden_case_matches_the_lesson_it_names() -> None:
    """The golden vector must describe the golden lesson's real tick domain.

    Regression guard. The case was once a relabeled copy of ``constant_120bpm``
    (960 PPQ, 8640 ticks) while the lesson it claimed to describe exports 480
    PPQ and 2880 ticks. Every probe still passed, because the case was internally
    consistent -- it simply exercised a tick domain the browser never sees. A
    named case has to be checkable against the thing it names.
    """

    projection_payload = json.loads(
        (REPO_ROOT / "web" / "mvp1" / "projections" / "half_steps_one_string.json").read_text(
            encoding="utf-8"
        )
    )
    case = next(c for c in _cases() if c["case_id"] == "half_steps_one_string")

    exported = [
        {"tick": entry["tick"], "seconds": entry["seconds"]}
        for entry in projection_payload["timeline_anchors"]
    ]
    recorded = [
        {"tick": entry["tick"], "seconds": entry["seconds"]} for entry in case["anchors"]
    ]
    assert recorded == exported, (
        "the golden vector's anchors must be the anchors the browser is actually shipped"
    )


def test_every_case_declares_the_tick_domain_it_probes() -> None:
    """Two cases that differ only in PPQ are indistinguishable without this."""

    for case in _cases():
        assert isinstance(case["ticks_per_quarter"], int)
        assert case["ticks_per_quarter"] > 0
        assert case["total_ticks"] == case["anchors"][-1]["tick"]


def test_the_vector_file_is_regenerable_and_current() -> None:
    """The file claims to be generated; prove the generator still produces it.

    Loaded by path rather than imported as ``scripts.build_interpolation_vectors``:
    ``scripts/`` is not a package and is only importable when the repository root
    happens to be on ``sys.path``, which is true under ``python -m pytest`` and
    false under the bare ``pytest`` that CI runs.
    """

    spec = importlib.util.spec_from_file_location(
        "build_interpolation_vectors",
        REPO_ROOT / "scripts" / "build_interpolation_vectors.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.build() == _load()


# --- negative regression: semantic mislabeling -------------------------------


def _generator():
    """Load the vector generator as a module."""

    spec = importlib.util.spec_from_file_location(
        "build_interpolation_vectors",
        REPO_ROOT / "scripts" / "build_interpolation_vectors.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_generator_reports_the_current_vectors_as_current() -> None:
    """The detector must accept the good file, or its rejections mean nothing."""

    assert _generator().main(["--check"]) == 0


def test_a_mislabeled_golden_case_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A case labelled half_steps_one_string carrying a foreign tick domain fails.

    This reproduces the defect the generator was written to end: the golden case
    was a relabelled copy of ``constant_120bpm`` at 960 PPQ / 8640 ticks while the
    lesson it named exports 480 PPQ / 2880 ticks. Every probe passed, because the
    case was internally consistent -- it simply described a tick domain the
    browser never sees.

    Internal consistency is exactly why this needs a negative test. Asserting only
    that today's good file matches would pass just as happily against the broken
    one.
    """

    generator = _generator()
    payload = json.loads(json.dumps(generator.build()))

    golden = next(c for c in payload["cases"] if c["case_id"] == "half_steps_one_string")
    foreign = next(c for c in payload["cases"] if c["case_id"] == "constant_120bpm")
    assert golden["ticks_per_quarter"] != foreign["ticks_per_quarter"], (
        "the two cases must differ, or this test proves nothing"
    )

    # Keep the golden label; take the foreign timing domain wholesale. The result
    # is self-consistent and wrong -- the original defect exactly.
    for key in ("ticks_per_quarter", "total_ticks", "anchors"):
        golden[key] = foreign[key]
    golden["tick_to_seconds_from_anchors"] = foreign["tick_to_seconds_from_anchors"]
    golden["seconds_to_tick_from_anchors"] = foreign["seconds_to_tick_from_anchors"]

    tampered = tmp_path / "interpolation_vectors.json"
    tampered.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(generator, "VECTORS", tampered)

    assert generator.main(["--check"]) == 1
    assert "stale" in capsys.readouterr().err


def test_the_tampered_case_would_still_satisfy_its_own_probes(tmp_path: Path) -> None:
    """Shows why label-checking is needed: the bad case is internally valid.

    Every probe in the foreign domain interpolates correctly against the foreign
    anchors. Nothing inside the case is wrong; only its name is.
    """

    generator = _generator()
    payload = generator.build()
    foreign = next(c for c in payload["cases"] if c["case_id"] == "constant_120bpm")
    anchors = tuple(
        TimelineAnchorV1(
            schema_version=entry["schema_version"],
            tick=entry["tick"],
            seconds=entry["seconds"],
        )
        for entry in foreign["anchors"]
    )
    for probe in foreign["tick_to_seconds_from_anchors"]:
        assert tick_to_seconds_from_anchors(anchors, probe["tick"]) == pytest.approx(
            probe["seconds"], abs=1e-9
        )
