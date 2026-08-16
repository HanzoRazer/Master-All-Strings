"""Evidence-linked finding rules (DO-010).

Each finding cites Performance alignment evidence. Thresholds come only from
``PracticeEvaluationPolicyV1`` — never from buried constants.
"""

from __future__ import annotations

from collections.abc import Sequence

from master_all_strings.education.contracts import (
    PracticeEvaluationPolicyV1,
    PracticeFindingSeverity,
    PracticeFindingType,
    PracticeFindingV1,
)
from master_all_strings.performance.contracts.alignment import (
    AlignedPerformanceEventV1,
    AlignmentStatus,
)

__all__ = [
    "evaluate_extra_observed",
    "evaluate_missing_expected",
    "evaluate_pitch_findings",
    "evaluate_timing_findings",
]

_MATCHED = (
    AlignmentStatus.MATCHED_EXACT_PITCH,
    AlignmentStatus.MATCHED_PITCH_DIFFERENCE,
    AlignmentStatus.UNRESOLVED_CAPTURE,
)


def _evidence_key(row: AlignedPerformanceEventV1) -> str:
    expected = row.expected_event_id or "none"
    observed = row.observed_event_id or "none"
    return f"aligned:{expected}@{row.repetition_index}:{observed}"


def _expected_refs(row: AlignedPerformanceEventV1) -> tuple[str, ...]:
    if row.expected_event_id is None:
        return ()
    return (row.expected_event_id,)


def evaluate_timing_findings(
    aligned_events: Sequence[AlignedPerformanceEventV1],
    policy: PracticeEvaluationPolicyV1,
    *,
    id_prefix: str = "timing",
) -> tuple[PracticeFindingV1, ...]:
    findings: list[PracticeFindingV1] = []
    index = 0
    for row in aligned_events:
        if row.status not in _MATCHED:
            continue
        if row.timing_delta_ms is None:
            continue
        delta = row.timing_delta_ms
        if delta <= -policy.early_finding_threshold_ms:
            index += 1
            severity = (
                PracticeFindingSeverity.SIGNIFICANT
                if abs(delta) >= 2 * policy.early_finding_threshold_ms
                else PracticeFindingSeverity.FOCUS
            )
            findings.append(
                PracticeFindingV1(
                    schema_version=PracticeFindingV1.SCHEMA_VERSION,
                    finding_id=f"{id_prefix}-early-{index:04d}",
                    finding_type=PracticeFindingType.EARLY_ENTRY,
                    severity=severity,
                    evidence_refs=(_evidence_key(row),),
                    expected_event_refs=_expected_refs(row),
                    message_key="finding.early_entry",
                    repetition_index=row.repetition_index,
                    focus_start_tick=row.expected_start_tick,
                    focus_end_tick=row.expected_start_tick,
                    observed_value=float(delta),
                    threshold_value=float(-policy.early_finding_threshold_ms),
                )
            )
        elif delta >= policy.late_finding_threshold_ms:
            index += 1
            severity = (
                PracticeFindingSeverity.SIGNIFICANT
                if abs(delta) >= 2 * policy.late_finding_threshold_ms
                else PracticeFindingSeverity.FOCUS
            )
            findings.append(
                PracticeFindingV1(
                    schema_version=PracticeFindingV1.SCHEMA_VERSION,
                    finding_id=f"{id_prefix}-late-{index:04d}",
                    finding_type=PracticeFindingType.LATE_ENTRY,
                    severity=severity,
                    evidence_refs=(_evidence_key(row),),
                    expected_event_refs=_expected_refs(row),
                    message_key="finding.late_entry",
                    repetition_index=row.repetition_index,
                    focus_start_tick=row.expected_start_tick,
                    focus_end_tick=row.expected_start_tick,
                    observed_value=float(delta),
                    threshold_value=float(policy.late_finding_threshold_ms),
                )
            )
    return tuple(findings)


def evaluate_pitch_findings(
    aligned_events: Sequence[AlignedPerformanceEventV1],
    policy: PracticeEvaluationPolicyV1,
    *,
    id_prefix: str = "pitch",
) -> tuple[PracticeFindingV1, ...]:
    findings: list[PracticeFindingV1] = []
    index = 0
    for row in aligned_events:
        if row.status not in _MATCHED:
            continue
        if row.pitch_delta_semitones is None:
            continue
        distance = abs(row.pitch_delta_semitones)
        if distance < policy.pitch_difference_threshold_semitones:
            continue
        index += 1
        severity = (
            PracticeFindingSeverity.SIGNIFICANT
            if distance >= max(2, 2 * policy.pitch_difference_threshold_semitones)
            else PracticeFindingSeverity.FOCUS
        )
        findings.append(
            PracticeFindingV1(
                schema_version=PracticeFindingV1.SCHEMA_VERSION,
                finding_id=f"{id_prefix}-{index:04d}",
                finding_type=PracticeFindingType.PITCH_DIFFERENCE,
                severity=severity,
                evidence_refs=(_evidence_key(row),),
                expected_event_refs=_expected_refs(row),
                message_key="finding.pitch_difference",
                repetition_index=row.repetition_index,
                focus_start_tick=row.expected_start_tick,
                focus_end_tick=row.expected_start_tick,
                observed_value=float(row.pitch_delta_semitones),
                threshold_value=float(policy.pitch_difference_threshold_semitones),
            )
        )
    return tuple(findings)


def evaluate_missing_expected(
    aligned_events: Sequence[AlignedPerformanceEventV1],
    *,
    id_prefix: str = "missing",
) -> tuple[PracticeFindingV1, ...]:
    findings: list[PracticeFindingV1] = []
    index = 0
    for row in aligned_events:
        if row.status is not AlignmentStatus.EXPECTED_NOT_OBSERVED:
            continue
        index += 1
        findings.append(
            PracticeFindingV1(
                schema_version=PracticeFindingV1.SCHEMA_VERSION,
                finding_id=f"{id_prefix}-{index:04d}",
                finding_type=PracticeFindingType.EXPECTED_NOTE_MISSING,
                severity=PracticeFindingSeverity.FOCUS,
                evidence_refs=(_evidence_key(row),),
                expected_event_refs=_expected_refs(row),
                message_key="finding.expected_note_missing",
                repetition_index=row.repetition_index,
                focus_start_tick=row.expected_start_tick,
                focus_end_tick=row.expected_start_tick,
            )
        )
    return tuple(findings)


def evaluate_extra_observed(
    aligned_events: Sequence[AlignedPerformanceEventV1],
    *,
    id_prefix: str = "extra",
) -> tuple[PracticeFindingV1, ...]:
    """Every OBSERVED_NOT_EXPECTED row becomes UNEXPECTED_NOTE (always)."""

    extras = [
        row for row in aligned_events if row.status is AlignmentStatus.OBSERVED_NOT_EXPECTED
    ]
    total = len(extras)
    findings: list[PracticeFindingV1] = []
    for index, row in enumerate(extras, start=1):
        if total >= 3:
            severity = PracticeFindingSeverity.SIGNIFICANT
        elif total == 2:
            severity = PracticeFindingSeverity.FOCUS
        else:
            severity = PracticeFindingSeverity.INFO
        findings.append(
            PracticeFindingV1(
                schema_version=PracticeFindingV1.SCHEMA_VERSION,
                finding_id=f"{id_prefix}-{index:04d}",
                finding_type=PracticeFindingType.UNEXPECTED_NOTE,
                severity=severity,
                evidence_refs=(_evidence_key(row),),
                expected_event_refs=(),
                message_key="finding.unexpected_note",
                repetition_index=row.repetition_index,
                observed_value=1.0,
                threshold_value=0.0,
                metadata=(("extra_note_count", str(total)),),
            )
        )
    return tuple(findings)
