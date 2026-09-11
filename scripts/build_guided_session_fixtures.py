"""Regenerate guided-practice session fixtures (DO-015 Stage 3).

Each fixture is produced by the Stage 2 public lifecycle service from fixed
DO-014 evaluation/guidance inputs. This script does not choose Educational
actions, mint identities, or execute Transport.

Usage: python scripts/build_guided_session_fixtures.py [--check]
"""

from __future__ import annotations

import argparse
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
from master_all_strings.education.guidance_builder import build_teaching_guidance_projection
from master_all_strings.education.guided_session import (
    GuidedPracticeActionDisposition,
    GuidedPracticeExecutionStatus,
    GuidedPracticeSessionV1,
    serialize_guided_practice_session,
)
from master_all_strings.education.guided_session_service import (
    append_evaluated_attempt,
    create_from_first_evaluated_attempt,
    record_action_disposition,
    record_action_execution,
    transition_session,
)
from master_all_strings.education.serialization import compute_evaluation_digest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "resources" / "education" / "examples" / "guided_sessions"

ASSIGNMENT = "assignment-do015-001"
CONTENT = "content-do015-001"
REVISION = "revision-do015-001"
NEXT_ASSIGNMENT = "assignment-do015-002"
NEXT_CONTENT = "content-do015-002"
OTHER_REVISION = "revision-do015-002"
FINDING_ID = "finding-do015-001"

FIXTURE_STEMS = (
    "slow_down_accepted",
    "slow_down_declined",
    "isolate_passage_accepted",
    "repeat_accepted",
    "continue_accepted_closed",
    "continue_declined",
    "execution_failed",
    "view_one_string_unsupported",
    "lesson_transition",
    "three_attempt_progression",
)


def _session_id(stem: str) -> str:
    return f"session-do015-{stem}"


def _attempt_id(stem: str, index: int = 0) -> str:
    return f"attempt-do015-{stem}-{index}"


def _performance_session_id(stem: str, index: int = 0) -> str:
    return f"performance-session-do015-{stem}-{index}"


def _finding() -> PracticeFindingV1:
    return PracticeFindingV1(
        schema_version=PracticeFindingV1.SCHEMA_VERSION,
        finding_id=FINDING_ID,
        finding_type=PracticeFindingType.LATE_ENTRY,
        severity=PracticeFindingSeverity.FOCUS,
        evidence_refs=("aligned-event-do015-001",),
        expected_event_refs=("ev-do015-001",),
        message_key="finding.late_entry",
        observed_value=140.0,
        threshold_value=100.0,
    )


def _continue() -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.CONTINUE,
        reason_finding_ids=(),
        message_key="action.continue",
    )


def _slow_down() -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.SLOW_DOWN,
        reason_finding_ids=(FINDING_ID,),
        message_key="action.slow_down",
        target_rate=0.75,
    )


def _isolate() -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.ISOLATE_PASSAGE,
        reason_finding_ids=(FINDING_ID,),
        message_key="action.isolate_passage",
        focus_start_tick=960,
        focus_end_tick=1920,
    )


def _repeat() -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.REPEAT,
        reason_finding_ids=(FINDING_ID,),
        message_key="action.repeat",
    )


def _view_one_string() -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.VIEW_ONE_STRING,
        reason_finding_ids=(FINDING_ID,),
        message_key="action.view_one_string",
        teaching_aid="one_string",
    )


def _evaluation(
    action: PracticeNextActionV1,
    *,
    assignment_id: str = ASSIGNMENT,
    content_id: str = CONTENT,
    performance_session_id: str,
) -> PracticeEvaluationResultV1:
    findings = () if action.action_type is PracticeNextActionType.CONTINUE else (_finding(),)
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
        performance_session_id=performance_session_id,
        expected_event_count=1,
        observed_event_count=1,
        matched_count=1,
        missing_count=0,
        extra_count=0,
        pitch_finding_count=0,
        timing_finding_count=len(findings),
        actionable_finding_count=len(findings),
        repetition_count=1,
        focus_ranges=focus,
        primary_action=action,
        secondary_actions=(),
    )
    provenance = (("assembler", "scripts.build_guided_session_fixtures"),)
    digest = compute_evaluation_digest(
        assignment_id=assignment_id,
        content_id=content_id,
        performance_session_id=performance_session_id,
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
        assignment_id=assignment_id,
        content_id=content_id,
        performance_session_id=performance_session_id,
        evaluation_policy_id="mvp-do010-v1",
        evaluation_policy_version=PracticeEvaluationPolicyV1.SCHEMA_VERSION,
        findings=findings,
        summary=summary,
        primary_next_action=action,
        secondary_actions=(),
        provenance=provenance,
        evaluation_digest=digest,
    )


def _guidance(
    evaluation: PracticeEvaluationResultV1,
    *,
    canonical_revision_id: str = REVISION,
):
    return build_teaching_guidance_projection(
        evaluation,
        canonical_revision_id=canonical_revision_id,
    )


def _create(
    action: PracticeNextActionV1,
    *,
    stem: str,
    attempt_index: int = 0,
    assignment_id: str = ASSIGNMENT,
    content_id: str = CONTENT,
    canonical_revision_id: str = REVISION,
) -> GuidedPracticeSessionV1:
    evaluation = _evaluation(
        action,
        assignment_id=assignment_id,
        content_id=content_id,
        performance_session_id=_performance_session_id(stem, attempt_index),
    )
    return create_from_first_evaluated_attempt(
        evaluation,
        _guidance(evaluation, canonical_revision_id=canonical_revision_id),
        session_id=_session_id(stem),
        attempt_id=_attempt_id(stem, attempt_index),
    )


def _accept(session: GuidedPracticeSessionV1) -> GuidedPracticeSessionV1:
    return record_action_disposition(session, GuidedPracticeActionDisposition.ACCEPTED)


def _decline(session: GuidedPracticeSessionV1) -> GuidedPracticeSessionV1:
    return record_action_disposition(session, GuidedPracticeActionDisposition.DECLINED)


def _succeed(session: GuidedPracticeSessionV1) -> GuidedPracticeSessionV1:
    return record_action_execution(session, GuidedPracticeExecutionStatus.SUCCEEDED)


def _fail(session: GuidedPracticeSessionV1) -> GuidedPracticeSessionV1:
    return record_action_execution(session, GuidedPracticeExecutionStatus.FAILED)


def _unsupported(session: GuidedPracticeSessionV1) -> GuidedPracticeSessionV1:
    return record_action_execution(session, GuidedPracticeExecutionStatus.UNSUPPORTED)


def _append(
    session: GuidedPracticeSessionV1,
    action: PracticeNextActionV1,
    *,
    stem: str,
    attempt_index: int,
    canonical_revision_id: str = REVISION,
) -> GuidedPracticeSessionV1:
    evaluation = _evaluation(
        action,
        assignment_id=session.assignment_id,
        content_id=session.content_id,
        performance_session_id=_performance_session_id(stem, attempt_index),
    )
    return append_evaluated_attempt(
        session,
        evaluation,
        _guidance(evaluation, canonical_revision_id=canonical_revision_id),
        attempt_id=_attempt_id(stem, attempt_index),
    )


def _accepted_succeeded(action: PracticeNextActionV1, *, stem: str) -> GuidedPracticeSessionV1:
    return _succeed(_accept(_create(action, stem=stem)))


def _declined_session(action: PracticeNextActionV1, *, stem: str) -> GuidedPracticeSessionV1:
    return _decline(_create(action, stem=stem))


def build_three_attempt_steps() -> tuple[
    GuidedPracticeSessionV1,
    GuidedPracticeSessionV1,
    GuidedPracticeSessionV1,
]:
    """Return the three-attempt golden after attempt 0, 1, and 2 resolve."""

    stem = "three_attempt_progression"
    after_0 = _succeed(_accept(_create(_slow_down(), stem=stem)))
    after_1 = _succeed(_accept(_append(after_0, _isolate(), stem=stem, attempt_index=1)))
    after_2 = _succeed(_accept(_append(after_1, _continue(), stem=stem, attempt_index=2)))
    return after_0, after_1, after_2


def build_continue_failed() -> GuidedPracticeSessionV1:
    return _fail(_accept(_create(_continue(), stem="continue_failed")))


def build_sessions() -> dict[str, GuidedPracticeSessionV1]:
    after_0, after_1, after_2 = build_three_attempt_steps()
    del after_0, after_1
    return {
        "slow_down_accepted": _accepted_succeeded(_slow_down(), stem="slow_down_accepted"),
        "slow_down_declined": _declined_session(_slow_down(), stem="slow_down_declined"),
        "isolate_passage_accepted": _accepted_succeeded(
            _isolate(), stem="isolate_passage_accepted"
        ),
        "repeat_accepted": _accepted_succeeded(_repeat(), stem="repeat_accepted"),
        "continue_accepted_closed": _accepted_succeeded(
            _continue(), stem="continue_accepted_closed"
        ),
        "continue_declined": _declined_session(_continue(), stem="continue_declined"),
        "execution_failed": _fail(_accept(_create(_slow_down(), stem="execution_failed"))),
        "view_one_string_unsupported": _unsupported(
            _accept(_create(_view_one_string(), stem="view_one_string_unsupported"))
        ),
        "lesson_transition": transition_session(
            _accepted_succeeded(_slow_down(), stem="lesson_transition"),
            next_assignment_id=NEXT_ASSIGNMENT,
            next_content_id=NEXT_CONTENT,
        ),
        "three_attempt_progression": after_2,
    }


def render_fixtures() -> dict[str, str]:
    return {
        stem: serialize_guided_practice_session(session)
        for stem, session in build_sessions().items()
    }


def write_fixtures() -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    for stem, text in render_fixtures().items():
        (EXAMPLES / f"{stem}.json").write_text(text, encoding="utf-8")


def check_fixtures() -> int:
    rendered = render_fixtures()
    drifted: list[str] = []
    existing = {path.stem for path in EXAMPLES.glob("*.json")}
    expected = set(FIXTURE_STEMS)
    if existing != expected:
        drifted.extend(sorted((existing | expected) - (existing & expected)))
    for stem, text in rendered.items():
        path = EXAMPLES / f"{stem}.json"
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            drifted.append(stem)
    if drifted:
        print("guided session fixture drift: " + ", ".join(dict.fromkeys(drifted)), file=sys.stderr)
        return 1
    print("guided session fixtures: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        return check_fixtures()
    write_fixtures()
    print(f"wrote {len(render_fixtures())} guided session fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
