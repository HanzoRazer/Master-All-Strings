"""Golden-vector runner for the Musical Spatial Mapping Engine.

Generation and selection assertions are kept visibly separate. Generation
expectations execute now; selection expectations are explicitly reserved until
DO-004 and are asserted as reserved rather than skipped, so a vector cannot quietly
stop being checked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.spatial_mapping import (
    MappingConstraints,
    generate_candidates,
    instrument_profile_from_mapping,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "tests" / "golden" / "msme_v1_vectors.json"
SCHEMA_PATH = ROOT / "tests" / "golden" / "msme_v1_vectors.schema.json"
EXAMPLES = ROOT / "resources" / "instruments" / "examples"

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

VECTORS: list[dict[str, Any]] = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
SCHEMA: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
_VECTOR_IDS = [vector["vector_id"] for vector in VECTORS]


def _profile(instrument_id: str) -> Any:
    return instrument_profile_from_mapping(
        json.loads((EXAMPLES / f"{instrument_id}.json").read_text(encoding="utf-8"))
    )


def _run_generation(vector: dict[str, Any]) -> list[dict[str, Any]]:
    inputs = vector["inputs"]
    event = MusicalEvent(
        event_id=vector["vector_id"],
        midi_note=inputs["event"]["midi_note"],
        start_tick=0,
        duration_ticks=480,
        cents_offset=inputs["event"].get("cents_offset", 0.0),
    )
    constraints = MappingConstraints(**inputs.get("constraints", {}))
    produced = generate_candidates(event, _profile(vector["instrument_id"]), constraints)
    return [
        {
            "string_id": c.string_id,
            "course_id": c.course_id,
            "display_order": c.display_order,
            "sounding_midi_note": c.sounding_midi_note,
            "cents_offset": c.cents_offset,
            "relative_semitone_position": c.relative_semitone_position,
            "physical_semitone_position_from_nut": c.physical_semitone_position_from_nut,
            "physical_fret_number": c.physical_fret_number,
            "reference_type": c.reference_type.value,
            "normalized_position": round(c.normalized_position, 12),
            "distance_from_nut_mm": (
                None if c.distance_from_nut_mm is None else round(c.distance_from_nut_mm, 12)
            ),
            "is_open_string": c.is_open_string,
        }
        for c in produced
    ]


class TestVectorFileIntegrity:
    def test_vectors_validate_against_the_schema(self) -> None:
        jsonschema.validate(VECTORS, SCHEMA)

    def test_required_scenario_tags_are_covered(self) -> None:
        observed = {tag for vector in VECTORS for tag in vector["tags"]}
        assert REQUIRED_TAGS <= observed

    def test_all_four_reference_instruments_are_represented(self) -> None:
        assert {vector["instrument_id"] for vector in VECTORS} == {
            "guitar-standard-6",
            "bass-fretless-4",
            "violin-standard",
            "mandolin-standard",
        }

    def test_vector_ids_are_unique(self) -> None:
        assert len(_VECTOR_IDS) == len(set(_VECTOR_IDS))

    def test_a_malformed_selection_expectation_fails_validation(self) -> None:
        """Neither reserved nor resolved: the schema must reject it outright."""
        broken = json.loads(json.dumps(VECTORS))
        broken[0]["expected"]["selection"] = {"status": "maybe"}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(broken, SCHEMA)

    def test_a_missing_generation_expectation_fails_validation(self) -> None:
        broken = json.loads(json.dumps(VECTORS))
        del broken[0]["expected"]["generation"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(broken, SCHEMA)

    def test_a_reserved_selection_must_carry_a_reason(self) -> None:
        broken = json.loads(json.dumps(VECTORS))
        broken[0]["expected"]["selection"] = {"status": "reserved"}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(broken, SCHEMA)


class TestGenerationPhase:
    """Executable now: DO-003 owns these expectations."""

    @pytest.mark.parametrize("vector", VECTORS, ids=_VECTOR_IDS)
    def test_generated_candidates_match_expectations(self, vector: dict[str, Any]) -> None:
        assert _run_generation(vector) == vector["expected"]["generation"]["candidates"]

    @pytest.mark.parametrize("vector", VECTORS, ids=_VECTOR_IDS)
    def test_generation_is_reproducible(self, vector: dict[str, Any]) -> None:
        assert _run_generation(vector) == _run_generation(vector)

    def test_at_least_one_vector_expects_no_playable_position(self) -> None:
        empty = [v for v in VECTORS if not v["expected"]["generation"]["candidates"]]
        assert empty, "the unplayable case must stay covered"
        for vector in empty:
            assert "no-playable-position" in vector["tags"]

    def test_no_playable_position_tag_always_means_zero_candidates(self) -> None:
        """Guards against a vector whose premise drifts out of step with its profile."""
        for vector in VECTORS:
            if "no-playable-position" in vector["tags"]:
                assert vector["expected"]["generation"]["candidates"] == [], vector["vector_id"]

    def test_ambiguity_vectors_really_are_ambiguous(self) -> None:
        for vector in VECTORS:
            if "multiple-playable-positions" in vector["tags"]:
                count = len(vector["expected"]["generation"]["candidates"])
                assert count > 1, vector["vector_id"]


class TestSelectionPhase:
    """Deferred to DO-004, but asserted as deferred rather than skipped."""

    @pytest.mark.parametrize("vector", VECTORS, ids=_VECTOR_IDS)
    def test_selection_expectation_is_explicitly_reserved(
        self, vector: dict[str, Any]
    ) -> None:
        selection = vector["expected"]["selection"]
        assert selection["status"] == "reserved"
        assert selection["reason"]

    def test_previous_position_vectors_state_the_contract_gap(self) -> None:
        for vector in VECTORS:
            if "previous-position-influence" in vector["tags"]:
                reason = vector["expected"]["selection"]["reason"]
                assert "continuity" in reason or "previous-position" in reason

    def test_tie_resolution_vectors_are_reserved_not_absent(self) -> None:
        tagged = [v for v in VECTORS if "deterministic-tie-resolution" in v["tags"]]
        assert tagged, "the tie-resolution scenario must remain in the file for DO-004"
        for vector in tagged:
            assert vector["expected"]["selection"]["status"] == "reserved"
