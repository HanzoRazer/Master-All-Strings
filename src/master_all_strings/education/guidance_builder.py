"""Project PracticeEvaluationResultV1 onto canonical event identity (DO-014).

This module copies Educational findings and next actions onto a teaching-guidance
projection. It does not evaluate a performance, invent musical IDs, or choose a
different next action.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from master_all_strings.education.contracts import (
    PracticeEvaluationResultV1,
    PracticeFindingV1,
    PracticeNextActionV1,
)
from master_all_strings.education.errors import EducationContractError, require_identifier
from master_all_strings.education.guidance import (
    GUIDANCE_POLICY_VERSION,
    GUIDANCE_SCHEMA_VERSION,
    TeachingGuidanceItemV1,
    TeachingGuidanceProjectionV1,
    compute_guidance_digest,
    sort_guidance_items,
)

__all__ = ["build_teaching_guidance_projection"]

_PRODUCER = "TeachingGuidanceProjectionV1/v1"


def _item_for_event(
    finding: PracticeFindingV1,
    canonical_event_id: str | None,
    zone_by_event: Mapping[str, str] | None,
) -> TeachingGuidanceItemV1:
    zone_context = None
    if canonical_event_id is not None and zone_by_event is not None:
        zone = zone_by_event.get(canonical_event_id)
        if zone is not None:
            require_identifier(zone, "zone_context")
            zone_context = zone
    return TeachingGuidanceItemV1(
        schema_version=GUIDANCE_SCHEMA_VERSION,
        finding_id=finding.finding_id,
        finding_type=finding.finding_type,
        severity=finding.severity,
        evidence_refs=finding.evidence_refs,
        message_key=finding.message_key,
        canonical_event_id=canonical_event_id,
        observed_value=finding.observed_value,
        threshold_value=finding.threshold_value,
        zone_context=zone_context,
    )


def _items_from_finding(
    finding: PracticeFindingV1,
    zone_by_event: Mapping[str, str] | None,
) -> list[TeachingGuidanceItemV1]:
    refs = finding.expected_event_refs
    if not refs:
        return [_item_for_event(finding, None, zone_by_event)]
    return [_item_for_event(finding, event_id, zone_by_event) for event_id in refs]


def build_teaching_guidance_projection(
    evaluation: PracticeEvaluationResultV1,
    *,
    canonical_revision_id: str,
    policy_version: str = GUIDANCE_POLICY_VERSION,
    zone_by_event: Mapping[str, str] | None = None,
    provenance: Sequence[tuple[str, str]] | None = None,
) -> TeachingGuidanceProjectionV1:
    """Map one evaluation onto canonical events. No educational re-evaluation."""

    if not isinstance(evaluation, PracticeEvaluationResultV1):
        raise EducationContractError("evaluation must be a PracticeEvaluationResultV1")
    require_identifier(canonical_revision_id, "canonical_revision_id")
    require_identifier(policy_version, "policy_version")
    if not isinstance(evaluation.primary_next_action, PracticeNextActionV1):
        raise EducationContractError(
            "evaluation.primary_next_action must be a PracticeNextActionV1"
        )

    items: list[TeachingGuidanceItemV1] = []
    for finding in evaluation.findings:
        if not isinstance(finding, PracticeFindingV1):
            raise EducationContractError("findings must contain PracticeFindingV1")
        items.extend(_items_from_finding(finding, zone_by_event))
    ordered = sort_guidance_items(items)

    provenance_tuple = (
        tuple(provenance)
        if provenance is not None
        else (
            ("producer", _PRODUCER),
            ("evaluation_digest", evaluation.evaluation_digest),
        )
    )
    digest = compute_guidance_digest(
        canonical_revision_id=canonical_revision_id,
        performance_session_id=evaluation.performance_session_id,
        evaluation_digest=evaluation.evaluation_digest,
        policy_version=policy_version,
        items=ordered,
        next_action=evaluation.primary_next_action,
    )
    return TeachingGuidanceProjectionV1(
        schema_version=GUIDANCE_SCHEMA_VERSION,
        canonical_revision_id=canonical_revision_id,
        performance_session_id=evaluation.performance_session_id,
        evaluation_digest=evaluation.evaluation_digest,
        policy_version=policy_version,
        items=ordered,
        next_action=evaluation.primary_next_action,
        guidance_digest=digest,
        provenance=provenance_tuple,
    )
