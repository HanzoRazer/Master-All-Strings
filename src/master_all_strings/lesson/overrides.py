"""Teacher-override validation against Musical Core / MSME physical truth."""

from __future__ import annotations

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.spatial_mapping import SpatialPosition, generate_candidates
from master_all_strings.instruments import InstrumentProfile

from .errors import TeacherOverrideError
from .models import SerializedCanonicalEventV1, TeacherOverrideV1

__all__ = [
    "ValidatedOverrideV1",
    "apply_validated_overrides",
    "resolve_override_position",
    "validate_teacher_override",
]


class ValidatedOverrideV1:
    """A physically verified override bound to its MSME candidate."""

    __slots__ = ("override", "position")

    def __init__(self, override: TeacherOverrideV1, position: SpatialPosition) -> None:
        self.override = override
        self.position = position


def _as_musical_event(event: SerializedCanonicalEventV1 | MusicalEvent) -> MusicalEvent:
    if isinstance(event, MusicalEvent):
        return event
    return MusicalEvent(
        event_id=event.event_id,
        midi_note=event.midi_note,
        start_tick=event.start_tick,
        duration_ticks=event.duration_ticks,
        velocity=event.velocity,
        cents_offset=event.cents_offset,
        voice_id=event.voice_id,
    )


def resolve_override_position(
    override: TeacherOverrideV1,
    *,
    event: SerializedCanonicalEventV1 | MusicalEvent,
    instrument: InstrumentProfile,
) -> SpatialPosition:
    """Return the MSME candidate matching the override, or raise."""

    musical = _as_musical_event(event)
    candidates = generate_candidates(musical, instrument)
    for candidate in candidates:
        if (
            candidate.string_id == override.string_id
            and candidate.physical_fret_number == override.physical_fret_number
        ):
            return candidate
    string_ids = {string.string_id for string in instrument.strings}
    if override.string_id not in string_ids:
        raise TeacherOverrideError(
            f"override string_id {override.string_id!r} is not on the instrument",
            code="override_impossible_position",
        )
    raise TeacherOverrideError(
        (
            f"override for event {override.event_id!r} at "
            f"{override.string_id!r} fret {override.physical_fret_number} "
            "is not physically valid for the event pitch"
        ),
        code="override_impossible_position",
    )


def validate_teacher_override(
    override: TeacherOverrideV1,
    *,
    event: SerializedCanonicalEventV1 | MusicalEvent,
    instrument: InstrumentProfile,
) -> ValidatedOverrideV1:
    """Verify event pitch + instrument physical validity, then accept the override."""

    position = resolve_override_position(override, event=event, instrument=instrument)
    return ValidatedOverrideV1(override=override, position=position)


def apply_validated_overrides(
    overrides: tuple[TeacherOverrideV1, ...],
    *,
    events: tuple[MusicalEvent, ...],
    instrument: InstrumentProfile,
) -> dict[str, SpatialPosition]:
    """Validate all overrides and return event_id → selected SpatialPosition."""

    by_id = {event.event_id: event for event in events}
    selected: dict[str, SpatialPosition] = {}
    for override in overrides:
        event = by_id.get(override.event_id)
        if event is None:
            raise TeacherOverrideError(
                f"override references unknown event_id {override.event_id!r}",
                code="override_unknown_event",
            )
        validated = validate_teacher_override(override, event=event, instrument=instrument)
        selected[override.event_id] = validated.position
    return selected
