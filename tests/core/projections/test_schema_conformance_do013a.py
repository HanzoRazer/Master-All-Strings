"""JSON Schema and Python contract agreement for DO-013 projections.

These artifacts cross the Core -> browser boundary as serialized JSON, so the
dataclass alone is not the contract a consumer sees. The schema is the second,
independent description, and two descriptions of one contract only earn their
keep if they agree: every valid fixture must satisfy both, and every malformed
fixture must be refused by at least one.

The negative fixtures are not generic corruption. Each models a specific way the
projection boundary could fail -- TAB inventing a fingering, a derived rest
claiming canonical identity, a tie appearing where no tie evidence exists -- so a
schema that stopped catching one of them fails here rather than passing quietly.

Cross-file ``$ref`` resolution uses a registry built from the four schemas in
this directory. That is local test wiring, not a discovery framework: the files
are listed, not searched for.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from master_all_strings.core.projections.contracts import (
    NotationProjectionV1,
    ProjectionRequestV1,
    ProjectionResultV1,
    TabProjectionV1,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "resources" / "projections" / "schema"
EXAMPLES = REPO_ROOT / "resources" / "projections" / "examples"
INVALID = EXAMPLES / "invalid"

SCHEMA_NAMES = (
    "projection_request_v1",
    "projection_result_v1",
    "tab_projection_v1",
    "notation_projection_v1",
    "projection_unsupported_feature_v1",
)

# Fixture stem prefix -> schema file. Longest-prefix wins, so the envelope names
# are matched before the payload suffixes they happen to end with.
_ROUTES: tuple[tuple[str, str], ...] = (
    ("projection_request_", "projection_request_v1"),
    ("projection_result_", "projection_result_v1"),
    ("request_", "projection_request_v1"),
    ("result_", "projection_result_v1"),
    ("tab_", "tab_projection_v1"),
    ("notation_", "notation_projection_v1"),
)

# Which contract class owns each schema, for the "both descriptions agree" check.
_CONTRACTS: dict[str, type] = {
    "projection_request_v1": ProjectionRequestV1,
    "projection_result_v1": ProjectionResultV1,
    "tab_projection_v1": TabProjectionV1,
    "notation_projection_v1": NotationProjectionV1,
}


def _schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def _registry() -> Registry:
    """Resolve the projection schemas' cross-references by their declared $id."""

    registry = Registry()
    for name in SCHEMA_NAMES:
        schema = _schema(name)
        registry = registry.with_resource(
            schema["$id"], Resource.from_contents(schema)
        )
    return registry


def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(_schema(name), registry=_registry())


def _route(path: Path) -> str:
    for prefix, schema_name in _ROUTES:
        if path.stem.startswith(prefix):
            return schema_name
    # Payload fixtures are named for what they prove, so fall back on the kind
    # their name ends with.
    if path.stem.endswith("_tab"):
        return "tab_projection_v1"
    if path.stem.endswith("_notation"):
        return "notation_projection_v1"
    raise AssertionError(f"no schema route for fixture {path.name}")


def _valid_fixtures() -> list[Path]:
    return sorted(EXAMPLES.glob("*.json"))


def _invalid_fixtures() -> list[Path]:
    return sorted(INVALID.glob("*.json"))


# --- the schemas themselves --------------------------------------------------


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_every_schema_is_itself_valid(name: str) -> None:
    Draft202012Validator.check_schema(_schema(name))


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_every_schema_declares_a_stable_id(name: str) -> None:
    """Cross-file references resolve by $id, so an absent one breaks silently."""

    schema = _schema(name)
    assert schema["$id"].startswith("https://master-all-strings.dev/schema/projections/")
    assert schema["$id"].endswith(".schema.json")


def test_every_required_schema_exists() -> None:
    """The ruling names four externally serialized contracts; none may be missing."""

    required = {
        "projection_request_v1",
        "projection_result_v1",
        "tab_projection_v1",
        "notation_projection_v1",
    }
    present = {path.name.replace(".schema.json", "") for path in SCHEMA_DIR.glob("*.schema.json")}
    assert required <= present


def test_no_duplicate_canonical_revision_schema_was_created() -> None:
    """The revision belongs to Core's score domain, not to a projection-local copy."""

    stems = {path.name for path in SCHEMA_DIR.glob("*.schema.json")}
    assert not any("canonical" in stem or "revision" in stem for stem in stems)


# --- valid fixtures satisfy both descriptions --------------------------------


def test_the_fixture_set_is_not_empty() -> None:
    assert _valid_fixtures()
    assert _invalid_fixtures()


@pytest.mark.parametrize("path", _valid_fixtures(), ids=lambda p: p.stem)
def test_valid_fixture_passes_its_schema(path: Path) -> None:
    _validator(_route(path)).validate(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("path", _valid_fixtures(), ids=lambda p: p.stem)
def test_fixture_schema_and_dataclass_agree_on_the_field_set(path: Path) -> None:
    """The drift this catches: a dataclass field added without the schema.

    Serializing through ``projection_to_dict`` emits every declared field, so a
    new one shows up in a regenerated fixture immediately. If the schema were not
    updated too, ``additionalProperties: false`` would reject the fixture -- but
    only if something compares the two, which is this. The reverse case, a schema
    property no dataclass field backs, is caught by the same comparison.
    """

    import dataclasses

    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_name = _route(path)
    contract = _CONTRACTS[schema_name]

    declared = {field.name for field in dataclasses.fields(contract)}
    assert set(payload) <= declared, f"{path.name} carries keys the contract lacks"

    schema_properties = set(_schema(schema_name)["properties"])
    assert schema_properties == declared, (
        f"{schema_name} and {contract.__name__} disagree on the field set"
    )

    required = {
        field.name
        for field in dataclasses.fields(contract)
        if field.default is dataclasses.MISSING
        and field.default_factory is dataclasses.MISSING  # type: ignore[misc]
    }
    assert required <= set(payload), f"{path.name} omits a field with no default"


# --- malformed fixtures are refused ------------------------------------------


@pytest.mark.parametrize("path", _invalid_fixtures(), ids=lambda p: p.stem)
def test_invalid_fixture_is_refused_by_its_schema(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert not _validator(_route(path)).is_valid(payload)


def test_a_fingering_on_an_unresolved_event_is_refused() -> None:
    """The invariant TAB exists to protect: no fret nobody selected."""

    payload = json.loads(
        (INVALID / "tab_unresolved_with_fingering.json").read_text(encoding="utf-8")
    )
    errors = list(_validator("tab_projection_v1").iter_errors(payload))
    assert errors


def test_a_rest_claiming_canonical_identity_is_refused() -> None:
    """A derived rest corresponds to no canonical event, so it may not name one."""

    payload = json.loads(
        (INVALID / "notation_rest_claiming_canonical_identity.json").read_text(
            encoding="utf-8"
        )
    )
    assert not _validator("notation_projection_v1").is_valid(payload)


def test_tie_metadata_is_refused_under_any_field_name() -> None:
    """additionalProperties is false precisely so an invented tie cannot slip in."""

    payload = json.loads(
        (INVALID / "notation_inferred_tie_metadata.json").read_text(encoding="utf-8")
    )
    assert not _validator("notation_projection_v1").is_valid(payload)


def test_an_unknown_projection_kind_is_refused() -> None:
    payload = json.loads(
        (INVALID / "request_unknown_projection_kind.json").read_text(encoding="utf-8")
    )
    assert not _validator("projection_request_v1").is_valid(payload)


def test_a_malformed_digest_is_refused() -> None:
    """A digest that is not a sha256 citation cannot be checked by anyone."""

    payload = json.loads(
        (INVALID / "result_malformed_digest.json").read_text(encoding="utf-8")
    )
    assert not _validator("projection_result_v1").is_valid(payload)


# --- the schemas describe the committed contracts ----------------------------


def test_tab_status_vocabulary_matches_the_contract() -> None:
    from master_all_strings.core.projections.contracts import TabEventStatus

    schema = _schema("tab_projection_v1")
    declared = schema["$defs"]["tabEvent"]["properties"]["status"]["enum"]
    assert set(declared) == {member.value for member in TabEventStatus}


def test_notation_display_durations_match_the_contract() -> None:
    from master_all_strings.core.projections.contracts import DisplayDuration

    schema = _schema("notation_projection_v1")
    declared = schema["$defs"]["event"]["properties"]["display_duration"]["enum"]
    assert set(declared) == {member.value for member in DisplayDuration} | {None}


def test_unsupported_feature_codes_match_the_contract() -> None:
    from master_all_strings.core.projections.contracts import UnsupportedFeatureCode

    declared = _schema("projection_unsupported_feature_v1")["properties"]["code"]["enum"]
    assert set(declared) == {member.value for member in UnsupportedFeatureCode}


def test_rest_derivations_match_the_contract() -> None:
    from master_all_strings.core.projections.contracts import RestDerivation

    schema = _schema("notation_projection_v1")
    declared = schema["$defs"]["event"]["properties"]["derivation"]["enum"]
    assert set(declared) == {member.value for member in RestDerivation} | {None}


def test_notation_carries_no_instrument_profile() -> None:
    """Fingering independence, asserted at the contract's surface."""

    properties = _schema("notation_projection_v1")["properties"]
    assert "instrument_profile_id" not in properties
