"""Regenerate teaching-guidance projection fixtures (DO-014).

Each fixture is produced by ``build_teaching_guidance_projection`` from a
``PracticeEvaluationResultV1``. The Educational Engine still decides the
findings and next action; this script only projects them.

Usage: python scripts/build_guidance_fixtures.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from master_all_strings.education.contracts import (
    PracticeAttemptSummaryV1,
    PracticeEvaluationPolicyV1,
    PracticeEvaluationResultV1,
    PracticeFindingSeverity,
    PracticeFindingType,
    PracticeFindingV1,
    PracticeFocusRangeV1,
    PracticeNextActionType,
    PracticeNextActionV1,
)
from master_all_strings.education.evaluation import PracticeEvaluator
from master_all_strings.education.guidance_builder import build_teaching_guidance_projection
from master_all_strings.education.serialization import compute_evaluation_digest, to_dict
from master_all_strings.performance.contracts.alignment import (
    AlignedPerformanceEventV1,
    AlignmentStatus,
    PerformanceAlignmentPolicyV1,
    PerformanceAlignmentResultV1,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "resources" / "education" / "examples" / "guidance"

REVISION = "rev-b85e77022251b045cfe38b7d"


def _row(
    *,
    expected: str,
    observed: str | None = "obs",
    status: AlignmentStatus = AlignmentStatus.MATCHED_EXACT_PITCH,
    timing: int | None = 0,
    pitch: int | None = 0,
    tick: int = 0,
) -> AlignedPerformanceEventV1:
    return AlignedPerformanceEventV1(
        status=status,
        expected_event_id=expected,
        observed_event_id=None if status is AlignmentStatus.EXPECTED_NOT_OBSERVED else observed,
        repetition_index=0,
        timing_delta_ms=timing,
        pitch_delta_semitones=pitch,
        expected_start_tick=tick,
    )


def _evaluate(*rows: AlignedPerformanceEventV1) -> PracticeEvaluationResultV1:
    alignment = PerformanceAlignmentResultV1(
        schema_version="1.0.0",
        assignment_id="golden-do014",
        content_id="half_steps_one_string",
        performance_session_id="session-do014",
        alignment_policy=PerformanceAlignmentPolicyV1(),
        aligned_events=rows,
        unmatched_expected_ids=(),
        unmatched_observed_ids=(),
    )
    return PracticeEvaluator().evaluate(alignment)


def _finding(
    finding_id: str,
    *,
    event_ids: tuple[str, ...] = (),
    finding_type: PracticeFindingType = PracticeFindingType.LATE_ENTRY,
    severity: PracticeFindingSeverity = PracticeFindingSeverity.FOCUS,
    message_key: str = "finding.late_entry",
    evidence_refs: tuple[str, ...] = ("aligned:manual",),
    observed: float | None = 140.0,
    threshold: float | None = 100.0,
) -> PracticeFindingV1:
    return PracticeFindingV1(
        schema_version=PracticeFindingV1.SCHEMA_VERSION,
        finding_id=finding_id,
        finding_type=finding_type,
        severity=severity,
        evidence_refs=evidence_refs,
        expected_event_refs=event_ids,
        message_key=message_key,
        observed_value=observed,
        threshold_value=threshold,
    )


def _manual(
    findings: tuple[PracticeFindingV1, ...],
    action: PracticeNextActionV1,
    *,
    session_id: str,
) -> PracticeEvaluationResultV1:
    focus = ()
    if action.focus_start_tick is not None and action.focus_end_tick is not None:
        focus = (
            PracticeFocusRangeV1(
                action.focus_start_tick,
                action.focus_end_tick,
                action.reason_finding_ids,
            ),
        )
    summary = PracticeAttemptSummaryV1(
        schema_version=PracticeAttemptSummaryV1.SCHEMA_VERSION,
        performance_session_id=session_id,
        expected_event_count=6,
        observed_event_count=6,
        matched_count=6,
        missing_count=0,
        extra_count=0,
        pitch_finding_count=sum(
            1
            for finding in findings
            if finding.finding_type is PracticeFindingType.PITCH_DIFFERENCE
        ),
        timing_finding_count=sum(
            1
            for finding in findings
            if finding.finding_type
            in {PracticeFindingType.EARLY_ENTRY, PracticeFindingType.LATE_ENTRY}
        ),
        actionable_finding_count=sum(1 for finding in findings if finding.is_actionable),
        repetition_count=1,
        focus_ranges=focus,
        primary_action=action,
        secondary_actions=(),
    )
    provenance = (("assembler", "scripts.build_guidance_fixtures"),)
    digest = compute_evaluation_digest(
        assignment_id="golden-do014",
        content_id="half_steps_one_string",
        performance_session_id=session_id,
        evaluation_policy_id="mvp-do010-v1",
        evaluation_policy_version=PracticeEvaluationPolicyV1.SCHEMA_VERSION,
        findings=findings,
        summary=summary,
        primary_next_action=action,
        secondary_actions=(),
        provenance=provenance,
    )
    return PracticeEvaluationResultV1(
        schema_version=PracticeEvaluationResultV1.SCHEMA_VERSION,
        assignment_id="golden-do014",
        content_id="half_steps_one_string",
        performance_session_id=session_id,
        evaluation_policy_id="mvp-do010-v1",
        evaluation_policy_version=PracticeEvaluationPolicyV1.SCHEMA_VERSION,
        findings=findings,
        summary=summary,
        primary_next_action=action,
        secondary_actions=(),
        provenance=provenance,
        evaluation_digest=digest,
    )


def _cases() -> dict[str, PracticeEvaluationResultV1]:
    scale = [
        _row(expected=f"ev-{index}", observed=f"obs-{index}", timing=timing, tick=(index - 1) * 480)
        for index, timing in enumerate((0, 0, 0, 0, 0, 0), start=1)
    ]
    continue_eval = _evaluate(*scale)

    single = _manual(
        (
            _finding(
                "timing-late-0001",
                event_ids=("ev-2",),
                evidence_refs=("aligned:ev-2@0:obs-2",),
            ),
        ),
        PracticeNextActionV1(
            schema_version="1.0.0",
            action_type=PracticeNextActionType.REPEAT,
            reason_finding_ids=("timing-late-0001",),
            message_key="action.repeat",
        ),
        session_id="session-single",
    )

    multiple = _manual(
        (
            _finding(
                "timing-late-0001",
                event_ids=("ev-1",),
                evidence_refs=("aligned:ev-1@0:obs-1",),
            ),
            _finding(
                "pitch-0001",
                event_ids=("ev-3",),
                finding_type=PracticeFindingType.PITCH_DIFFERENCE,
                message_key="finding.pitch_difference",
                evidence_refs=("aligned:ev-3@0:obs-3",),
                observed=2.0,
                threshold=1.0,
            ),
        ),
        PracticeNextActionV1(
            schema_version="1.0.0",
            action_type=PracticeNextActionType.REPEAT,
            reason_finding_ids=("timing-late-0001", "pitch-0001"),
            message_key="action.repeat",
        ),
        session_id="session-multiple",
    )

    isolate = _manual(
        (
            _finding("timing-late-0001", event_ids=("ev-3",), evidence_refs=("aligned:ev-3",)),
            _finding("timing-late-0002", event_ids=("ev-4",), evidence_refs=("aligned:ev-4",)),
            _finding("timing-late-0003", event_ids=("ev-5",), evidence_refs=("aligned:ev-5",)),
        ),
        PracticeNextActionV1(
            schema_version="1.0.0",
            action_type=PracticeNextActionType.ISOLATE_PASSAGE,
            reason_finding_ids=("timing-late-0001", "timing-late-0002", "timing-late-0003"),
            message_key="action.isolate_passage",
            focus_start_tick=960,
            focus_end_tick=1920,
        ),
        session_id="session-isolate",
    )

    slow = _manual(
        tuple(
            _finding(
                f"timing-late-{index:04d}",
                event_ids=(f"ev-{index}",),
                evidence_refs=(f"aligned:ev-{index}",),
            )
            for index in range(1, 4)
        ),
        PracticeNextActionV1(
            schema_version="1.0.0",
            action_type=PracticeNextActionType.SLOW_DOWN,
            reason_finding_ids=("timing-late-0001", "timing-late-0002", "timing-late-0003"),
            message_key="action.slow_down",
            target_rate=0.75,
        ),
        session_id="session-slow",
    )

    unrenderable = _manual(
        (
            _finding(
                "timing-late-0001",
                event_ids=("ev-ghost",),
                evidence_refs=("aligned:ev-ghost",),
            ),
        ),
        PracticeNextActionV1(
            schema_version="1.0.0",
            action_type=PracticeNextActionType.REPEAT,
            reason_finding_ids=("timing-late-0001",),
            message_key="action.repeat",
        ),
        session_id="session-unrenderable",
    )

    return {
        "continue_guidance": continue_eval,
        "single_finding_guidance": single,
        "multiple_finding_guidance": multiple,
        "isolate_passage_guidance": isolate,
        "slow_down_guidance": slow,
        "unrenderable_event_guidance": unrenderable,
    }


def render_fixtures() -> dict[str, str]:
    rendered: dict[str, str] = {}
    for stem, evaluation in _cases().items():
        projection = build_teaching_guidance_projection(
            evaluation,
            canonical_revision_id=REVISION,
        )
        rendered[stem] = json.dumps(to_dict(projection), indent=2, sort_keys=False) + "\n"
    return rendered


def write_fixtures() -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    for stem, text in render_fixtures().items():
        (EXAMPLES / f"{stem}.json").write_text(text, encoding="utf-8")


def check_fixtures() -> int:
    rendered = render_fixtures()
    drifted = []
    for stem, text in rendered.items():
        path = EXAMPLES / f"{stem}.json"
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            drifted.append(stem)
    if drifted:
        print("guidance fixture drift: " + ", ".join(drifted), file=sys.stderr)
        return 1
    print("guidance fixtures: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        return check_fixtures()
    write_fixtures()
    print(f"wrote {len(render_fixtures())} guidance fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
