"""JSON Schema and Python validator agreement for lesson fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from master_all_strings.lesson.errors import LessonAssignmentError
from master_all_strings.lesson.serialization import deserialize_lesson_assignment
from master_all_strings.lesson.validation import validate_assignment

REPO_ROOT = Path(__file__).resolve().parents[2]
LESSON_EXAMPLES = REPO_ROOT / "resources" / "lesson" / "examples"
LESSON_SCHEMA = REPO_ROOT / "resources" / "lesson" / "schema" / "lesson_assignment_v1.schema.json"
GUITAR_PROFILE_PATH = (
    REPO_ROOT / "resources" / "instruments" / "examples" / "guitar-standard-6.json"
)


@pytest.fixture(scope="module")
def schema_validator() -> Draft202012Validator:
    schema = json.loads(LESSON_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.fixture(scope="module")
def profiles() -> dict:
    from master_all_strings.core.spatial_mapping.serialization import (
        instrument_profile_from_mapping,
    )

    guitar = instrument_profile_from_mapping(
        json.loads(GUITAR_PROFILE_PATH.read_text(encoding="utf-8"))
    )
    return {guitar.instrument_id: guitar}


def _valid_files() -> list[Path]:
    return sorted(
        p for p in LESSON_EXAMPLES.glob("*.json") if p.is_file() and p.parent.name != "invalid"
    )


def _invalid_files() -> list[Path]:
    return sorted((LESSON_EXAMPLES / "invalid").glob("*.json"))


@pytest.mark.parametrize("path", _valid_files(), ids=lambda p: p.name)
def test_valid_fixtures_pass_schema_and_python(
    path: Path,
    schema_validator: Draft202012Validator,
    profiles: dict,
) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    schema_validator.validate(data)
    assignment = deserialize_lesson_assignment(data)
    validate_assignment(assignment, instrument_profiles=profiles)


@pytest.mark.parametrize("path", _invalid_files(), ids=lambda p: p.name)
def test_invalid_fixtures_fail_with_named_reason(
    path: Path,
    schema_validator: Draft202012Validator,
    profiles: dict,
) -> None:
    if path.name == "EXPECTED_FAILURES.json":
        pytest.skip("catalog")
    expected = json.loads((LESSON_EXAMPLES / "invalid" / "EXPECTED_FAILURES.json").read_text())
    meta = expected["fixtures"][path.name]
    data = json.loads(path.read_text(encoding="utf-8"))

    schema_errors = sorted(schema_validator.iter_errors(data), key=lambda e: e.path)
    if meta["rejected_by"] == "schema":
        assert schema_errors, f"{path.name} should fail JSON Schema"
        return

    # Python-owned invariants may still be schema-valid.
    if schema_errors:
        # Some python cases also fail schema (e.g. empty events); that is fine.
        pass

    with pytest.raises(LessonAssignmentError) as excinfo:
        assignment = deserialize_lesson_assignment(data)
        validate_assignment(assignment, instrument_profiles=profiles)
    assert meta["code"] in str(excinfo.value) or meta["code"] == getattr(
        excinfo.value, "code", ""
    )


def test_expected_failures_catalog_complete() -> None:
    catalog = json.loads((LESSON_EXAMPLES / "invalid" / "EXPECTED_FAILURES.json").read_text())
    files = {p.name for p in (LESSON_EXAMPLES / "invalid").glob("*.json")} - {
        "EXPECTED_FAILURES.json"
    }
    assert set(catalog["fixtures"]) == files
