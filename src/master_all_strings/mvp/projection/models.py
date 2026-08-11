"""FretboardScrollProjectionV1 — product delivery projection (not canonical)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.core.foundation import (
    require_finite,
    require_index,
    require_midi_note,
    require_non_empty,
    require_nonnegative,
    require_positive,
)
from master_all_strings.mvp.errors import ProjectionBuildError, UnsupportedProjectionVersionError

__all__ = [
    "FRETBOARD_SCROLL_PROJECTION_TYPE",
    "FRETBOARD_SCROLL_PROJECTION_VERSION",
    "FretProjectionV1",
    "FretboardInstrumentProjectionV1",
    "FretboardLaneV1",
    "FretboardProjectedNoteV1",
    "FretboardScrollProjectionV1",
    "FretboardTimelineV1",
    "ProjectedNoteStatus",
    "SelectionOrigin",
    "TempoChangeProjectionV1",
]

FRETBOARD_SCROLL_PROJECTION_TYPE = "fretboard_scroll"
FRETBOARD_SCROLL_PROJECTION_VERSION = "1.0.0"


class ProjectedNoteStatus(StrEnum):
    SELECTED = "selected"
    UNPLAYABLE = "unplayable"


class SelectionOrigin(StrEnum):
    AUTOMATIC = "automatic"
    TEACHER_OVERRIDE = "teacher_override"


@dataclass(frozen=True)
class TempoChangeProjectionV1:
    tick: int
    tempo_bpm: float
    microseconds_per_quarter: int

    def __post_init__(self) -> None:
        require_index(self.tick, "tick")
        require_finite(self.tempo_bpm, "tempo_bpm")
        require_positive(self.tempo_bpm, "tempo_bpm")
        if (
            isinstance(self.microseconds_per_quarter, bool)
            or not isinstance(self.microseconds_per_quarter, int)
            or self.microseconds_per_quarter <= 0
        ):
            raise ProjectionBuildError("microseconds_per_quarter must be a positive integer")


@dataclass(frozen=True)
class FretboardTimelineV1:
    ticks_per_quarter: int
    total_ticks: int
    total_seconds: float
    seconds_per_screen: float
    play_line_fraction: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.ticks_per_quarter, bool)
            or not isinstance(self.ticks_per_quarter, int)
            or self.ticks_per_quarter <= 0
        ):
            raise ProjectionBuildError("ticks_per_quarter must be a positive integer")
        require_index(self.total_ticks, "total_ticks")
        require_finite(self.total_seconds, "total_seconds")
        require_nonnegative(self.total_seconds, "total_seconds")
        require_finite(self.seconds_per_screen, "seconds_per_screen")
        require_positive(self.seconds_per_screen, "seconds_per_screen")
        require_finite(self.play_line_fraction, "play_line_fraction")
        if not 0.0 <= self.play_line_fraction <= 1.0:
            raise ProjectionBuildError("play_line_fraction must be between 0 and 1")


@dataclass(frozen=True)
class FretboardLaneV1:
    string_id: str
    display_label: str
    display_order: int
    open_midi_note: int
    open_pitch_label: str

    def __post_init__(self) -> None:
        require_non_empty(self.string_id, "string_id")
        require_non_empty(self.display_label, "display_label")
        require_index(self.display_order, "display_order")
        require_midi_note(self.open_midi_note, "open_midi_note")
        require_non_empty(self.open_pitch_label, "open_pitch_label")


@dataclass(frozen=True)
class FretProjectionV1:
    fret_number: int
    normalized_position: float
    marker_label: str | None = None

    def __post_init__(self) -> None:
        require_index(self.fret_number, "fret_number")
        require_finite(self.normalized_position, "normalized_position")
        if not 0.0 <= self.normalized_position <= 1.0:
            raise ProjectionBuildError("normalized_position must be between 0 and 1")
        if self.marker_label is not None:
            require_non_empty(self.marker_label, "marker_label")


@dataclass(frozen=True)
class FretboardInstrumentProjectionV1:
    instrument_id: str
    display_name: str
    fingerboard_mode: str
    scale_length_mm: float | None
    lanes: tuple[FretboardLaneV1, ...]
    frets: tuple[FretProjectionV1, ...]

    def __post_init__(self) -> None:
        require_non_empty(self.instrument_id, "instrument_id")
        require_non_empty(self.display_name, "display_name")
        require_non_empty(self.fingerboard_mode, "fingerboard_mode")
        if self.scale_length_mm is not None:
            require_finite(self.scale_length_mm, "scale_length_mm")
            require_positive(self.scale_length_mm, "scale_length_mm")
        if not self.lanes:
            raise ProjectionBuildError("instrument lanes must not be empty")


@dataclass(frozen=True)
class FretboardProjectedNoteV1:
    event_id: str
    status: ProjectedNoteStatus
    midi_note: int
    pitch_label: str
    onset_tick: int
    duration_ticks: int
    onset_seconds: float
    release_seconds: float
    lane_display_order: int | None = None
    string_id: str | None = None
    fret_number: int | None = None
    relative_semitone_position: float | None = None
    normalized_position: float | None = None
    is_open_string: bool | None = None
    selection_origin: SelectionOrigin | None = None
    unresolved_reason: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.event_id, "event_id")
        try:
            status = ProjectedNoteStatus(self.status)
        except ValueError as exc:
            raise ProjectionBuildError(f"invalid note status: {self.status!r}") from exc
        object.__setattr__(self, "status", status)
        require_midi_note(self.midi_note, "midi_note")
        require_non_empty(self.pitch_label, "pitch_label")
        require_index(self.onset_tick, "onset_tick")
        if (
            isinstance(self.duration_ticks, bool)
            or not isinstance(self.duration_ticks, int)
            or self.duration_ticks <= 0
        ):
            raise ProjectionBuildError("duration_ticks must be a positive integer")
        require_finite(self.onset_seconds, "onset_seconds")
        require_nonnegative(self.onset_seconds, "onset_seconds")
        require_finite(self.release_seconds, "release_seconds")
        if self.release_seconds < self.onset_seconds:
            raise ProjectionBuildError("release_seconds must not precede onset_seconds")

        if status is ProjectedNoteStatus.SELECTED:
            if self.unresolved_reason is not None:
                raise ProjectionBuildError("selected notes must not carry unresolved_reason")
            if (
                self.string_id is None
                or self.fret_number is None
                or self.lane_display_order is None
                or self.relative_semitone_position is None
                or self.normalized_position is None
                or self.is_open_string is None
                or self.selection_origin is None
            ):
                raise ProjectionBuildError("selected notes require complete spatial fields")
            require_non_empty(self.string_id, "string_id")
            require_index(self.fret_number, "fret_number")
            require_index(self.lane_display_order, "lane_display_order")
            require_finite(self.relative_semitone_position, "relative_semitone_position")
            require_nonnegative(self.relative_semitone_position, "relative_semitone_position")
            require_finite(self.normalized_position, "normalized_position")
            if not 0.0 <= self.normalized_position <= 1.0:
                raise ProjectionBuildError("normalized_position must be between 0 and 1")
            if not isinstance(self.is_open_string, bool):
                raise ProjectionBuildError("is_open_string must be a boolean")
            try:
                origin = SelectionOrigin(self.selection_origin)
            except ValueError as exc:
                raise ProjectionBuildError(
                    f"invalid selection_origin: {self.selection_origin!r}"
                ) from exc
            object.__setattr__(self, "selection_origin", origin)
            return

        # Unplayable: no fabricated spatial fields.
        if any(
            value is not None
            for value in (
                self.string_id,
                self.fret_number,
                self.lane_display_order,
                self.relative_semitone_position,
                self.normalized_position,
                self.is_open_string,
                self.selection_origin,
            )
        ):
            raise ProjectionBuildError("unplayable notes must not carry spatial placement fields")
        if self.unresolved_reason is None or not str(self.unresolved_reason).strip():
            raise ProjectionBuildError("unplayable notes require unresolved_reason")


@dataclass(frozen=True)
class FretboardScrollProjectionV1:
    schema_version: str
    projection_type: str
    projection_version: str
    fidelity: str
    projection_digest: str
    assignment_id: str
    content_id: str
    title: str
    timeline: FretboardTimelineV1
    tempo_changes: tuple[TempoChangeProjectionV1, ...]
    instrument: FretboardInstrumentProjectionV1
    selection_policy: str
    notes: tuple[FretboardProjectedNoteV1, ...]
    warnings: tuple[str, ...] = ()
    unsupported_features: tuple[str, ...] = ()
    description: str | None = None
    objective: str | None = None
    teacher_note: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.schema_version, "schema_version")
        if self.projection_type != FRETBOARD_SCROLL_PROJECTION_TYPE:
            raise UnsupportedProjectionVersionError(
                f"unsupported projection_type: {self.projection_type!r}"
            )
        major = self.projection_version.split(".", 1)[0]
        expected_major = FRETBOARD_SCROLL_PROJECTION_VERSION.split(".", 1)[0]
        if (
            major != expected_major
            or self.projection_version != FRETBOARD_SCROLL_PROJECTION_VERSION
        ):
            raise UnsupportedProjectionVersionError(
                f"unsupported projection_version: {self.projection_version!r}"
            )
        require_non_empty(self.fidelity, "fidelity")
        require_non_empty(self.projection_digest, "projection_digest")
        require_non_empty(self.assignment_id, "assignment_id")
        require_non_empty(self.content_id, "content_id")
        require_non_empty(self.title, "title")
        require_non_empty(self.selection_policy, "selection_policy")
        if not self.tempo_changes:
            raise ProjectionBuildError("projection requires a tempo map")
        if self.tempo_changes[0].tick != 0:
            raise ProjectionBuildError("tempo map must begin at tick 0")
