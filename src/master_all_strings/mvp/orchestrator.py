"""MVP lesson orchestration: assignment → MSME → enumeration_v1 → projection.

Unplayable (zero-candidate) events become explicit projection rows here.
``lesson.pipeline`` hard-fail behavior is intentionally left unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from master_all_strings.core.spatial_mapping import generate_candidates
from master_all_strings.instruments import InstrumentProfile
from master_all_strings.lesson.auto_select import select_automatic_position
from master_all_strings.lesson.errors import LessonAssignmentError, LessonValidationError
from master_all_strings.lesson.importers.midi import build_assignment_from_midi
from master_all_strings.lesson.models import LessonAssignmentV1
from master_all_strings.lesson.overrides import apply_validated_overrides
from master_all_strings.lesson.resolver import ResolvedLessonV1, resolve_lesson_assignment
from master_all_strings.lesson.serialization import (
    compute_lesson_behavior_digest,
    deserialize_lesson_assignment,
)
from master_all_strings.lesson.validation import validate_assignment
from master_all_strings.mvp.errors import (
    LessonLoadError,
    MvpError,
    ProjectionBuildError,
    UnknownInstrumentError,
    UnsupportedMidiError,
    format_mvp_error,
)
from master_all_strings.mvp.projection.builder import (
    SelectedNoteInput,
    build_fretboard_scroll_projection,
)
from master_all_strings.mvp.projection.models import (
    FretboardScrollProjectionV1,
    SelectionOrigin,
)
from master_all_strings.mvp.projection.timeline import build_core_tempo_map

__all__ = ["MvpLessonOrchestrator", "MvpOrchestrationResultV1"]


@dataclass(frozen=True)
class MvpOrchestrationResultV1:
    assignment: LessonAssignmentV1
    resolved: ResolvedLessonV1
    behavior_digest: str
    projection: FretboardScrollProjectionV1
    candidate_counts: tuple[tuple[str, int], ...]


class MvpLessonOrchestrator:
    """Coordinate public Lesson/Core contracts into a product projection."""

    def __init__(self, instrument_profiles: Mapping[str, InstrumentProfile]) -> None:
        self._profiles = dict(instrument_profiles)

    def list_instruments(self) -> tuple[InstrumentProfile, ...]:
        return tuple(self._profiles[key] for key in sorted(self._profiles))

    def load_assignment(
        self,
        assignment: LessonAssignmentV1,
        *,
        instrument_profile_id: str | None = None,
    ) -> MvpOrchestrationResultV1:
        try:
            return self._run(assignment, instrument_profile_id=instrument_profile_id)
        except MvpError:
            # MVP boundary errors are already user-facing and semantically specific
            # (LessonLoadError, ProjectionBuildError, UnknownInstrumentError, ...).
            # Re-wrapping them would flatten that distinction for callers and tests.
            raise
        except LessonAssignmentError as exc:
            raise LessonLoadError(format_mvp_error(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - map foreign failures to the boundary
            raise ProjectionBuildError(format_mvp_error(exc)) from exc

    def load_assignment_json(
        self,
        text: str | bytes | dict[str, Any],
        *,
        instrument_profile_id: str | None = None,
    ) -> MvpOrchestrationResultV1:
        try:
            assignment = deserialize_lesson_assignment(text)
        except LessonAssignmentError as exc:
            raise LessonLoadError(format_mvp_error(exc)) from exc
        return self.load_assignment(assignment, instrument_profile_id=instrument_profile_id)

    def import_midi(
        self,
        midi_bytes: bytes,
        *,
        assignment_id: str,
        instrument_profile_id: str,
        source_name: str | None = None,
        title: str | None = None,
    ) -> MvpOrchestrationResultV1:
        try:
            imported = build_assignment_from_midi(
                midi_bytes,
                assignment_id=assignment_id,
                instrument_profile_id=instrument_profile_id,
                source_name=source_name,
                title=title,
            )
        except UnsupportedMidiError:
            raise
        except Exception as exc:  # noqa: BLE001 - import is a conversion boundary
            raise UnsupportedMidiError(format_mvp_error(exc)) from exc
        return self.load_assignment(
            imported.assignment,
            instrument_profile_id=instrument_profile_id,
        )

    def _run(
        self,
        assignment: LessonAssignmentV1,
        *,
        instrument_profile_id: str | None,
    ) -> MvpOrchestrationResultV1:
        profile_id = instrument_profile_id or assignment.spatial_guidance.instrument_profile_id
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise UnknownInstrumentError(f"Unknown instrument profile: {profile_id}")

        # Structural validation without physical override checks first; overrides are
        # validated against the chosen profile below. An explicit instrument override
        # at the MVP boundary (demos/CLI) is allowed to differ from the assignment's
        # declared profile, so no equality check is performed here.
        validate_assignment(
            assignment,
            instrument_profiles=None,
            validate_overrides_physically=False,
        )

        resolved = resolve_lesson_assignment(assignment)
        if not resolved.events:
            raise LessonLoadError("No usable musical events")

        override_positions = apply_validated_overrides(
            assignment.teacher_overrides,
            events=resolved.events,
            instrument=profile,
        )

        selected_notes: list[SelectedNoteInput] = []
        candidate_counts: list[tuple[str, int]] = []
        warnings: list[str] = []
        # Order-preserving set semantics: each unsupported feature is reported once.
        unsupported: dict[str, None] = {}

        # Soft spatial guidance for automatic selection uses assignment guidance,
        # even when the runtime instrument id was overridden.
        spatial = resolved.spatial

        for event in resolved.events:
            candidates = generate_candidates(event, profile)
            candidate_counts.append((event.event_id, len(candidates)))
            override = override_positions.get(event.event_id)
            if override is not None:
                selected_notes.append(
                    SelectedNoteInput(
                        event,
                        position=override,
                        selection_origin=SelectionOrigin.TEACHER_OVERRIDE,
                    )
                )
                continue
            if not candidates:
                selected_notes.append(
                    SelectedNoteInput(
                        event,
                        unresolved_reason="no_playable_position",
                    )
                )
                warnings.append(
                    f"event {event.event_id} is unplayable on {profile.instrument_id}"
                )
                continue
            try:
                position = select_automatic_position(candidates, spatial=spatial)
            except LessonValidationError:
                selected_notes.append(
                    SelectedNoteInput(
                        event,
                        unresolved_reason="no_admissible_position_under_guidance",
                    )
                )
                warnings.append(
                    f"event {event.event_id} has candidates but none satisfy guidance"
                )
                continue
            selected_notes.append(
                SelectedNoteInput(
                    event,
                    position=position,
                    selection_origin=SelectionOrigin.AUTOMATIC,
                )
            )

        if all(item.position is None for item in selected_notes):
            warnings.append("lesson contains no playable events on the selected instrument")

        onsets = [event.start_tick for event in resolved.events]
        if len(onsets) != len(set(onsets)):
            unsupported["chord_aware_selection"] = None

        source_tempos = tuple(
            (change.tick, change.tempo_bpm)
            for change in assignment.musical_content.tempo_changes
        )
        tempo_map = build_core_tempo_map(
            tempo_override_bpm=assignment.playback.tempo_override,
            source_tempo_changes=source_tempos,
        )

        projection = build_fretboard_scroll_projection(
            assignment_id=assignment.assignment_id,
            content_id=assignment.content_id,
            title=assignment.title,
            description=assignment.identity.description,
            objective=assignment.instruction.objective,
            teacher_note=assignment.instruction.teacher_note,
            ticks_per_quarter=assignment.musical_content.ticks_per_quarter,
            tempo_map=tempo_map,
            instrument=profile,
            selection_policy=assignment.spatial_guidance.fingering_policy_id,
            selected_notes=selected_notes,
            warnings=warnings,
            unsupported_features=tuple(unsupported),
        )
        return MvpOrchestrationResultV1(
            assignment=assignment,
            resolved=resolved,
            behavior_digest=compute_lesson_behavior_digest(assignment),
            projection=projection,
            candidate_counts=tuple(candidate_counts),
        )
