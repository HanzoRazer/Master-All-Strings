"""Practice evaluation contracts (DO-010).

These records interpret immutable Performance evidence. They never rewrite
measurement fields and never claim long-term mastery.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.education.errors import (
    EducationContractError,
    require_finite_number,
    require_identifier,
    require_nonnegative_int,
    require_optional_identifier,
    require_positive_int,
    require_ratio,
    require_schema_version,
    require_tuple,
    require_unique,
)
from master_all_strings.education.messages import MESSAGE_CATALOG_V1

__all__ = [
    "PracticeAttemptSummaryV1",
    "PracticeEvaluationPolicyV1",
    "PracticeEvaluationResultV1",
    "PracticeFindingSeverity",
    "PracticeFindingType",
    "PracticeFindingV1",
    "PracticeFocusRangeV1",
    "PracticeNextActionType",
    "PracticeNextActionV1",
]


class PracticeFindingType(StrEnum):
    EARLY_ENTRY = "early_entry"
    LATE_ENTRY = "late_entry"
    PITCH_DIFFERENCE = "pitch_difference"
    EXPECTED_NOTE_MISSING = "expected_note_missing"
    UNEXPECTED_NOTE = "unexpected_note"
    DURATION_SHORT = "duration_short"
    DURATION_LONG = "duration_long"
    REPETITION_IMPROVED = "repetition_improved"
    REPETITION_REGRESSED = "repetition_regressed"
    FINDINGS_CONCENTRATED = "findings_concentrated"


class PracticeFindingSeverity(StrEnum):
    """Ordinal guidance weight — never emotional judgment."""

    INFO = "info"
    FOCUS = "focus"
    SIGNIFICANT = "significant"


class PracticeNextActionType(StrEnum):
    CONTINUE = "continue"
    REPEAT = "repeat"
    SLOW_DOWN = "slow_down"
    ISOLATE_PASSAGE = "isolate_passage"
    VIEW_ONE_STRING = "view_one_string"
    ENABLE_ZONE_VIEW = "enable_zone_view"


SUPPORTED_PRACTICE_RATES: tuple[float, ...] = (0.5, 0.75, 1.0, 1.5)


@dataclass(frozen=True)
class PracticeEvaluationPolicyV1:
    """Versioned Educational thresholds — not Performance alignment windows."""

    schema_version: str
    policy_id: str
    early_finding_threshold_ms: int
    late_finding_threshold_ms: int
    pitch_difference_threshold_semitones: int
    passage_cluster_window_events: int
    passage_cluster_min_findings: int
    slow_down_finding_ratio: float
    continue_actionable_finding_count: int
    minimum_expected_events: int = 1

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.policy_id, "policy_id")
        require_nonnegative_int(self.early_finding_threshold_ms, "early_finding_threshold_ms")
        require_nonnegative_int(self.late_finding_threshold_ms, "late_finding_threshold_ms")
        require_nonnegative_int(
            self.pitch_difference_threshold_semitones, "pitch_difference_threshold_semitones"
        )
        require_positive_int(self.passage_cluster_window_events, "passage_cluster_window_events")
        require_positive_int(self.passage_cluster_min_findings, "passage_cluster_min_findings")
        require_ratio(self.slow_down_finding_ratio, "slow_down_finding_ratio")
        require_nonnegative_int(
            self.continue_actionable_finding_count, "continue_actionable_finding_count"
        )
        require_positive_int(self.minimum_expected_events, "minimum_expected_events")

    @classmethod
    def mvp_defaults(cls, *, policy_id: str = "mvp-do010-v1") -> PracticeEvaluationPolicyV1:
        """Explicit DO-010 V1 defaults — never buried as magic numbers in evaluators."""

        return cls(
            schema_version=cls.SCHEMA_VERSION,
            policy_id=policy_id,
            early_finding_threshold_ms=100,
            late_finding_threshold_ms=100,
            pitch_difference_threshold_semitones=1,
            passage_cluster_window_events=4,
            passage_cluster_min_findings=3,
            slow_down_finding_ratio=0.30,
            continue_actionable_finding_count=1,
            minimum_expected_events=1,
        )


@dataclass(frozen=True)
class PracticeFocusRangeV1:
    """Canonical tick range identified for concentrated findings."""

    start_tick: int
    end_tick: int
    finding_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_nonnegative_int(self.start_tick, "start_tick")
        require_nonnegative_int(self.end_tick, "end_tick")
        if self.end_tick < self.start_tick:
            raise EducationContractError("end_tick must not precede start_tick")
        require_tuple(self.finding_ids, "finding_ids")
        for finding_id in self.finding_ids:
            require_identifier(finding_id, "finding_ids entry")
        require_unique(self.finding_ids, "finding_ids")


@dataclass(frozen=True)
class PracticeFindingV1:
    """One evidence-linked Educational interpretation."""

    schema_version: str
    finding_id: str
    finding_type: PracticeFindingType
    severity: PracticeFindingSeverity
    evidence_refs: tuple[str, ...]
    message_key: str
    expected_event_refs: tuple[str, ...] = ()
    repetition_index: int | None = None
    focus_start_tick: int | None = None
    focus_end_tick: int | None = None
    observed_value: float | None = None
    threshold_value: float | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.finding_id, "finding_id")
        if not isinstance(self.finding_type, PracticeFindingType):
            raise EducationContractError("finding_type must be a PracticeFindingType")
        if not isinstance(self.severity, PracticeFindingSeverity):
            raise EducationContractError("severity must be a PracticeFindingSeverity")
        require_tuple(self.evidence_refs, "evidence_refs")
        if not self.evidence_refs:
            raise EducationContractError("evidence_refs must cite at least one evidence object")
        for ref in self.evidence_refs:
            require_identifier(ref, "evidence_refs entry")
        require_unique(self.evidence_refs, "evidence_refs")
        require_tuple(self.expected_event_refs, "expected_event_refs")
        for ref in self.expected_event_refs:
            require_identifier(ref, "expected_event_refs entry")
        require_unique(self.expected_event_refs, "expected_event_refs")
        require_identifier(self.message_key, "message_key")
        if self.message_key not in MESSAGE_CATALOG_V1:
            raise EducationContractError(f"unknown message_key: {self.message_key!r}")
        if self.repetition_index is not None:
            require_nonnegative_int(self.repetition_index, "repetition_index")
        if self.focus_start_tick is not None:
            require_nonnegative_int(self.focus_start_tick, "focus_start_tick")
        if self.focus_end_tick is not None:
            require_nonnegative_int(self.focus_end_tick, "focus_end_tick")
        if (
            self.focus_start_tick is not None
            and self.focus_end_tick is not None
            and self.focus_end_tick < self.focus_start_tick
        ):
            raise EducationContractError("focus_end_tick must not precede focus_start_tick")
        if self.observed_value is not None:
            require_finite_number(self.observed_value, "observed_value")
        if self.threshold_value is not None:
            require_finite_number(self.threshold_value, "threshold_value")
        require_tuple(self.metadata, "metadata")
        for key, value in self.metadata:
            require_identifier(key, "metadata key")
            require_identifier(value, "metadata value")

    @property
    def is_actionable(self) -> bool:
        """FOCUS and SIGNIFICANT findings drive next-action decisions."""

        return self.severity is not PracticeFindingSeverity.INFO


@dataclass(frozen=True)
class PracticeNextActionV1:
    """Deterministic recommended practice action derived from findings."""

    schema_version: str
    action_type: PracticeNextActionType
    reason_finding_ids: tuple[str, ...]
    message_key: str
    target_rate: float | None = None
    focus_start_tick: int | None = None
    focus_end_tick: int | None = None
    teaching_aid: str | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        if not isinstance(self.action_type, PracticeNextActionType):
            raise EducationContractError("action_type must be a PracticeNextActionType")
        require_tuple(self.reason_finding_ids, "reason_finding_ids")
        for finding_id in self.reason_finding_ids:
            require_identifier(finding_id, "reason_finding_ids entry")
        require_unique(self.reason_finding_ids, "reason_finding_ids")
        require_identifier(self.message_key, "message_key")
        if self.message_key not in MESSAGE_CATALOG_V1:
            raise EducationContractError(f"unknown message_key: {self.message_key!r}")
        if self.target_rate is not None:
            require_finite_number(self.target_rate, "target_rate")
            if float(self.target_rate) not in SUPPORTED_PRACTICE_RATES:
                raise EducationContractError(
                    f"target_rate must be one of {SUPPORTED_PRACTICE_RATES}"
                )
        if self.focus_start_tick is not None:
            require_nonnegative_int(self.focus_start_tick, "focus_start_tick")
        if self.focus_end_tick is not None:
            require_nonnegative_int(self.focus_end_tick, "focus_end_tick")
        if (
            self.focus_start_tick is not None
            and self.focus_end_tick is not None
            and self.focus_end_tick < self.focus_start_tick
        ):
            raise EducationContractError("focus_end_tick must not precede focus_start_tick")
        require_optional_identifier(self.teaching_aid, "teaching_aid")
        if self.action_type is PracticeNextActionType.SLOW_DOWN and self.target_rate is None:
            raise EducationContractError("SLOW_DOWN requires target_rate")
        if self.action_type is PracticeNextActionType.ISOLATE_PASSAGE and (
            self.focus_start_tick is None or self.focus_end_tick is None
        ):
            raise EducationContractError("ISOLATE_PASSAGE requires focus tick range")


@dataclass(frozen=True)
class PracticeAttemptSummaryV1:
    """Attempt-level Educational interpretation summary."""

    schema_version: str
    performance_session_id: str
    expected_event_count: int
    observed_event_count: int
    matched_count: int
    missing_count: int
    extra_count: int
    pitch_finding_count: int
    timing_finding_count: int
    actionable_finding_count: int
    repetition_count: int
    focus_ranges: tuple[PracticeFocusRangeV1, ...]
    primary_action: PracticeNextActionV1
    secondary_actions: tuple[PracticeNextActionV1, ...] = ()

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.performance_session_id, "performance_session_id")
        for name in (
            "expected_event_count",
            "observed_event_count",
            "matched_count",
            "missing_count",
            "extra_count",
            "pitch_finding_count",
            "timing_finding_count",
            "actionable_finding_count",
            "repetition_count",
        ):
            require_nonnegative_int(getattr(self, name), name)
        require_tuple(self.focus_ranges, "focus_ranges")
        for focus in self.focus_ranges:
            if not isinstance(focus, PracticeFocusRangeV1):
                raise EducationContractError("focus_ranges must contain PracticeFocusRangeV1")
        if not isinstance(self.primary_action, PracticeNextActionV1):
            raise EducationContractError("primary_action must be a PracticeNextActionV1")
        require_tuple(self.secondary_actions, "secondary_actions")
        for action in self.secondary_actions:
            if not isinstance(action, PracticeNextActionV1):
                raise EducationContractError("secondary_actions must contain PracticeNextActionV1")


@dataclass(frozen=True)
class PracticeEvaluationResultV1:
    """Portable Educational evaluation artifact for one performance attempt."""

    schema_version: str
    assignment_id: str
    content_id: str
    performance_session_id: str
    evaluation_policy_id: str
    evaluation_policy_version: str
    findings: tuple[PracticeFindingV1, ...]
    summary: PracticeAttemptSummaryV1
    primary_next_action: PracticeNextActionV1
    secondary_actions: tuple[PracticeNextActionV1, ...]
    provenance: tuple[tuple[str, str], ...]
    evaluation_digest: str

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        for name in (
            "assignment_id",
            "content_id",
            "performance_session_id",
            "evaluation_policy_id",
            "evaluation_policy_version",
            "evaluation_digest",
        ):
            require_identifier(getattr(self, name), name)
        if not self.evaluation_digest.startswith("sha256:"):
            raise EducationContractError("evaluation_digest must be a sha256: digest")
        require_tuple(self.findings, "findings")
        for finding in self.findings:
            if not isinstance(finding, PracticeFindingV1):
                raise EducationContractError("findings must contain PracticeFindingV1")
        require_unique([f.finding_id for f in self.findings], "finding_id")
        if not isinstance(self.summary, PracticeAttemptSummaryV1):
            raise EducationContractError("summary must be a PracticeAttemptSummaryV1")
        if self.summary.performance_session_id != self.performance_session_id:
            raise EducationContractError("summary.performance_session_id mismatch")
        if not isinstance(self.primary_next_action, PracticeNextActionV1):
            raise EducationContractError("primary_next_action must be a PracticeNextActionV1")
        if self.summary.primary_action != self.primary_next_action:
            raise EducationContractError("summary.primary_action must equal primary_next_action")
        require_tuple(self.secondary_actions, "secondary_actions")
        for action in self.secondary_actions:
            if not isinstance(action, PracticeNextActionV1):
                raise EducationContractError("secondary_actions must contain PracticeNextActionV1")
        if self.summary.secondary_actions != self.secondary_actions:
            raise EducationContractError(
                "summary.secondary_actions must equal secondary_actions"
            )
        require_tuple(self.provenance, "provenance")
        for key, value in self.provenance:
            require_identifier(key, "provenance key")
            require_identifier(value, "provenance value")
