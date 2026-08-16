"""Deterministic next-action recommendation (DO-010).

Precedence:
ISOLATE_PASSAGE → SLOW_DOWN → REPEAT → CONTINUE
"""

from __future__ import annotations

from collections.abc import Sequence

from master_all_strings.education.contracts import (
    SUPPORTED_PRACTICE_RATES,
    PracticeEvaluationPolicyV1,
    PracticeFindingSeverity,
    PracticeFindingType,
    PracticeFindingV1,
    PracticeFocusRangeV1,
    PracticeNextActionType,
    PracticeNextActionV1,
)
from master_all_strings.education.errors import EducationContractError

__all__ = ["build_next_actions", "choose_primary_next_action", "supported_slower_rate"]


def supported_slower_rate(current_rate: float) -> float:
    """Map to the next slower supported practice rate."""

    if isinstance(current_rate, bool) or not isinstance(current_rate, (int, float)):
        raise EducationContractError("current_rate must be a number")
    rate = float(current_rate)
    if rate not in SUPPORTED_PRACTICE_RATES:
        raise EducationContractError(f"unsupported practice rate: {rate}")
    mapping = {1.5: 1.0, 1.0: 0.75, 0.75: 0.5, 0.5: 0.5}
    return mapping[rate]


def _actionable(findings: Sequence[PracticeFindingV1]) -> tuple[PracticeFindingV1, ...]:
    return tuple(f for f in findings if f.is_actionable)


def _timing_or_pitch(findings: Sequence[PracticeFindingV1]) -> tuple[PracticeFindingV1, ...]:
    allowed = {
        PracticeFindingType.EARLY_ENTRY,
        PracticeFindingType.LATE_ENTRY,
        PracticeFindingType.PITCH_DIFFERENCE,
    }
    return tuple(f for f in findings if f.is_actionable and f.finding_type in allowed)


def choose_primary_next_action(
    findings: Sequence[PracticeFindingV1],
    focus_ranges: Sequence[PracticeFocusRangeV1],
    policy: PracticeEvaluationPolicyV1,
    *,
    expected_event_count: int,
    current_rate: float = 1.0,
) -> PracticeNextActionV1:
    actionable = _actionable(findings)
    has_significant = any(f.severity is PracticeFindingSeverity.SIGNIFICANT for f in actionable)

    if focus_ranges and len(focus_ranges[0].finding_ids) >= policy.passage_cluster_min_findings:
        focus = focus_ranges[0]
        return PracticeNextActionV1(
            schema_version=PracticeNextActionV1.SCHEMA_VERSION,
            action_type=PracticeNextActionType.ISOLATE_PASSAGE,
            reason_finding_ids=focus.finding_ids,
            message_key="action.isolate_passage",
            focus_start_tick=focus.start_tick,
            focus_end_tick=focus.end_tick,
        )

    timing_pitch = _timing_or_pitch(findings)
    expected = max(expected_event_count, policy.minimum_expected_events)
    ratio = len(timing_pitch) / float(expected)
    if ratio >= policy.slow_down_finding_ratio:
        return PracticeNextActionV1(
            schema_version=PracticeNextActionV1.SCHEMA_VERSION,
            action_type=PracticeNextActionType.SLOW_DOWN,
            reason_finding_ids=tuple(f.finding_id for f in timing_pitch),
            message_key="action.slow_down",
            target_rate=supported_slower_rate(current_rate),
        )

    if len(actionable) > policy.continue_actionable_finding_count or has_significant:
        return PracticeNextActionV1(
            schema_version=PracticeNextActionV1.SCHEMA_VERSION,
            action_type=PracticeNextActionType.REPEAT,
            reason_finding_ids=tuple(f.finding_id for f in actionable),
            message_key="action.repeat",
        )

    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.CONTINUE,
        reason_finding_ids=tuple(f.finding_id for f in actionable),
        message_key="action.continue",
    )


def build_next_actions(
    findings: Sequence[PracticeFindingV1],
    focus_ranges: Sequence[PracticeFocusRangeV1],
    policy: PracticeEvaluationPolicyV1,
    *,
    expected_event_count: int,
    current_rate: float = 1.0,
) -> tuple[PracticeNextActionV1, tuple[PracticeNextActionV1, ...]]:
    primary = choose_primary_next_action(
        findings,
        focus_ranges,
        policy,
        expected_event_count=expected_event_count,
        current_rate=current_rate,
    )
    secondary: list[PracticeNextActionV1] = []
    if primary.action_type is not PracticeNextActionType.REPEAT:
        actionable = _actionable(findings)
        if actionable:
            secondary.append(
                PracticeNextActionV1(
                    schema_version=PracticeNextActionV1.SCHEMA_VERSION,
                    action_type=PracticeNextActionType.REPEAT,
                    reason_finding_ids=tuple(f.finding_id for f in actionable),
                    message_key="action.repeat",
                )
            )
    if (
        primary.action_type is not PracticeNextActionType.SLOW_DOWN
        and len(_timing_or_pitch(findings)) > 0
    ):
        secondary.append(
            PracticeNextActionV1(
                schema_version=PracticeNextActionV1.SCHEMA_VERSION,
                action_type=PracticeNextActionType.SLOW_DOWN,
                reason_finding_ids=tuple(f.finding_id for f in _timing_or_pitch(findings)),
                message_key="action.slow_down",
                target_rate=supported_slower_rate(current_rate),
            )
        )
    return primary, tuple(secondary)
