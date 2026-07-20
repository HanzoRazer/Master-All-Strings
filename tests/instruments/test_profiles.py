from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from master_all_strings.core.spatial_mapping import FingerboardMode, instrument_profile_from_mapping
from master_all_strings.instruments import InstrumentProfile, StringProfile

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "resources" / "instruments" / "schema" / "instrument_profile.schema.json"
EXAMPLES_DIR = ROOT / "resources" / "instruments" / "examples"


def test_fretted_instruments_require_physical_fret_count() -> None:
    with pytest.raises(ValueError, match="physical_fret_count"):
        InstrumentProfile(
            schema_version="1.0.0",
            instrument_id="bad-guitar",
            display_name="Bad Guitar",
            family="guitar",
            fingerboard_mode=FingerboardMode.FRETTED,
            strings=(StringProfile("s1", "E2", 0, 40),),
            scale_length_mm=648.0,
            physical_fret_count=None,
        )


def test_example_profiles_validate_against_json_schema() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)

    for example_path in sorted(EXAMPLES_DIR.glob("*.json")):
        payload = json.loads(example_path.read_text(encoding="utf-8"))
        validator.validate(payload)
        profile = instrument_profile_from_mapping(payload)
        assert profile.instrument_id == payload["instrument_id"]
