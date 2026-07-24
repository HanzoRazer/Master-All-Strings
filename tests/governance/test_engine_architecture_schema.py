"""The registry must validate against its JSON Schema; malformed copies must fail."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from master_all_strings.governance import engine_boundaries as eb

SCHEMA = json.loads(eb.SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def registry() -> dict[str, Any]:
    return eb.load_registry()


def test_committed_registry_validates(registry: dict[str, Any]) -> None:
    jsonschema.validate(registry, SCHEMA)


def test_registry_and_schema_files_exist() -> None:
    assert eb.REGISTRY_PATH.exists()
    assert eb.SCHEMA_PATH.exists()
    assert eb.REGISTRY_PATH == Path(eb._REPO_ROOT) / "governance" / "engine_architecture_v1.json"


def test_unknown_engine_id_fails_schema(registry: dict[str, Any]) -> None:
    registry["capabilities"][0]["owning_engine"] = "GHOST_ENGINE"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(registry, SCHEMA)


def test_extra_top_level_key_fails_schema(registry: dict[str, Any]) -> None:
    registry["surprise"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(registry, SCHEMA)


def test_five_engines_fails_schema(registry: dict[str, Any]) -> None:
    registry["engines"].append(copy.deepcopy(registry["engines"][0]))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(registry, SCHEMA)


def test_bad_relation_enum_fails_schema(registry: dict[str, Any]) -> None:
    registry["dependency_rules"][0]["relation"] = "sometimes"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(registry, SCHEMA)


def test_bad_adr_pattern_fails_schema(registry: dict[str, Any]) -> None:
    registry["adr_assignments"][0]["adr"] = "ADR-5"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(registry, SCHEMA)
