"""MSME-backed alternate projection constrained to one selected string."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.spatial_mapping import MappingConstraints, generate_candidates
from master_all_strings.instruments import InstrumentProfile
from master_all_strings.mvp.errors import ProjectionBuildError


class OneStringEventStatus(StrEnum):
    PLAYABLE = "playable"
    UNPLAYABLE = "unplayable"


@dataclass(frozen=True)
class OneStringTeachingEventV1:
    event_id: str
    midi_note: int
    status: OneStringEventStatus
    requested_string_id: str
    display_order: int | None = None
    physical_fret_number: int | None = None
    relative_semitone_position: float | None = None
    normalized_position: float | None = None
    is_open_string: bool | None = None
    unresolved_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status is OneStringEventStatus.PLAYABLE:
            if any(
                value is None
                for value in (
                    self.display_order,
                    self.physical_fret_number,
                    self.relative_semitone_position,
                    self.normalized_position,
                    self.is_open_string,
                )
            ):
                raise ProjectionBuildError("playable one-string events require spatial fields")
            if self.unresolved_reason is not None:
                raise ProjectionBuildError("playable one-string events cannot be unresolved")
        elif not self.unresolved_reason:
            raise ProjectionBuildError("unplayable one-string events require an explicit reason")


@dataclass(frozen=True)
class OneStringTeachingProjectionV1:
    schema_version: str
    instrument_id: str
    requested_string_id: str
    display_label: str
    events: tuple[OneStringTeachingEventV1, ...]

    def __post_init__(self) -> None:
        if self.schema_version != "1.0":
            raise ProjectionBuildError("unsupported one-string teaching projection version")
        if not self.events:
            raise ProjectionBuildError("one-string teaching projection requires events")


def build_one_string_teaching_projection(
    events: Sequence[MusicalEvent],
    instrument: InstrumentProfile,
    *,
    string_id: str,
) -> OneStringTeachingProjectionV1:
    """Constrain MSME to one string and preserve impossible events explicitly."""

    requested = next(
        (string for string in instrument.strings if string.string_id == string_id),
        None,
    )
    if requested is None:
        raise ProjectionBuildError(f"unknown one-string teaching target: {string_id!r}")
    constraints = MappingConstraints(allowed_string_ids=(string_id,))
    projected: list[OneStringTeachingEventV1] = []
    for event in events:
        candidates = generate_candidates(event, instrument, constraints)
        if not candidates:
            projected.append(
                OneStringTeachingEventV1(
                    event_id=event.event_id,
                    midi_note=event.midi_note,
                    status=OneStringEventStatus.UNPLAYABLE,
                    requested_string_id=string_id,
                    unresolved_reason="unplayable_on_requested_string",
                )
            )
            continue
        position = candidates[0]
        projected.append(
            OneStringTeachingEventV1(
                event_id=event.event_id,
                midi_note=event.midi_note,
                status=OneStringEventStatus.PLAYABLE,
                requested_string_id=string_id,
                display_order=position.display_order,
                physical_fret_number=position.physical_fret_number,
                relative_semitone_position=position.relative_semitone_position,
                normalized_position=position.normalized_position,
                is_open_string=position.is_open_string,
            )
        )
    return OneStringTeachingProjectionV1(
        schema_version="1.0",
        instrument_id=instrument.instrument_id,
        requested_string_id=string_id,
        display_label=requested.display_label,
        events=tuple(projected),
    )


__all__ = [
    "OneStringEventStatus",
    "OneStringTeachingEventV1",
    "OneStringTeachingProjectionV1",
    "build_one_string_teaching_projection",
]
