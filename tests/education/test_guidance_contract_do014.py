"""DO-014 Commit 1: TeachingGuidanceProjectionV1 contract, schema, serialization."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from jsonschema import Draft202012Validator

from master_all_strings.education import (
    GUIDANCE_POLICY_VERSION,
    GUIDANCE_SCHEMA_VERSION,
    EducationContractError,
    PracticeNextActionType,
    PracticeNextActionV1,
    TeachingGuidanceItemV1,
    TeachingGuidanceProjectionV1,
    compute_guidance_digest,
    serialize_guidance_projection,
    sort_guidance_items,
    to_dict,
)
from master_all_strings.education.contracts import PracticeFindingSeverity, PracticeFindingType
from master_all_strings.education.guidance import GUIDANCE_POLICY_VERSION as POLICY
from master_all_strings.education.guidance import projection_with_digest

REPO = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO / "resources" / "education" / "schema"
SCHEMA_PATH = SCHEMA_DIR / "teaching_guidance_projection_v1.schema.json"

DIGEST = "sha256:" + ("a" * 64)
REVISION = "rev-do014-contract"


def _continue() -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.CONTINUE,
        reason_finding_ids=(),
        message_key="action.continue",
    )


def _item(
    finding_id: str = "timing-late-0001",
    *,
    event_id: str | None = "ev-1",
    finding_type: PracticeFindingType = PracticeFindingType.LATE_ENTRY,
    zone_context: str | None = None,
) -> TeachingGuidanceItemV1:
    return TeachingGuidanceItemV1(
        schema_version=TeachingGuidanceItemV1.SCHEMA_VERSION,
        finding_id=finding_id,
        finding_type=finding_type,
        severity=PracticeFindingSeverity.FOCUS,
        evidence_refs=("aligned:ev-1@0:obs-1",),
        message_key="finding.late_entry",
        canonical_event_id=event_id,
        observed_value=140.0,
        threshold_value=100.0,
        zone_context=zone_context,
    )


def _projection(
    items: tuple[TeachingGuidanceItemV1, ...] | None = None,
    *,
    next_action: PracticeNextActionV1 | None = None,
    provenance: tuple[tuple[str, str], ...] = (("producer", "TeachingGuidanceProjectionV1"),),
    evaluation_digest: str = DIGEST,
    canonical_revision_id: str = REVISION,
    policy_version: str = GUIDANCE_POLICY_VERSION,
) -> TeachingGuidanceProjectionV1:
    ordered = sort_guidance_items(items if items is not None else (_item(),))
    action = next_action or _continue()
    digest = compute_guidance_digest(
        canonical_revision_id=canonical_revision_id,
        performance_session_id="session-1",
        evaluation_digest=evaluation_digest,
        policy_version=policy_version,
        items=ordered,
        next_action=action,
    )
    return TeachingGuidanceProjectionV1(
        schema_version=TeachingGuidanceProjectionV1.SCHEMA_VERSION,
        canonical_revision_id=canonical_revision_id,
        performance_session_id="session-1",
        evaluation_digest=evaluation_digest,
        policy_version=policy_version,
        items=ordered,
        next_action=action,
        guidance_digest=digest,
        provenance=provenance,
    )


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


# --- contract construction ---------------------------------------------------


def test_schema_and_policy_versions_are_explicit() -> None:
    assert GUIDANCE_SCHEMA_VERSION == "1.0.0"
    assert POLICY == "teaching-guidance-v1"
    assert TeachingGuidanceProjectionV1.SCHEMA_VERSION == GUIDANCE_SCHEMA_VERSION


def test_item_requires_evidence_and_known_types() -> None:
    with pytest.raises(EducationContractError, match="evidence_refs"):
        TeachingGuidanceItemV1(
            schema_version="1.0.0",
            finding_id="f1",
            finding_type=PracticeFindingType.LATE_ENTRY,
            severity=PracticeFindingSeverity.FOCUS,
            evidence_refs=(),
            message_key="finding.late_entry",
        )
    with pytest.raises(EducationContractError, match="finding_type"):
        TeachingGuidanceItemV1(
            schema_version="1.0.0",
            finding_id="f1",
            finding_type="late_entry",  # type: ignore[arg-type]
            severity=PracticeFindingSeverity.FOCUS,
            evidence_refs=("e1",),
            message_key="finding.late_entry",
        )
    with pytest.raises(EducationContractError, match="severity"):
        TeachingGuidanceItemV1(
            schema_version="1.0.0",
            finding_id="f1",
            finding_type=PracticeFindingType.LATE_ENTRY,
            severity="focus",  # type: ignore[arg-type]
            evidence_refs=("e1",),
            message_key="finding.late_entry",
        )


def test_item_allows_null_canonical_event_id() -> None:
    item = _item(event_id=None, finding_type=PracticeFindingType.UNEXPECTED_NOTE)
    assert item.canonical_event_id is None


def test_item_rejects_blank_canonical_event_id() -> None:
    with pytest.raises(EducationContractError, match="canonical_event_id"):
        _item(event_id="  ")


def test_projection_requires_sha256_digests() -> None:
    ordered = sort_guidance_items((_item(),))
    action = _continue()
    with pytest.raises(EducationContractError, match="evaluation_digest"):
        TeachingGuidanceProjectionV1(
            schema_version="1.0.0",
            canonical_revision_id=REVISION,
            performance_session_id="session-1",
            evaluation_digest="not-a-digest",
            policy_version=GUIDANCE_POLICY_VERSION,
            items=ordered,
            next_action=action,
            guidance_digest=DIGEST,
        )
    with pytest.raises(EducationContractError, match="guidance_digest"):
        TeachingGuidanceProjectionV1(
            schema_version="1.0.0",
            canonical_revision_id=REVISION,
            performance_session_id="session-1",
            evaluation_digest=DIGEST,
            policy_version=GUIDANCE_POLICY_VERSION,
            items=ordered,
            next_action=action,
            guidance_digest="sha1:abcd",
        )


def test_projection_rejects_malformed_items_and_action() -> None:
    with pytest.raises(EducationContractError, match="TeachingGuidanceItemV1"):
        TeachingGuidanceProjectionV1(
            schema_version="1.0.0",
            canonical_revision_id=REVISION,
            performance_session_id="session-1",
            evaluation_digest=DIGEST,
            policy_version=GUIDANCE_POLICY_VERSION,
            items=("nope",),  # type: ignore[arg-type]
            next_action=_continue(),
            guidance_digest=DIGEST,
        )
    with pytest.raises(EducationContractError, match="PracticeNextActionV1"):
        TeachingGuidanceProjectionV1(
            schema_version="1.0.0",
            canonical_revision_id=REVISION,
            performance_session_id="session-1",
            evaluation_digest=DIGEST,
            policy_version=GUIDANCE_POLICY_VERSION,
            items=(_item(),),
            next_action="continue",  # type: ignore[arg-type]
            guidance_digest=DIGEST,
        )


def test_continue_is_never_serialized_as_mastery() -> None:
    projection = _projection()
    text = serialize_guidance_projection(projection).lower()
    for token in ("mastered", "perfect", "complete", "passed curriculum"):
        assert token not in text
    assert projection.next_action.action_type is PracticeNextActionType.CONTINUE


def test_guided_event_ids_skip_untargeted_and_deduplicate() -> None:
    items = (
        _item("a", event_id="ev-2"),
        _item("b", event_id=None),
        _item("c", event_id="ev-2"),
        _item("d", event_id="ev-1"),
    )
    projection = _projection(items)
    # Sorted by finding_id, then first-seen canonical id. Untargeted items contribute none.
    assert projection.guided_event_ids == ("ev-2", "ev-1")


def test_sort_is_independent_of_input_order() -> None:
    first = (_item("z", event_id="ev-9"), _item("a", event_id="ev-1"))
    second = tuple(reversed(first))
    assert sort_guidance_items(first) == sort_guidance_items(second)


# --- serialization / digest --------------------------------------------------


def test_round_trip_is_semantically_equal() -> None:
    projection = _projection(
        (
            _item("timing-late-0001", event_id="ev-2"),
            _item("pitch-0001", event_id="ev-1", finding_type=PracticeFindingType.PITCH_DIFFERENCE),
        )
    )
    payload = json.loads(serialize_guidance_projection(projection))
    assert payload["schema_version"] == "1.0.0"
    assert payload["canonical_revision_id"] == REVISION
    assert payload["items"][0]["finding_id"] == "pitch-0001"
    assert payload["next_action"]["action_type"] == "continue"
    assert payload["guidance_digest"] == projection.guidance_digest
    again = compute_guidance_digest(
        canonical_revision_id=projection.canonical_revision_id,
        performance_session_id=projection.performance_session_id,
        evaluation_digest=projection.evaluation_digest,
        policy_version=projection.policy_version,
        items=projection.items,
        next_action=projection.next_action,
    )
    assert again == projection.guidance_digest


def test_digest_ignores_zone_context_and_provenance() -> None:
    plain = _projection((_item(zone_context=None),), provenance=(("producer", "a"),))
    zoned = _projection(
        (_item(zone_context="ZONE_1"),),
        provenance=(("producer", "b"), ("assembled_at", "wall-clock")),
    )
    assert plain.guidance_digest == zoned.guidance_digest


def test_digest_changes_when_canonical_event_changes() -> None:
    a = _projection((_item(event_id="ev-1"),))
    b = _projection((_item(event_id="ev-2"),))
    assert a.guidance_digest != b.guidance_digest


def test_projection_with_digest_is_idempotent() -> None:
    projection = _projection()
    assert projection_with_digest(projection) is projection


# --- schema ------------------------------------------------------------------


def test_guidance_schema_is_well_formed() -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == "1.0.0"
    assert schema["$id"].endswith("teaching-guidance-projection-v1.schema.json")


def test_valid_projection_satisfies_schema() -> None:
    jsonschema.validate(to_dict(_projection()), _schema())


def test_untargeted_item_satisfies_schema() -> None:
    jsonschema.validate(to_dict(_projection((_item(event_id=None),))), _schema())


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


REJECTIONS: tuple[tuple[str, Mutation], ...] = (
    ("missing schema version", _drop("schema_version")),
    ("missing revision ID", _drop("canonical_revision_id")),
    ("malformed canonical event ID type", _set("items", 0, "canonical_event_id", 12)),
    ("malformed guidance item", _set("items", 0, "finding_id", "")),
    ("invalid next-action value", _set("next_action", "action_type", "mastered")),
    ("malformed range type", _set("next_action", "focus_start_tick", "0")),
    ("unknown required enum", _set("items", 0, "severity", "critical")),
    ("unexpected object shape", _set("score_override", {"midi": 60})),
    ("malformed evaluation digest", _set("evaluation_digest", "md5:abcd")),
    ("malformed item evidence type", _set("items", 0, "evidence_refs", "aligned-1")),
)


@pytest.mark.parametrize("label,mutate", REJECTIONS, ids=[row[0] for row in REJECTIONS])
def test_schema_rejects_malformed_projections(label: str, mutate: Mutation) -> None:
    payload = to_dict(_projection())
    mutate(payload)
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(payload)


def test_end_before_start_is_rejected_by_the_action_contract() -> None:
    """Range order is a Python invariant of PracticeNextActionV1, not a new clock."""

    with pytest.raises(EducationContractError, match="focus_end_tick"):
        PracticeNextActionV1(
            schema_version="1.0.0",
            action_type=PracticeNextActionType.ISOLATE_PASSAGE,
            reason_finding_ids=("f1",),
            message_key="action.isolate_passage",
            focus_start_tick=480,
            focus_end_tick=0,
        )


def test_schema_does_not_accept_a_mutated_copy_of_a_valid_payload() -> None:
    payload = copy.deepcopy(to_dict(_projection()))
    payload["items"][0]["finding_type"] = "wrong_note"
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(payload)


def test_serialize_guidance_projection_rejects_non_projection() -> None:
    with pytest.raises(EducationContractError):
        serialize_guidance_projection(_item())  # type: ignore[arg-type]


# --- digest is content-addressed regardless of caller discipline -------------


def test_the_digest_ignores_the_order_items_arrive_in() -> None:
    """The digest sorts internally rather than trusting its caller.

    ``sort_keys`` orders a mapping's keys but never a list, so hashing items in
    the order given would make the digest depend on the order findings happened
    to be iterated. The builder sorts before calling, but the function is public
    and a different caller need not.
    """

    first = _item(event_id="ev-1")
    second = _item("timing-late-0002", event_id="ev-2")

    def digest_for(items):
        return compute_guidance_digest(
            canonical_revision_id="rev-1",
            performance_session_id="session-1",
            evaluation_digest="sha256:" + "0" * 64,
            policy_version=GUIDANCE_POLICY_VERSION,
            items=items,
            next_action=_continue(),
        )

    assert digest_for((first, second)) == digest_for((second, first))


def test_the_digest_still_distinguishes_different_content() -> None:
    """Sorting must not flatten genuinely different guidance into one hash."""

    def digest_for(items):
        return compute_guidance_digest(
            canonical_revision_id="rev-1",
            performance_session_id="session-1",
            evaluation_digest="sha256:" + "0" * 64,
            policy_version=GUIDANCE_POLICY_VERSION,
            items=items,
            next_action=_continue(),
        )

    one = (_item(event_id="ev-1"),)
    two = (_item(event_id="ev-1"), _item("timing-late-0002", event_id="ev-2"))
    assert digest_for(one) != digest_for(two)


def test_projection_with_digest_is_a_declared_export() -> None:
    """It is imported directly by callers, so the module should say it is public."""

    from master_all_strings.education import guidance

    assert "projection_with_digest" in guidance.__all__
