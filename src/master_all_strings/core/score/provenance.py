"""Where a canonical revision came from.

Provenance is **required** on every revision, not optional. A revision that cannot say
where it came from is unauditable, and that is true whether it came from a captured
performance, a manual construction, or a future Creative edit.

``SourceEventProvenanceV1`` is the side map that keeps instrument-specific capture
evidence reachable without putting it on ``MusicalEvent``. MIDI channel and observed
source string belong to how a performance was captured, not to what the music is
(ADR-0008 D9). Held as an ordered tuple rather than a mapping so the serialized form is
deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.core.score.errors import (
    ScoreContractError,
    require_identifier,
    require_nonnegative_int,
    require_positive_int,
    require_schema_version,
    require_tuple,
    require_unique,
)

# 16 MIDI channels, 0-based.
MAX_MIDI_CHANNEL = 15
# A source may report which string produced a note; index bound matches the capture
# contract's, without importing it.
MAX_SOURCE_STRING = 15


class ScoreSourceKind(StrEnum):
    """How a revision's content came into existence."""

    PERFORMANCE_CAPTURE = "performance_capture"
    MANUAL_CONSTRUCTION = "manual_construction"
    CREATIVE_EDIT = "creative_edit"
    IMPORT = "import"


class RoundingPolicy(StrEnum):
    """How fractional ticks were resolved during conversion.

    Named explicitly because Python's built-in ``round`` uses banker's rounding, which
    would make the conversion ambiguous to reimplement in another language. Elapsed
    times are nonnegative, so half-away-from-zero is half-up in practice.
    """

    ROUND_HALF_AWAY_FROM_ZERO = "round_half_away_from_zero"


@dataclass(frozen=True)
class SourceEventProvenanceV1:
    """The audit trail for one canonical event derived from captured performance.

    Timing and capture fields are optional on this generic contract because a manually
    constructed revision has no nanoseconds to record. ``DIRECT_EVENT_IMPORT_V1``
    requires them (A5), which is where the stricter rule belongs.
    """

    schema_version: str
    canonical_event_id: str
    source_capture_event_ids: tuple[str, ...] = ()
    source_channel: int | None = None
    observed_source_string: int | None = None
    source_capture_time_ns: int | None = None
    source_release_time_ns: int | None = None
    converted_start_tick: int | None = None
    converted_duration_ticks: int | None = None
    rounding_delta_start_ns: int | None = None
    rounding_delta_duration_ns: int | None = None
    rounding_policy: RoundingPolicy | None = None
    ticks_per_quarter: int | None = None
    microseconds_per_quarter: int | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.canonical_event_id, "canonical_event_id")

        require_tuple(self.source_capture_event_ids, "source_capture_event_ids")
        for source_id in self.source_capture_event_ids:
            require_identifier(source_id, "source_capture_event_ids entry")
        require_unique(self.source_capture_event_ids, "source_capture_event_ids")

        if self.source_channel is not None:
            self._require_range(self.source_channel, "source_channel", 0, MAX_MIDI_CHANNEL)
        if self.observed_source_string is not None:
            self._require_range(
                self.observed_source_string, "observed_source_string", 0, MAX_SOURCE_STRING
            )

        for name in (
            "source_capture_time_ns",
            "source_release_time_ns",
            "converted_start_tick",
        ):
            value = getattr(self, name)
            if value is not None:
                require_nonnegative_int(value, name)
        if self.converted_duration_ticks is not None:
            require_positive_int(self.converted_duration_ticks, "converted_duration_ticks")

        # Rounding deltas are signed: an event may round up or down.
        for name in ("rounding_delta_start_ns", "rounding_delta_duration_ns"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ScoreContractError(f"{name} must be an integer")

        if self.rounding_policy is not None and not isinstance(
            self.rounding_policy, RoundingPolicy
        ):
            raise ScoreContractError("rounding_policy must be a RoundingPolicy")
        for name in ("ticks_per_quarter", "microseconds_per_quarter"):
            value = getattr(self, name)
            if value is not None:
                require_positive_int(value, name)

        if (
            self.source_release_time_ns is not None
            and self.source_capture_time_ns is not None
            and self.source_release_time_ns < self.source_capture_time_ns
        ):
            raise ScoreContractError(
                "source_release_time_ns must not precede source_capture_time_ns"
            )

    @staticmethod
    def _require_range(value: int, field_name: str, low: int, high: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ScoreContractError(f"{field_name} must be an integer")
        if not low <= value <= high:
            raise ScoreContractError(f"{field_name} must be between {low} and {high}")

    @property
    def string_identity_observed(self) -> bool:
        """Whether the capture source actually reported a string for this event."""
        return self.observed_source_string is not None


@dataclass(frozen=True)
class RevisionProvenanceV1:
    """Where one canonical revision came from. Required on every revision."""

    schema_version: str
    source_kind: ScoreSourceKind
    policy_version: str
    source_reference: str | None = None
    event_provenance: tuple[SourceEventProvenanceV1, ...] = ()
    notes: tuple[str, ...] = ()

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        if not isinstance(self.source_kind, ScoreSourceKind):
            raise ScoreContractError("source_kind must be a ScoreSourceKind")
        require_identifier(self.policy_version, "policy_version")
        if self.source_reference is not None:
            require_identifier(self.source_reference, "source_reference")

        require_tuple(self.event_provenance, "event_provenance")
        for entry in self.event_provenance:
            if not isinstance(entry, SourceEventProvenanceV1):
                raise ScoreContractError(
                    "event_provenance must contain SourceEventProvenanceV1 values"
                )
        # One record per canonical event: two records for the same event would make the
        # audit trail ambiguous about which conversion actually happened.
        require_unique(
            [entry.canonical_event_id for entry in self.event_provenance],
            "event_provenance canonical_event_id",
        )

        require_tuple(self.notes, "notes")
        for note in self.notes:
            require_identifier(note, "notes entry")

        # A capture-sourced revision must say which capture; otherwise the evidence
        # trail stops at the boundary it most needs to cross.
        if (
            self.source_kind is ScoreSourceKind.PERFORMANCE_CAPTURE
            and self.source_reference is None
        ):
            raise ScoreContractError(
                "a performance_capture revision must record a source_reference"
            )

    def for_event(self, canonical_event_id: str) -> SourceEventProvenanceV1 | None:
        """Return the provenance record for an event, or ``None``."""
        for entry in self.event_provenance:
            if entry.canonical_event_id == canonical_event_id:
                return entry
        return None
