"""Deriving factual observations from a capture.

Everything produced here is evidence: counts, bounds, states, and faults. Nothing
here may conclude anything about a player. No function returns *beginner*, *poor*,
*mastered*, *too difficult*, or a curriculum recommendation, and the observation
contract has no field capable of carrying one (ADR-0007 D10, Seam 4).

The distinction is not stylistic. "Three note-offs are missing" is a fact about the
record; "the player is sloppy" is an interpretation about a person, and only the
Educational Engine may make it — citing this observation.
"""

from __future__ import annotations

from master_all_strings.performance.contracts.capture import (
    CapturedMidiEventV1,
    MidiEventType,
    PerformanceObservationV1,
    RawPerformanceCaptureV1,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.runtime import RuntimeState


def detect_missing_note_offs(
    capture: RawPerformanceCaptureV1,
) -> tuple[tuple[int, int], ...]:
    """Return ``(channel, note)`` pairs left sounding when the capture ended.

    A note is matched by (channel, note). Repeated note-ons for the same pair before a
    note-off count as separate sounding notes, because that is what the instrument
    reported — reconciling them would be interpretation.
    """
    sounding: dict[tuple[int, int], int] = {}
    for event in capture.events:
        if event.note is None:
            continue
        key = (event.channel, event.note)
        if event.event_type is MidiEventType.NOTE_ON and (event.velocity or 0) > 0:
            sounding[key] = sounding.get(key, 0) + 1
        elif event.event_type is MidiEventType.NOTE_OFF or (
            event.event_type is MidiEventType.NOTE_ON and (event.velocity or 0) == 0
        ):
            # A note-on with velocity 0 is a note-off by MIDI convention.
            if sounding.get(key):
                sounding[key] -= 1
                if sounding[key] == 0:
                    del sounding[key]
    return tuple(
        (channel, note) for (channel, note), count in sorted(sounding.items()) for _ in range(count)
    )


def summarize_capture_faults(capture: RawPerformanceCaptureV1) -> tuple[str, ...]:
    """Return the fault codes attached to a capture, in order."""
    return tuple(fault.code.value for fault in capture.faults)


def _velocity_bounds(events: tuple[CapturedMidiEventV1, ...]) -> tuple[int | None, int | None]:
    velocities = [
        e.velocity
        for e in events
        if e.event_type is MidiEventType.NOTE_ON and e.velocity is not None
    ]
    if not velocities:
        return None, None
    return min(velocities), max(velocities)


def derive_performance_observation(
    capture: RawPerformanceCaptureV1,
    *,
    observation_id: str,
    observed_at: str,
    runtime_state: RuntimeState,
) -> PerformanceObservationV1:
    """Derive the factual observation for a capture.

    Requires a closed capture: an observation about a take still in progress would be
    a statement about an incomplete record, and would go stale the moment the next
    event arrived.
    """
    if not capture.is_closed:
        raise PerformanceContractError(
            f"capture {capture.capture_id!r} is still IN_PROGRESS; "
            "an observation may only be derived from a closed capture"
        )

    events = capture.events
    note_ons = tuple(e for e in events if e.event_type is MidiEventType.NOTE_ON)
    note_offs = tuple(e for e in events if e.event_type is MidiEventType.NOTE_OFF)
    velocity_min, velocity_max = _velocity_bounds(events)

    channels = tuple(sorted({e.channel for e in events}))
    strings = tuple(sorted({e.source_string for e in events if e.source_string is not None}))
    unresolved = sum(1 for e in events if e.source_string is None)

    return PerformanceObservationV1(
        schema_version=PerformanceObservationV1.SCHEMA_VERSION,
        observation_id=observation_id,
        capture_id=capture.capture_id,
        session_id=capture.session_id,
        observed_at=observed_at,
        event_count=len(events),
        note_on_count=len(note_ons),
        note_off_count=len(note_offs),
        completion_state=capture.completion_state,
        runtime_state=runtime_state,
        first_event_time_ns=events[0].capture_time_ns if events else None,
        last_event_time_ns=events[-1].capture_time_ns if events else None,
        velocity_min=velocity_min,
        velocity_max=velocity_max,
        channels_observed=channels,
        source_strings_observed=strings,
        unresolved_string_event_count=unresolved,
        missing_note_off_count=len(detect_missing_note_offs(capture)),
        fault_codes=summarize_capture_faults(capture),
    )
