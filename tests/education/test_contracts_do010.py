"""DO-010 Commit 1: Educational Practice*V1 contracts, schemas, serialization."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from master_all_strings.education import (
    MESSAGE_CATALOG_V1,
    EducationContractError,
    PracticeAttemptSummaryV1,
    PracticeEvaluationPolicyV1,
    PracticeEvaluationResultV1,
    PracticeFindingSeverity,
    PracticeFindingType,
    PracticeFindingV1,
    PracticeFocusRangeV1,
    PracticeNextActionType,
    PracticeNextActionV1,
    compute_evaluation_digest,
    serialize_evaluation_result,
    to_dict,
)

REPO = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO / "resources" / "education" / "schema"


def _continue_action() -> PracticeNextActionV1:
    return PracticeNextActionV1(
        schema_version=PracticeNextActionV1.SCHEMA_VERSION,
        action_type=PracticeNextActionType.CONTINUE,
        reason_finding_ids=(),
        message_key="action.continue",
    )


def _finding(
    finding_id: str = "finding-1",
    *,
    finding_type: PracticeFindingType = PracticeFindingType.LATE_ENTRY,
    severity: PracticeFindingSeverity = PracticeFindingSeverity.FOCUS,
    observed: float = 142.0,
    threshold: float = 100.0,
) -> PracticeFindingV1:
    return PracticeFindingV1(
        schema_version=PracticeFindingV1.SCHEMA_VERSION,
        finding_id=finding_id,
        finding_type=finding_type,
        severity=severity,
        evidence_refs=("aligned-event-17",),
        expected_event_refs=("ev-17",),
        message_key={
            PracticeFindingType.LATE_ENTRY: "finding.late_entry",
            PracticeFindingType.EARLY_ENTRY: "finding.early_entry",
            PracticeFindingType.PITCH_DIFFERENCE: "finding.pitch_difference",
            PracticeFindingType.EXPECTED_NOTE_MISSING: "finding.expected_note_missing",
            PracticeFindingType.UNEXPECTED_NOTE: "finding.unexpected_note",
        }[finding_type],
        repetition_index=0,
        observed_value=observed,
        threshold_value=threshold,
    )


def test_mvp_default_policy_values_are_explicit() -> None:
    policy = PracticeEvaluationPolicyV1.mvp_defaults()
    assert policy.early_finding_threshold_ms == 100
    assert policy.late_finding_threshold_ms == 100
    assert policy.pitch_difference_threshold_semitones == 1
    assert policy.passage_cluster_window_events == 4
    assert policy.passage_cluster_min_findings == 3
    assert policy.slow_down_finding_ratio == pytest.approx(0.30)
    assert policy.continue_actionable_finding_count == 1


def test_policy_rejects_invalid_ratio() -> None:
    with pytest.raises(EducationContractError):
        PracticeEvaluationPolicyV1(
            schema_version="1.0.0",
            policy_id="bad",
            early_finding_threshold_ms=100,
            late_finding_threshold_ms=100,
            pitch_difference_threshold_semitones=1,
            passage_cluster_window_events=4,
            passage_cluster_min_findings=3,
            slow_down_finding_ratio=1.5,
            continue_actionable_finding_count=1,
        )


def test_finding_requires_evidence_and_known_message_key() -> None:
    with pytest.raises(EducationContractError, match="evidence_refs"):
        PracticeFindingV1(
            schema_version="1.0.0",
            finding_id="f1",
            finding_type=PracticeFindingType.LATE_ENTRY,
            severity=PracticeFindingSeverity.FOCUS,
            evidence_refs=(),
            message_key="finding.late_entry",
        )
    with pytest.raises(EducationContractError, match="message_key"):
        PracticeFindingV1(
            schema_version="1.0.0",
            finding_id="f1",
            finding_type=PracticeFindingType.LATE_ENTRY,
            severity=PracticeFindingSeverity.FOCUS,
            evidence_refs=("aligned-1",),
            message_key="finding.unknown",
        )


def test_finding_is_actionable_excludes_info() -> None:
    focus = _finding(severity=PracticeFindingSeverity.FOCUS)
    info = _finding(
        finding_id="finding-info",
        finding_type=PracticeFindingType.UNEXPECTED_NOTE,
        severity=PracticeFindingSeverity.INFO,
        observed=1.0,
        threshold=0.0,
    )
    assert focus.is_actionable is True
    assert info.is_actionable is False


def test_slow_down_requires_supported_rate() -> None:
    with pytest.raises(EducationContractError, match="target_rate"):
        PracticeNextActionV1(
            schema_version="1.0.0",
            action_type=PracticeNextActionType.SLOW_DOWN,
            reason_finding_ids=("f1",),
            message_key="action.slow_down",
        )
    with pytest.raises(EducationContractError, match="target_rate"):
        PracticeNextActionV1(
            schema_version="1.0.0",
            action_type=PracticeNextActionType.SLOW_DOWN,
            reason_finding_ids=("f1",),
            message_key="action.slow_down",
            target_rate=0.6,
        )


def test_isolate_requires_focus_range() -> None:
    with pytest.raises(EducationContractError, match="focus"):
        PracticeNextActionV1(
            schema_version="1.0.0",
            action_type=PracticeNextActionType.ISOLATE_PASSAGE,
            reason_finding_ids=("f1",),
            message_key="action.isolate_passage",
        )


def test_evaluation_result_round_trip_and_digest() -> None:
    finding = _finding()
    primary = _continue_action()
    summary = PracticeAttemptSummaryV1(
        schema_version=PracticeAttemptSummaryV1.SCHEMA_VERSION,
        performance_session_id="perf-1",
        expected_event_count=5,
        observed_event_count=5,
        matched_count=5,
        missing_count=0,
        extra_count=0,
        pitch_finding_count=0,
        timing_finding_count=1,
        actionable_finding_count=1,
        repetition_count=1,
        focus_ranges=(PracticeFocusRangeV1(0, 480, ("finding-1",)),),
        primary_action=primary,
        secondary_actions=(),
    )
    digest = compute_evaluation_digest(
        assignment_id="assign-1",
        content_id="content-1",
        performance_session_id="perf-1",
        evaluation_policy_id="mvp-do010-v1",
        evaluation_policy_version=PracticeEvaluationPolicyV1.SCHEMA_VERSION,
        findings=(finding,),
        summary=summary,
        primary_next_action=primary,
        secondary_actions=(),
        provenance=(("assembler", "education.tests"),),
    )
    result = PracticeEvaluationResultV1(
        schema_version=PracticeEvaluationResultV1.SCHEMA_VERSION,
        assignment_id="assign-1",
        content_id="content-1",
        performance_session_id="perf-1",
        evaluation_policy_id="mvp-do010-v1",
        evaluation_policy_version=PracticeEvaluationPolicyV1.SCHEMA_VERSION,
        findings=(finding,),
        summary=summary,
        primary_next_action=primary,
        secondary_actions=(),
        provenance=(("assembler", "education.tests"),),
        evaluation_digest=digest,
    )
    again = compute_evaluation_digest(
        assignment_id=result.assignment_id,
        content_id=result.content_id,
        performance_session_id=result.performance_session_id,
        evaluation_policy_id=result.evaluation_policy_id,
        evaluation_policy_version=result.evaluation_policy_version,
        findings=result.findings,
        summary=result.summary,
        primary_next_action=result.primary_next_action,
        secondary_actions=result.secondary_actions,
        provenance=result.provenance,
    )
    assert again == result.evaluation_digest
    text = serialize_evaluation_result(result)
    assert "sha256:" in text
    payload = json.loads(text)
    assert payload["findings"][0]["finding_type"] == "late_entry"
    assert to_dict(result)["primary_next_action"]["action_type"] == "continue"


def test_message_catalog_covers_all_finding_and_action_keys() -> None:
    for finding_type in PracticeFindingType:
        key = f"finding.{finding_type.value}"
        assert key in MESSAGE_CATALOG_V1
    for action in (
        PracticeNextActionType.CONTINUE,
        PracticeNextActionType.REPEAT,
        PracticeNextActionType.SLOW_DOWN,
        PracticeNextActionType.ISOLATE_PASSAGE,
    ):
        assert f"action.{action.value}" in MESSAGE_CATALOG_V1


@pytest.mark.parametrize(
    "name",
    [
        "practice_evaluation_policy_v1",
        "practice_finding_v1",
        "practice_next_action_v1",
        "practice_evaluation_result_v1",
    ],
)
def test_education_schemas_are_well_formed(name: str) -> None:
    schema = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == "1.0.0"


def test_policy_and_finding_validate_against_schemas() -> None:
    policy = PracticeEvaluationPolicyV1.mvp_defaults()
    finding = _finding()
    action = PracticeNextActionV1(
        schema_version="1.0.0",
        action_type=PracticeNextActionType.SLOW_DOWN,
        reason_finding_ids=("finding-1",),
        message_key="action.slow_down",
        target_rate=0.75,
    )
    jsonschema.validate(
        to_dict(policy),
        json.loads((SCHEMA_DIR / "practice_evaluation_policy_v1.schema.json").read_text()),
    )
    jsonschema.validate(
        to_dict(finding),
        json.loads((SCHEMA_DIR / "practice_finding_v1.schema.json").read_text()),
    )
    jsonschema.validate(
        to_dict(action),
        json.loads((SCHEMA_DIR / "practice_next_action_v1.schema.json").read_text()),
    )


def test_performance_must_not_import_education() -> None:
    performance_root = REPO / "src" / "master_all_strings" / "performance"
    offenders: list[str] = []
    for path in performance_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "master_all_strings.education" in text:
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == []


def test_contract_validation_edges_for_coverage() -> None:
    with pytest.raises(EducationContractError):
        PracticeFocusRangeV1(10, 5)
    with pytest.raises(EducationContractError):
        PracticeFindingV1(
            schema_version="1.0.0",
            finding_id="f1",
            finding_type="late_entry",  # type: ignore[arg-type]
            severity=PracticeFindingSeverity.FOCUS,
            evidence_refs=("e1",),
            message_key="finding.late_entry",
        )
    with pytest.raises(EducationContractError):
        PracticeFindingV1(
            schema_version="1.0.0",
            finding_id="f1",
            finding_type=PracticeFindingType.LATE_ENTRY,
            severity="focus",  # type: ignore[arg-type]
            evidence_refs=("e1",),
            message_key="finding.late_entry",
        )
    with pytest.raises(EducationContractError):
        PracticeFindingV1(
            schema_version="1.0.0",
            finding_id="f1",
            finding_type=PracticeFindingType.LATE_ENTRY,
            severity=PracticeFindingSeverity.FOCUS,
            evidence_refs=("e1",),
            message_key="finding.late_entry",
            focus_start_tick=20,
            focus_end_tick=10,
        )
    with pytest.raises(EducationContractError):
        PracticeFindingV1(
            schema_version="1.0.0",
            finding_id="f1",
            finding_type=PracticeFindingType.LATE_ENTRY,
            severity=PracticeFindingSeverity.FOCUS,
            evidence_refs=("e1",),
            message_key="finding.late_entry",
            metadata=((" ", "x"),),
        )
    with pytest.raises(EducationContractError):
        PracticeNextActionV1(
            schema_version="1.0.0",
            action_type="continue",  # type: ignore[arg-type]
            reason_finding_ids=(),
            message_key="action.continue",
        )
    with pytest.raises(EducationContractError):
        PracticeNextActionV1(
            schema_version="1.0.0",
            action_type=PracticeNextActionType.CONTINUE,
            reason_finding_ids=(),
            message_key="action.missing",
        )
    with pytest.raises(EducationContractError):
        PracticeNextActionV1(
            schema_version="1.0.0",
            action_type=PracticeNextActionType.CONTINUE,
            reason_finding_ids=(),
            message_key="action.continue",
            focus_start_tick=5,
            focus_end_tick=1,
        )
    primary = _continue_action()
    with pytest.raises(EducationContractError):
        PracticeAttemptSummaryV1(
            schema_version="1.0.0",
            performance_session_id="p",
            expected_event_count=1,
            observed_event_count=1,
            matched_count=1,
            missing_count=0,
            extra_count=0,
            pitch_finding_count=0,
            timing_finding_count=0,
            actionable_finding_count=0,
            repetition_count=1,
            focus_ranges=("nope",),  # type: ignore[arg-type]
            primary_action=primary,
        )
    with pytest.raises(EducationContractError):
        PracticeAttemptSummaryV1(
            schema_version="1.0.0",
            performance_session_id="p",
            expected_event_count=1,
            observed_event_count=1,
            matched_count=1,
            missing_count=0,
            extra_count=0,
            pitch_finding_count=0,
            timing_finding_count=0,
            actionable_finding_count=0,
            repetition_count=1,
            focus_ranges=(),
            primary_action="nope",  # type: ignore[arg-type]
        )
    with pytest.raises(EducationContractError):
        PracticeAttemptSummaryV1(
            schema_version="1.0.0",
            performance_session_id="p",
            expected_event_count=1,
            observed_event_count=1,
            matched_count=1,
            missing_count=0,
            extra_count=0,
            pitch_finding_count=0,
            timing_finding_count=0,
            actionable_finding_count=0,
            repetition_count=1,
            focus_ranges=(),
            primary_action=primary,
            secondary_actions=("nope",),  # type: ignore[arg-type]
        )
    finding = _finding()
    summary = PracticeAttemptSummaryV1(
        schema_version="1.0.0",
        performance_session_id="perf-1",
        expected_event_count=1,
        observed_event_count=1,
        matched_count=1,
        missing_count=0,
        extra_count=0,
        pitch_finding_count=0,
        timing_finding_count=1,
        actionable_finding_count=1,
        repetition_count=1,
        focus_ranges=(),
        primary_action=primary,
    )
    digest = compute_evaluation_digest(
        assignment_id="a",
        content_id="c",
        performance_session_id="perf-1",
        evaluation_policy_id="p",
        evaluation_policy_version="1.0.0",
        findings=(finding,),
        summary=summary,
        primary_next_action=primary,
        secondary_actions=(),
        provenance=(),
    )
    with pytest.raises(EducationContractError):
        PracticeEvaluationResultV1(
            schema_version="1.0.0",
            assignment_id="a",
            content_id="c",
            performance_session_id="perf-1",
            evaluation_policy_id="p",
            evaluation_policy_version="1.0.0",
            findings=("nope",),  # type: ignore[arg-type]
            summary=summary,
            primary_next_action=primary,
            secondary_actions=(),
            provenance=(),
            evaluation_digest=digest,
        )
    with pytest.raises(EducationContractError):
        PracticeEvaluationResultV1(
            schema_version="1.0.0",
            assignment_id="a",
            content_id="c",
            performance_session_id="other",
            evaluation_policy_id="p",
            evaluation_policy_version="1.0.0",
            findings=(finding,),
            summary=summary,
            primary_next_action=primary,
            secondary_actions=(),
            provenance=(),
            evaluation_digest=digest,
        )
    with pytest.raises(EducationContractError):
        PracticeEvaluationResultV1(
            schema_version="1.0.0",
            assignment_id="a",
            content_id="c",
            performance_session_id="perf-1",
            evaluation_policy_id="p",
            evaluation_policy_version="1.0.0",
            findings=(finding,),
            summary=summary,
            primary_next_action=primary,
            secondary_actions=(),
            provenance=(),
            evaluation_digest="not-a-digest",
        )
    with pytest.raises(EducationContractError):
        to_dict("nope")
    with pytest.raises(EducationContractError):
        serialize_evaluation_result("nope")  # type: ignore[arg-type]


def test_error_helpers() -> None:
    from master_all_strings.education.errors import (
        require_identifier,
        require_nonnegative_int,
        require_optional_identifier,
        require_positive_int,
        require_schema_version,
        require_tuple,
        require_unique,
    )

    with pytest.raises(EducationContractError):
        require_schema_version("2.0.0", "1.0.0")
    with pytest.raises(EducationContractError):
        require_identifier(" ", "x")
    with pytest.raises(EducationContractError):
        require_identifier(" x", "x")
    with pytest.raises(EducationContractError):
        require_optional_identifier(" ", "x")
    with pytest.raises(EducationContractError):
        require_nonnegative_int(True, "x")  # type: ignore[arg-type]
    with pytest.raises(EducationContractError):
        require_nonnegative_int(-1, "x")
    with pytest.raises(EducationContractError):
        require_positive_int(0, "x")
    with pytest.raises(EducationContractError):
        require_tuple([], "x")
    with pytest.raises(EducationContractError):
        require_unique(("a", "a"), "x")
