"""Normalizing runtime MIDI into captured events, and closing captures.

This module may normalize *representation*. It must not quantize, respell, infer
fingering, or infer educational meaning (ADR-0007 §5.9). Concretely: it assigns
sequence numbers and validates shape, and it never changes a timestamp, a pitch, a
velocity, or a channel, and never fills in a ``source_string`` the source did not
supply.

Closure is the other responsibility here, and the important one. ``close_capture``
requires an explicit terminal state, and ``mark_capture_interrupted`` exists so a
crash has a single obvious path that cannot be confused with a normal stop.
"""

from __future__ import annotations

from master_all_strings.performance.contracts.capture import (
    SOURCE_STRING_UNRESOLVED,
    CaptureCompletionState,
    CapturedMidiEventV1,
    CaptureSourceV1,
    MidiEventType,
    RawPerformanceCaptureV1,
)
from master_all_strings.performance.contracts.errors import (
    PerformanceContractError,
    require_identifier,
)
from master_all_strings.performance.contracts.runtime import RuntimeFaultV1, RuntimeIdentityV1
from master_all_strings.performance.contracts.session import MeterV1


def normalize_midi_event(
    *,
    event_id: str,
    sequence_number: int,
    event_type: MidiEventType,
    capture_time_ns: int,
    channel: int,
    source_port: str,
    source_device: str,
    note: int | None = None,
    velocity: int | None = None,
    controller: int | None = None,
    controller_value: int | None = None,
    pitch_bend: int | None = None,
    source_string: int | None = SOURCE_STRING_UNRESOLVED,
    raw_payload: tuple[int, ...] = (),
) -> CapturedMidiEventV1:
    """Build a validated captured event from runtime-supplied values.

    Every value is passed through unchanged. ``source_string`` defaults to unresolved
    and is never derived from channel, pitch, or anything else: a per-string source
    reports it, and everything else leaves it unknown (ADR-0007 D7).
    """
    return CapturedMidiEventV1(
        schema_version=CapturedMidiEventV1.SCHEMA_VERSION,
        event_id=event_id,
        sequence_number=sequence_number,
        event_type=event_type,
        capture_time_ns=capture_time_ns,
        channel=channel,
        source_port=source_port,
        source_device=source_device,
        note=note,
        velocity=velocity,
        controller=controller,
        controller_value=controller_value,
        pitch_bend=pitch_bend,
        source_string=source_string,
        raw_payload=raw_payload,
    )


def build_raw_capture(
    *,
    capture_id: str,
    session_id: str,
    runtime_identity: RuntimeIdentityV1,
    source_identity: CaptureSourceV1,
    started_at: str,
    tempo_context: float,
    meter_context: MeterV1,
    events: tuple[CapturedMidiEventV1, ...] = (),
    warnings: tuple[str, ...] = (),
    provenance: tuple[tuple[str, str], ...] = (),
) -> RawPerformanceCaptureV1:
    """Open a capture in ``IN_PROGRESS``.

    A new capture is always open. There is no way to construct one that is already
    complete, so closure is always a deliberate act with a stated reason.
    """
    return RawPerformanceCaptureV1(
        schema_version=RawPerformanceCaptureV1.SCHEMA_VERSION,
        capture_id=capture_id,
        session_id=session_id,
        runtime_identity=runtime_identity,
        source_identity=source_identity,
        started_at=started_at,
        completion_state=CaptureCompletionState.IN_PROGRESS,
        tempo_context=tempo_context,
        meter_context=meter_context,
        events=events,
        ended_at=None,
        warnings=warnings,
        faults=(),
        provenance=provenance,
    )


def append_events(
    capture: RawPerformanceCaptureV1, events: tuple[CapturedMidiEventV1, ...]
) -> RawPerformanceCaptureV1:
    """Return a new capture with ``events`` appended.

    Refuses to append to a closed capture, which is the immutability guarantee made
    operational: once closed, a capture cannot grow.
    """
    if capture.is_closed:
        raise PerformanceContractError(
            f"capture {capture.capture_id!r} is closed ({capture.completion_state}) "
            "and cannot accept more events"
        )
    return _replace_capture(capture, events=capture.events + events)


def close_capture(
    capture: RawPerformanceCaptureV1,
    *,
    ended_at: str,
    completion_state: CaptureCompletionState = CaptureCompletionState.COMPLETE,
    faults: tuple[RuntimeFaultV1, ...] = (),
    warnings: tuple[str, ...] = (),
) -> RawPerformanceCaptureV1:
    """Close a capture with an explicit terminal state.

    Refuses to close an already-closed capture, so a late or duplicated stop cannot
    rewrite how a take ended.
    """
    require_identifier(ended_at, "ended_at")
    if completion_state is CaptureCompletionState.IN_PROGRESS:
        raise PerformanceContractError("close_capture requires a terminal completion state")
    if capture.is_closed:
        raise PerformanceContractError(
            f"capture {capture.capture_id!r} is already closed ({capture.completion_state})"
        )
    return _replace_capture(
        capture,
        completion_state=completion_state,
        ended_at=ended_at,
        faults=capture.faults + faults,
        warnings=capture.warnings + warnings,
    )


def mark_capture_interrupted(
    capture: RawPerformanceCaptureV1,
    *,
    ended_at: str,
    fault: RuntimeFaultV1,
    warning: str | None = None,
) -> RawPerformanceCaptureV1:
    """Close a capture as ``INTERRUPTED`` with the fault that caused it.

    The single path for a runtime failure during capture. Events accepted before the
    failure are preserved exactly; no note endings are invented, and the record says
    plainly that the take was cut short (ADR-0007 D15).
    """
    warnings = (warning,) if warning is not None else ()
    return close_capture(
        capture,
        ended_at=ended_at,
        completion_state=CaptureCompletionState.INTERRUPTED,
        faults=(fault,),
        warnings=warnings,
    )


def _replace_capture(
    capture: RawPerformanceCaptureV1,
    *,
    events: tuple[CapturedMidiEventV1, ...] | None = None,
    completion_state: CaptureCompletionState | None = None,
    ended_at: str | None = None,
    faults: tuple[RuntimeFaultV1, ...] | None = None,
    warnings: tuple[str, ...] | None = None,
) -> RawPerformanceCaptureV1:
    """Build a new capture from an existing one with selected fields replaced.

    Written out rather than using ``dataclasses.replace`` so that every field carried
    forward is visible: a silently dropped field on an evidence record would be a
    quiet loss of evidence.
    """
    return RawPerformanceCaptureV1(
        schema_version=capture.schema_version,
        capture_id=capture.capture_id,
        session_id=capture.session_id,
        runtime_identity=capture.runtime_identity,
        source_identity=capture.source_identity,
        started_at=capture.started_at,
        completion_state=(
            capture.completion_state if completion_state is None else completion_state
        ),
        tempo_context=capture.tempo_context,
        meter_context=capture.meter_context,
        events=capture.events if events is None else events,
        ended_at=capture.ended_at if ended_at is None else ended_at,
        warnings=capture.warnings if warnings is None else warnings,
        faults=capture.faults if faults is None else faults,
        provenance=capture.provenance,
    )
