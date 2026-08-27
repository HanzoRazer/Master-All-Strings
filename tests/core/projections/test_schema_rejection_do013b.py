"""What the projection schemas refuse, and what only Python can refuse (DO-013B).

A schema that accepts everything is documentation, not a contract. The suite in
``test_schema_conformance_do013a.py`` proves the schemas accept valid artifacts;
this one proves they reject malformed ones, field by field, so the acceptance
result means something.

Two kinds of rejection are kept in different places on purpose.

Structural failures -- a missing required field, a wrong type, an unknown enum
value -- are expressed here as named mutations of a valid fixture. Each names the
one thing it breaks, which a directory of near-identical JSON files would bury.
The checked-in fixtures under ``examples/invalid`` are reserved for *semantic*
boundary violations that are worth reading as artifacts: a fingering on an
unresolved event, a rest claiming canonical identity, tie metadata under an
undeclared name.

The kind/payload correspondence is deliberately absent from the schemas, and the
last section proves that absence is a decision rather than an oversight: the
schema alone accepts a TAB envelope carrying a notation payload, and Python does
not.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from master_all_strings.core.projections.contracts import (
    PROJECTION_SCHEMA_VERSION,
    NotationProjectionV1,
    ProjectionKind,
    ProjectionResultV1,
)
from master_all_strings.core.projections.notation import build_notation_projection
from master_all_strings.core.score.errors import ScoreContractError

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "resources" / "projections" / "schema"
EXAMPLES = REPO_ROOT / "resources" / "projections" / "examples"
WEB_ROOT = REPO_ROOT / "web" / "mvp1" / "projections"

SCHEMA_NAMES = (
    "projection_request_v1",
    "projection_result_v1",
    "tab_projection_v1",
    "notation_projection_v1",
    "projection_unsupported_feature_v1",
)


def _schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    registry = Registry()
    for schema_name in SCHEMA_NAMES:
        schema = _schema(schema_name)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(_schema(name), registry=registry)


def _example(stem: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"{stem}.json").read_text(encoding="utf-8"))


# --- the rejection matrix ----------------------------------------------------
#
# (schema, fixture, description, mutation). Each mutation breaks exactly one
# thing, so a passing case names the rule that caught it.

Mutation = Callable[[dict[str, Any]], None]


def _drop(*path: str | int) -> Mutation:
    def mutate(payload: dict[str, Any]) -> None:
        target: Any = payload
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return mutate


def _set(*path: Any) -> Mutation:
    *keys, value = path

    def mutate(payload: dict[str, Any]) -> None:
        target: Any = payload
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value

    return mutate


REJECTIONS: tuple[tuple[str, str, str, Mutation], ...] = (
    # --- ProjectionRequestV1 -------------------------------------------------
    (
        "projection_request_v1",
        "projection_request_tab",
        "missing canonical revision id",
        _drop("canonical_revision_id"),
    ),
    (
        "projection_request_v1",
        "projection_request_tab",
        "missing request id",
        _drop("request_id"),
    ),
    (
        "projection_request_v1",
        "projection_request_tab",
        "options as an object instead of ordered pairs",
        _set("options", {"transpose": "0"}),
    ),
    (
        "projection_request_v1",
        "projection_request_tab",
        "an option pair of the wrong arity",
        _set("options", [["transpose"]]),
    ),
    (
        "projection_request_v1",
        "projection_request_tab",
        "an option value that is not a string",
        _set("options", [["transpose", 0]]),
    ),
    (
        "projection_request_v1",
        "projection_request_tab",
        "a schema version this contract never issued",
        _set("schema_version", "2.0.0"),
    ),
    (
        "projection_request_v1",
        "projection_request_tab",
        "an unknown projection kind",
        _set("projection_kind", "chord_chart"),
    ),
    # --- ProjectionResultV1 --------------------------------------------------
    (
        "projection_result_v1",
        "projection_result_tab",
        "missing digest",
        _drop("digest"),
    ),
    (
        "projection_result_v1",
        "projection_result_tab",
        "missing canonical revision id",
        _drop("canonical_revision_id"),
    ),
    (
        "projection_result_v1",
        "projection_result_tab",
        "a payload that is not an object",
        _set("payload", "tab"),
    ),
    (
        "projection_result_v1",
        "projection_result_tab",
        "a payload that is an array",
        _set("payload", []),
    ),
    (
        "projection_result_v1",
        "projection_result_tab",
        "an empty payload matching neither projection shape",
        _set("payload", {}),
    ),
    (
        "projection_result_v1",
        "projection_result_tab",
        "an unknown projection kind",
        _set("projection_kind", "chord_chart"),
    ),
    (
        "projection_result_v1",
        "projection_result_tab",
        "a digest that is not a sha256 citation",
        _set("digest", "sha256:short"),
    ),
    # --- TabProjectionV1 -----------------------------------------------------
    (
        "tab_projection_v1",
        "unresolved_tab",
        "a status outside the closed vocabulary",
        _set("events", 0, "status", "maybe"),
    ),
    (
        "tab_projection_v1",
        "unresolved_tab",
        "a fret expressed as a string",
        _set("events", 0, "fret", "5"),
    ),
    (
        "tab_projection_v1",
        "unresolved_tab",
        "a string id expressed as a number",
        _set("events", 0, "string_id", 6),
    ),
    (
        "tab_projection_v1",
        "unresolved_tab",
        "a negative fret",
        _set("events", 0, "fret", -1),
    ),
    (
        "tab_projection_v1",
        "unresolved_tab",
        "a midi note outside the representable range",
        _set("events", 0, "midi_note", 200),
    ),
    (
        "tab_projection_v1",
        "unresolved_tab",
        "an event with no canonical identity",
        _drop("events", 0, "canonical_event_id"),
    ),
    (
        "tab_projection_v1",
        "unresolved_tab",
        "a missing instrument profile",
        _drop("instrument_profile_id"),
    ),
    # --- NotationProjectionV1 ------------------------------------------------
    (
        "notation_projection_v1",
        "global_rest_notation",
        "an event kind outside the closed vocabulary",
        _set("measures", 0, "events", 0, "event_kind", "grace"),
    ),
    (
        "notation_projection_v1",
        "global_rest_notation",
        "a display policy that was never defined",
        _set("display_policy", "flat_preferred_v1"),
    ),
    (
        "notation_projection_v1",
        "global_rest_notation",
        "a note missing its display pitch",
        _drop("measures", 0, "events", 0, "display_pitch"),
    ),
    (
        "notation_projection_v1",
        "global_rest_notation",
        "a display duration outside the V1 grammar",
        _set("measures", 0, "events", 0, "display_duration", "sixty_fourth"),
    ),
    (
        "notation_projection_v1",
        "global_rest_notation",
        "a measure with no meter",
        _drop("measures", 0, "meter"),
    ),
    (
        "notation_projection_v1",
        "global_rest_notation",
        "a meter denominator that is not a note value",
        _set("measures", 0, "meter", "denominator", 5),
    ),
    (
        "notation_projection_v1",
        "global_rest_notation",
        "a rest derived by a rule that does not exist",
        _set("measures", 0, "events", 1, "derivation", "voice_inference"),
    ),
    (
        "notation_projection_v1",
        "global_rest_notation",
        "missing ticks per quarter",
        _drop("ticks_per_quarter"),
    ),
)


@pytest.mark.parametrize(
    ("schema_name", "fixture", "description", "mutation"),
    REJECTIONS,
    ids=[f"{schema}-{description}" for schema, _, description, _ in REJECTIONS],
)
def test_the_schema_rejects(
    schema_name: str, fixture: str, description: str, mutation: Mutation
) -> None:
    payload = _example(fixture)
    mutation(payload)
    assert not _validator(schema_name).is_valid(payload), (
        f"{schema_name} accepted {description}"
    )


def test_the_unmutated_fixtures_still_pass() -> None:
    """Without this, every rejection above could be passing for the wrong reason."""

    for schema_name, fixture, _, _ in REJECTIONS:
        _validator(schema_name).validate(_example(fixture))


def test_the_matrix_covers_every_externally_serialized_contract() -> None:
    covered = {schema for schema, _, _, _ in REJECTIONS}
    assert covered == {
        "projection_request_v1",
        "projection_result_v1",
        "tab_projection_v1",
        "notation_projection_v1",
    }


# --- real product output, not only constructed input -------------------------

UNPLAYABLE_EXPORT = WEB_ROOT / "unplayable_note" / "tab.json"


def _unplayable_export() -> dict[str, Any]:
    return json.loads(UNPLAYABLE_EXPORT.read_text(encoding="utf-8"))


def test_the_real_unplayable_lesson_validates_as_an_envelope() -> None:
    """The schemas must accept what the product actually ships, not only fixtures."""

    _validator("projection_result_v1").validate(_unplayable_export())


def test_the_real_unplayable_payload_validates_as_tab() -> None:
    _validator("tab_projection_v1").validate(_unplayable_export()["payload"])


def test_the_real_corpus_supplies_the_unplayable_witness() -> None:
    """UNPLAYABLE needed no synthetic case: a bundled lesson already produces one."""

    events = _unplayable_export()["payload"]["events"]
    unplayable = [event for event in events if event["status"] == "unplayable"]
    assert len(unplayable) == 1
    assert unplayable[0]["canonical_event_id"] == "ev-2"


def test_the_real_unplayable_event_carries_no_fingering() -> None:
    """Schema-enforced, and confirmed here against genuine product output."""

    event = next(
        item
        for item in _unplayable_export()["payload"]["events"]
        if item["status"] == "unplayable"
    )
    assert event["string_id"] is None
    assert event["fret"] is None


def test_the_real_export_still_carries_playable_neighbours() -> None:
    """One unplayable note must not degrade the events around it."""

    events = _unplayable_export()["payload"]["events"]
    playable = [item for item in events if item["status"] == "playable"]
    assert len(playable) == 2
    assert all(item["string_id"] and item["fret"] is not None for item in playable)


def test_a_fingering_added_to_the_real_unplayable_event_is_refused() -> None:
    """The corpus witness, mutated: the invariant holds on real data too."""

    export = _unplayable_export()
    event = next(
        item for item in export["payload"]["events"] if item["status"] == "unplayable"
    )
    event["string_id"] = "string-1"
    event["fret"] = 0
    assert not _validator("tab_projection_v1").is_valid(export["payload"])


# --- what the schema cannot say, and Python must ------------------------------


def _mismatched_envelope() -> dict[str, Any]:
    """A TAB envelope carrying a notation payload."""

    envelope = copy.deepcopy(_example("projection_result_tab"))
    notation = _example("projection_result_notation")
    envelope["payload"] = notation["payload"]
    envelope["canonical_revision_id"] = notation["canonical_revision_id"]
    envelope["payload"]["canonical_revision_id"] = notation["canonical_revision_id"]
    return envelope


def test_the_schema_alone_accepts_a_mismatched_envelope() -> None:
    """Why the kind/payload rule is not in the schema (D3).

    ``payload`` is a oneOf, so a notation payload under ``projection_kind: tab``
    satisfies it: one branch matched. Expressing the correspondence in JSON Schema
    is possible but reports every unmatched branch instead of the single violation
    that occurred, which is worse evidence than none. This test records that the
    gap is deliberate -- if it ever starts failing, the schema gained the rule and
    the Python guard below may be redundant rather than load-bearing.
    """

    assert _validator("projection_result_v1").is_valid(_mismatched_envelope())


def test_python_refuses_the_mismatch_the_schema_allows() -> None:
    """The invariant itself, enforced where it can be reported precisely.

    The error names the expected payload type, which is the diagnostic a oneOf
    cannot produce.
    """

    notation_payload = _build_notation_payload()
    with pytest.raises(ScoreContractError, match="requires a TabProjectionV1"):
        ProjectionResultV1(
            schema_version=PROJECTION_SCHEMA_VERSION,
            projection_id="p1",
            canonical_revision_id=notation_payload.canonical_revision_id,
            projection_kind=ProjectionKind.TAB,
            payload=notation_payload,
            digest="sha256:" + "0" * 64,
        )


def test_the_same_payload_is_accepted_under_its_own_kind() -> None:
    """So the refusal above is about the pairing, not about the payload."""

    notation_payload = _build_notation_payload()
    result = ProjectionResultV1(
        schema_version=PROJECTION_SCHEMA_VERSION,
        projection_id="p1",
        canonical_revision_id=notation_payload.canonical_revision_id,
        projection_kind=ProjectionKind.NOTATION,
        payload=notation_payload,
        digest="sha256:" + "0" * 64,
    )
    assert result.projection_kind is ProjectionKind.NOTATION


def _build_notation_payload() -> NotationProjectionV1:
    """A real notation payload, built through the production builder."""

    import importlib.util
    import sys

    name = "build_projection_fixtures"
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / "build_projection_fixtures.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

    payload = build_notation_projection(
        module.build_synthetic_revision(module.GLOBAL_REST_NOTATION)
    )
    assert isinstance(payload, NotationProjectionV1)
    return payload
