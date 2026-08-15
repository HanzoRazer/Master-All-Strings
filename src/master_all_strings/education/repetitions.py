"""Repetition comparison findings — descriptive only, never mastery claims."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from master_all_strings.education.contracts import (
    PracticeFindingSeverity,
    PracticeFindingType,
    PracticeFindingV1,
)

__all__ = ["compare_repetitions"]


def compare_repetitions(
    findings: Sequence[PracticeFindingV1],
) -> tuple[PracticeFindingV1, ...]:
    """Compare actionable finding counts across repetition_index values."""

    counts: Counter[int] = Counter()
    for finding in findings:
        if finding.repetition_index is None:
            continue
        if not finding.is_actionable:
            continue
        if finding.finding_type in {
            PracticeFindingType.REPETITION_IMPROVED,
            PracticeFindingType.REPETITION_REGRESSED,
            PracticeFindingType.FINDINGS_CONCENTRATED,
        }:
            continue
        counts[finding.repetition_index] += 1
    if len(counts) < 2:
        return ()
    ordered = sorted(counts.items())
    first_rep, first_count = ordered[0]
    last_rep, last_count = ordered[-1]
    if last_count < first_count:
        return (
            PracticeFindingV1(
                schema_version=PracticeFindingV1.SCHEMA_VERSION,
                finding_id="rep-improved-0001",
                finding_type=PracticeFindingType.REPETITION_IMPROVED,
                severity=PracticeFindingSeverity.INFO,
                evidence_refs=(f"repetition:{first_rep}", f"repetition:{last_rep}"),
                message_key="finding.repetition_improved",
                observed_value=float(last_count),
                threshold_value=float(first_count),
                metadata=(
                    ("first_repetition", str(first_rep)),
                    ("last_repetition", str(last_rep)),
                    ("first_count", str(first_count)),
                    ("last_count", str(last_count)),
                ),
            ),
        )
    if last_count > first_count:
        return (
            PracticeFindingV1(
                schema_version=PracticeFindingV1.SCHEMA_VERSION,
                finding_id="rep-regressed-0001",
                finding_type=PracticeFindingType.REPETITION_REGRESSED,
                severity=PracticeFindingSeverity.INFO,
                evidence_refs=(f"repetition:{first_rep}", f"repetition:{last_rep}"),
                message_key="finding.repetition_regressed",
                observed_value=float(last_count),
                threshold_value=float(first_count),
                metadata=(
                    ("first_repetition", str(first_rep)),
                    ("last_repetition", str(last_rep)),
                    ("first_count", str(first_count)),
                    ("last_count", str(last_count)),
                ),
            ),
        )
    return ()
