from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "tests" / "golden" / "msme_v1_vectors.json"

REQUIRED_TAGS = {
    "standard-guitar",
    "fretless-bass",
    "violin",
    "mandolin",
    "open-string",
    "multiple-playable-positions",
    "no-playable-position",
    "capo-behavior",
    "imaginary-semitone-location",
    "fractional-fretless-target",
    "ambiguity",
    "deterministic-tie-resolution",
    "previous-position-influence",
}


def test_golden_vectors_exist_and_cover_required_scenarios() -> None:
    vectors = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    assert len(vectors) >= 20
    observed_tags = {tag for vector in vectors for tag in vector["tags"]}
    assert REQUIRED_TAGS <= observed_tags
    assert {vector["instrument_id"] for vector in vectors} == {
        "guitar-standard-6",
        "bass-fretless-4",
        "violin-standard",
        "mandolin-standard",
    }
