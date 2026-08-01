"""Deterministic ordering of revision content.

Canonical order is part of canonical identity (ADR-0008 D5). Two callers who submit the
same content in a different order must produce the same revision id, so ordering is
normalized before the digest is taken rather than left to whoever built the tuple.

The sort key for events is ``(start_tick, voice_id, midi_note, duration_ticks,
event_id)`` with ``None`` voices first. ``event_id`` is the final tiebreaker, which makes
the order total: no two distinct events can compare equal, so the result never depends on
the input order.
"""

from __future__ import annotations

from master_all_strings.core.musical_events.models import MusicalEvent
from master_all_strings.core.score.errors import (
    ScoreContractError,
    require_tuple,
    require_unique,
)
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.tempo import TempoChangeV1

# Sorts before any real voice id, so unvoiced events lead. A voice named "" cannot
# exist -- MusicalEvent rejects a blank voice_id -- so this cannot collide.
_UNVOICED_SORT_KEY = ""


def _event_sort_key(event: MusicalEvent) -> tuple[int, int, str, int, int, str]:
    voiced = 0 if event.voice_id is None else 1
    return (
        event.start_tick,
        voiced,
        event.voice_id or _UNVOICED_SORT_KEY,
        event.midi_note,
        event.duration_ticks,
        event.event_id,
    )


def canonicalize_events(events: tuple[MusicalEvent, ...]) -> tuple[MusicalEvent, ...]:
    """Return ``events`` in canonical order.

    Rejects duplicate event ids: two events with one id would make the order
    non-deterministic and every provenance record ambiguous.
    """
    require_tuple(events, "events")
    for event in events:
        if not isinstance(event, MusicalEvent):
            raise ScoreContractError("events must contain MusicalEvent values")
    require_unique([event.event_id for event in events], "event_id")
    return tuple(sorted(events, key=_event_sort_key))


def canonicalize_tempo_changes(
    changes: tuple[TempoChangeV1, ...],
) -> tuple[TempoChangeV1, ...]:
    """Return tempo changes ordered by tick, rejecting duplicate ticks."""
    require_tuple(changes, "tempo_changes")
    for change in changes:
        if not isinstance(change, TempoChangeV1):
            raise ScoreContractError("tempo_changes must contain TempoChangeV1 values")
    require_unique([change.tick for change in changes], "tempo_changes tick")
    return tuple(sorted(changes, key=lambda change: change.tick))


def canonicalize_meter_changes(
    changes: tuple[MeterChangeV1, ...],
) -> tuple[MeterChangeV1, ...]:
    """Return meter changes ordered by tick, rejecting duplicate ticks."""
    require_tuple(changes, "meter_changes")
    for change in changes:
        if not isinstance(change, MeterChangeV1):
            raise ScoreContractError("meter_changes must contain MeterChangeV1 values")
    require_unique([change.tick for change in changes], "meter_changes tick")
    return tuple(sorted(changes, key=lambda change: change.tick))
