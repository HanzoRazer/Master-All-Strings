"""Application-facing MVP state models (not domain duplicates)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.mvp.errors import MvpError
from master_all_strings.mvp.playback.models import LessonPlaybackPlanV1
from master_all_strings.mvp.practice.models import PracticeSessionPolicyV1
from master_all_strings.mvp.projection.models import FretboardScrollProjectionV1


class MvpLoadStatus(StrEnum):
    IDLE = "idle"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


@dataclass(frozen=True)
class MvpLessonSummaryV1:
    demo_id: str
    title: str
    description: str
    instrument_profile_id: str
    demonstrates: tuple[str, ...]
    audio_demo: bool = False
    known_limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class MvpInstrumentOptionV1:
    instrument_id: str
    display_name: str
    experimental: bool = False


@dataclass(frozen=True)
class MvpPracticeBundleV1:
    """Identity-checked delivery bundle without merging component authority."""

    schema_version: str
    assignment_id: str
    content_id: str
    fretboard_projection: FretboardScrollProjectionV1
    playback_plan: LessonPlaybackPlanV1
    practice_policy: PracticeSessionPolicyV1

    def __post_init__(self) -> None:
        if self.schema_version != "1.0.0":
            raise MvpError("Unsupported practice bundle version")
        identities = {
            (self.assignment_id, self.content_id),
            (
                self.fretboard_projection.assignment_id,
                self.fretboard_projection.content_id,
            ),
            (self.playback_plan.assignment_id, self.playback_plan.content_id),
            (self.practice_policy.assignment_id, self.practice_policy.content_id),
        }
        if len(identities) != 1:
            raise MvpError("Practice bundle components do not share source identity")
        projected = {note.event_id: note for note in self.fretboard_projection.notes}
        for event in self.playback_plan.events:
            note = projected.get(event.event_id)
            if note is None:
                continue
            if note.midi_note != event.midi_note or note.onset_seconds != event.onset_seconds:
                raise MvpError(
                    f"Practice bundle event {event.event_id!r} disagrees on pitch or onset"
                )


@dataclass(frozen=True)
class MvpProjectionResponseV1:
    status: MvpLoadStatus
    summary_title: str
    instrument_id: str
    behavior_digest: str
    projection: FretboardScrollProjectionV1
    playback_plan: LessonPlaybackPlanV1
    practice_policy: PracticeSessionPolicyV1
    warnings: tuple[str, ...] = ()
    unsupported_features: tuple[str, ...] = ()
