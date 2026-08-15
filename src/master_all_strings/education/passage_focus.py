"""Passage focus clustering for concentrated Educational findings.

Isolate fires when >= ``passage_cluster_min_findings`` actionable findings occur
inside a sliding window of ``passage_cluster_window_events`` consecutive expected
events from the lesson timeline.
"""

from __future__ import annotations

from collections.abc import Sequence

from master_all_strings.education.contracts import (
    PracticeEvaluationPolicyV1,
    PracticeFindingSeverity,
    PracticeFindingType,
    PracticeFindingV1,
    PracticeFocusRangeV1,
)

__all__ = ["cluster_findings_by_passage", "concentrated_finding"]

_CLUSTER_TYPES = frozenset(
    {
        PracticeFindingType.EARLY_ENTRY,
        PracticeFindingType.LATE_ENTRY,
        PracticeFindingType.PITCH_DIFFERENCE,
        PracticeFindingType.EXPECTED_NOTE_MISSING,
    }
)


def cluster_findings_by_passage(
    findings: Sequence[PracticeFindingV1],
    policy: PracticeEvaluationPolicyV1,
    *,
    expected_ticks: Sequence[int] | None = None,
) -> tuple[PracticeFocusRangeV1, ...]:
    """Group actionable expected-event findings into focus ranges.

    ``expected_ticks`` is the ordered lesson expected-event start-tick sequence.
    When omitted, unique finding ticks are used as a degraded fallback.
    """

    candidates = [
        f
        for f in findings
        if f.is_actionable
        and f.focus_start_tick is not None
        and f.finding_type in _CLUSTER_TYPES
    ]
    candidates.sort(key=lambda item: (item.focus_start_tick or 0, item.finding_id))
    if not candidates:
        return ()

    if expected_ticks is not None and len(expected_ticks) > 0:
        ordered_ticks = list(expected_ticks)
    else:
        ordered_ticks = sorted(
            {f.focus_start_tick for f in candidates if f.focus_start_tick is not None}
        )

    window = policy.passage_cluster_window_events
    minimum = policy.passage_cluster_min_findings
    ranges: list[PracticeFocusRangeV1] = []
    used: set[str] = set()

    for start in range(len(ordered_ticks)):
        tick_window = ordered_ticks[start : start + window]
        if not tick_window:
            continue
        tick_set = set(tick_window)
        group = [
            f
            for f in candidates
            if f.finding_id not in used and f.focus_start_tick in tick_set
        ]
        if len(group) < minimum:
            continue
        finding_ids = tuple(sorted(f.finding_id for f in group))
        used.update(finding_ids)
        ranges.append(
            PracticeFocusRangeV1(
                start_tick=min(tick_window),
                end_tick=max(tick_window),
                finding_ids=finding_ids,
            )
        )
    return tuple(ranges)


def concentrated_finding(
    focus_ranges: Sequence[PracticeFocusRangeV1],
) -> PracticeFindingV1 | None:
    """Emit a SIGNIFICANT concentration finding for the primary focus range."""

    if not focus_ranges:
        return None
    primary = focus_ranges[0]
    return PracticeFindingV1(
        schema_version=PracticeFindingV1.SCHEMA_VERSION,
        finding_id="focus-concentrated-0001",
        finding_type=PracticeFindingType.FINDINGS_CONCENTRATED,
        severity=PracticeFindingSeverity.SIGNIFICANT,
        evidence_refs=primary.finding_ids,
        expected_event_refs=(),
        message_key="finding.findings_concentrated",
        focus_start_tick=primary.start_tick,
        focus_end_tick=primary.end_tick,
    )
