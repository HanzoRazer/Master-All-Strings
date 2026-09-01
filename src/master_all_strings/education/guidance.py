"""Teaching-guidance projection contracts (DO-014).

Educational interpretation stays in ``PracticeEvaluationResultV1``. This module
is only the score-aware projection of that result onto canonical event identity.
It does not score a performance, mint musical IDs, or rewrite findings.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any

from master_all_strings.education.contracts import (
    PracticeFindingSeverity,
    PracticeFindingType,
    PracticeNextActionV1,
)
from master_all_strings.education.errors import (
    EducationContractError,
    require_finite_number,
    require_identifier,
    require_optional_identifier,
    require_schema_version,
    require_tuple,
)
from master_all_strings.education.serialization import to_dict

__all__ = [
    "GUIDANCE_POLICY_VERSION",
    "GUIDANCE_SCHEMA_VERSION",
    "TeachingGuidanceItemV1",
    "TeachingGuidanceProjectionV1",
    "compute_guidance_digest",
    "guided_event_ids",
    "serialize_guidance_projection",
    "sort_guidance_items",
]

GUIDANCE_SCHEMA_VERSION = "1.0.0"
GUIDANCE_POLICY_VERSION = "teaching-guidance-v1"

#: Explanatory or circular fields. Changing them must not change the semantic
#: digest: zone context is optional enrichment (D11), ``guidance_digest`` cannot
#: hash itself, and provenance is audit evidence about the projection.
_DIGEST_EXCLUDED_ITEM_FIELDS = frozenset({"zone_context"})
_DIGEST_EXCLUDED_PROJECTION_FIELDS = frozenset({"guidance_digest", "provenance"})

_MASTERY_FORBIDDEN = ("mastered", "perfect", "complete", "passed curriculum")


def _require_finding_type(value: object) -> PracticeFindingType:
    if isinstance(value, PracticeFindingType):
        return value
    raise EducationContractError("finding_type must be a PracticeFindingType")


def _require_severity(value: object) -> PracticeFindingSeverity:
    if isinstance(value, PracticeFindingSeverity):
        return value
    raise EducationContractError("severity must be a PracticeFindingSeverity")


def _forbid_mastery_wording(text: str, field_name: str) -> None:
    lowered = text.lower()
    for token in _MASTERY_FORBIDDEN:
        if token in lowered:
            raise EducationContractError(
                f"{field_name} must not represent CONTINUE as mastery ({token!r})"
            )


@dataclass(frozen=True)
class TeachingGuidanceItemV1:
    """One Educational finding projected onto at most one canonical event.

    ``canonical_event_id`` is the cross-view join key. It is copied from the
    finding's expected-event references and is never minted here. A missing id
    is valid: some findings (unexpected notes, concentrated-range summaries)
    have no canonical event to attach to.
    """

    schema_version: str
    finding_id: str
    finding_type: PracticeFindingType
    severity: PracticeFindingSeverity
    evidence_refs: tuple[str, ...]
    message_key: str
    canonical_event_id: str | None = None
    observed_value: float | None = None
    threshold_value: float | None = None
    zone_context: str | None = None

    SCHEMA_VERSION = GUIDANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.finding_id, "finding_id")
        object.__setattr__(self, "finding_type", _require_finding_type(self.finding_type))
        object.__setattr__(self, "severity", _require_severity(self.severity))
        require_tuple(self.evidence_refs, "evidence_refs")
        if not self.evidence_refs:
            raise EducationContractError("evidence_refs must cite at least one evidence object")
        for ref in self.evidence_refs:
            require_identifier(ref, "evidence_refs entry")
        require_identifier(self.message_key, "message_key")
        require_optional_identifier(self.canonical_event_id, "canonical_event_id")
        if self.observed_value is not None:
            require_finite_number(self.observed_value, "observed_value")
        if self.threshold_value is not None:
            require_finite_number(self.threshold_value, "threshold_value")
        require_optional_identifier(self.zone_context, "zone_context")


@dataclass(frozen=True)
class TeachingGuidanceProjectionV1:
    """Score-aware projection of one ``PracticeEvaluationResultV1``.

    Cites a canonical revision and an evaluation. Does not carry TAB or notation
    payloads and must not be confused with those digests.
    """

    schema_version: str
    canonical_revision_id: str
    performance_session_id: str
    evaluation_digest: str
    policy_version: str
    items: tuple[TeachingGuidanceItemV1, ...]
    next_action: PracticeNextActionV1
    guidance_digest: str
    provenance: tuple[tuple[str, str], ...] = ()

    SCHEMA_VERSION = GUIDANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.canonical_revision_id, "canonical_revision_id")
        require_identifier(self.performance_session_id, "performance_session_id")
        require_identifier(self.evaluation_digest, "evaluation_digest")
        if not self.evaluation_digest.startswith("sha256:"):
            raise EducationContractError("evaluation_digest must be a sha256: digest")
        require_identifier(self.policy_version, "policy_version")
        require_identifier(self.guidance_digest, "guidance_digest")
        if not self.guidance_digest.startswith("sha256:"):
            raise EducationContractError("guidance_digest must be a sha256: digest")
        require_tuple(self.items, "items")
        for item in self.items:
            if not isinstance(item, TeachingGuidanceItemV1):
                raise EducationContractError("items must contain TeachingGuidanceItemV1")
        if not isinstance(self.next_action, PracticeNextActionV1):
            raise EducationContractError("next_action must be a PracticeNextActionV1")
        _forbid_mastery_wording(self.next_action.action_type.value, "next_action.action_type")
        _forbid_mastery_wording(self.next_action.message_key, "next_action.message_key")
        require_tuple(self.provenance, "provenance")
        for key, value in self.provenance:
            require_identifier(key, "provenance key")
            require_identifier(value, "provenance value")

    @property
    def guided_event_ids(self) -> tuple[str, ...]:
        """Canonical event ids that event-level items actually cite, in item order."""

        return guided_event_ids(self.items)


def guided_event_ids(items: tuple[TeachingGuidanceItemV1, ...]) -> tuple[str, ...]:
    """Stable unique canonical ids. Never invents an id for an untargeted finding."""

    seen: list[str] = []
    known: set[str] = set()
    for item in items:
        event_id = item.canonical_event_id
        if event_id is None or event_id in known:
            continue
        known.add(event_id)
        seen.append(event_id)
    return tuple(seen)


def sort_guidance_items(
    items: tuple[TeachingGuidanceItemV1, ...] | list[TeachingGuidanceItemV1],
) -> tuple[TeachingGuidanceItemV1, ...]:
    """Deterministic item order independent of input finding permutation."""

    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.finding_id,
                item.canonical_event_id or "",
                item.finding_type.value,
                item.severity.value,
            ),
        )
    )


def _item_digest_dict(item: TeachingGuidanceItemV1) -> dict[str, Any]:
    encoded = to_dict(item)
    for field_name in _DIGEST_EXCLUDED_ITEM_FIELDS:
        encoded.pop(field_name, None)
    return encoded


def compute_guidance_digest(
    *,
    canonical_revision_id: str,
    performance_session_id: str,
    evaluation_digest: str,
    policy_version: str,
    items: tuple[TeachingGuidanceItemV1, ...],
    next_action: PracticeNextActionV1,
) -> str:
    """Digest semantic guidance content only.

    Same revision + evaluation + policy version must hash identically. Zone
    context, provenance, and the digest field itself are excluded.
    """

    payload = {
        "canonical_revision_id": canonical_revision_id,
        "evaluation_digest": evaluation_digest,
        "items": [_item_digest_dict(item) for item in items],
        "next_action": to_dict(next_action),
        "performance_session_id": performance_session_id,
        "policy_version": policy_version,
        "schema_version": GUIDANCE_SCHEMA_VERSION,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def serialize_guidance_projection(projection: TeachingGuidanceProjectionV1) -> str:
    if not isinstance(projection, TeachingGuidanceProjectionV1):
        raise EducationContractError("expected a TeachingGuidanceProjectionV1")
    return json.dumps(to_dict(projection), indent=2, sort_keys=False, ensure_ascii=True) + "\n"


def projection_with_digest(
    projection: TeachingGuidanceProjectionV1,
) -> TeachingGuidanceProjectionV1:
    """Return ``projection`` with ``guidance_digest`` matching its semantic fields."""

    digest = compute_guidance_digest(
        canonical_revision_id=projection.canonical_revision_id,
        performance_session_id=projection.performance_session_id,
        evaluation_digest=projection.evaluation_digest,
        policy_version=projection.policy_version,
        items=projection.items,
        next_action=projection.next_action,
    )
    if projection.guidance_digest == digest:
        return projection
    return replace(projection, guidance_digest=digest)
