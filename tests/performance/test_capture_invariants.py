"""Raw-capture invariants (DO-006 §8.4).

Raw capture is the evidence everything downstream cites. These tests assert the
properties that make it trustworthy: order and timing survive, closure is deliberate,
faults stay attached, and nothing is ever invented or silently repaired.
"""

from __future__ import annotations

import dataclasses

import pytest
from helpers import T0, T1, make_event

from master_all_strings.performance.capture_normalization import (
    append_events,
    build_raw_capture,
    close_capture,
    mark_capture_interrupted,
    normalize_midi_event,
)
from master_all_strings.performance.contracts.capture import (
    CaptureCompletionState,
    CaptureSourceV1,
    MidiEventType,
    RawPerformanceCaptureV1,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.runtime import (
    RuntimeFaultV1,
    RuntimeIdentityV1,
    RuntimeState,
)
from master_all_strings.performance.contracts.session import MeterV1
from master_all_strings.performance.observations import (
    derive_performance_observation,
    detect_missing_note_offs,
)


def _capture(
    identity: RuntimeIdentityV1,
    source: CaptureSourceV1,
    meter: MeterV1,
    events: tuple[object, ...] = (),
) -> RawPerformanceCaptureV1:
    return build_raw_capture(
        capture_id="capture-1",
        session_id="session-001",
        runtime_identity=identity,
        source_identity=source,
        started_at=T0,
        tempo_context=120.0,
        meter_context=meter,
        events=events,  # type: ignore[arg-type]
    )


class TestOrderAndTiming:
    def test_event_order_is_preserved(self, open_capture: RawPerformanceCaptureV1) -> None:
        assert [e.sequence_number for e in open_capture.events] == [0, 1]

    def test_original_timing_is_preserved(
        self, runtime_identity: RuntimeIdentityV1, capture_source: CaptureSourceV1, meter: MeterV1
    ) -> None:
        # Nothing rounds, quantizes, or normalizes a timestamp.
        events = (make_event(0, time_ns=1_234_567_891), make_event(1, time_ns=1_234_567_899))
        capture = _capture(runtime_identity, capture_source, meter, events)
        assert [e.capture_time_ns for e in capture.events] == [1_234_567_891, 1_234_567_899]

    def test_duplicate_sequence_numbers_fail(
        self, runtime_identity: RuntimeIdentityV1, capture_source: CaptureSourceV1, meter: MeterV1
    ) -> None:
        events = (make_event(0), dataclasses.replace(make_event(1), sequence_number=0))
        with pytest.raises(PerformanceContractError, match="strictly increase"):
            _capture(runtime_identity, capture_source, meter, events)

    def test_decreasing_sequence_numbers_fail(
        self, runtime_identity: RuntimeIdentityV1, capture_source: CaptureSourceV1, meter: MeterV1
    ) -> None:
        events = (make_event(5), make_event(1))
        with pytest.raises(PerformanceContractError, match="strictly increase"):
            _capture(runtime_identity, capture_source, meter, events)

    def test_decreasing_timestamps_fail(
        self, runtime_identity: RuntimeIdentityV1, capture_source: CaptureSourceV1, meter: MeterV1
    ) -> None:
        events = (make_event(0, time_ns=2_000), make_event(1, time_ns=1_000))
        with pytest.raises(PerformanceContractError, match="must not decrease"):
            _capture(runtime_identity, capture_source, meter, events)

    def test_equal_timestamps_are_permitted(
        self, runtime_identity: RuntimeIdentityV1, capture_source: CaptureSourceV1, meter: MeterV1
    ) -> None:
        # Two events can genuinely share a timestamp at clock resolution.
        events = (make_event(0, time_ns=1_000), make_event(1, time_ns=1_000))
        assert _capture(runtime_identity, capture_source, meter, events).event_count == 2

    def test_duplicate_event_ids_fail(
        self, runtime_identity: RuntimeIdentityV1, capture_source: CaptureSourceV1, meter: MeterV1
    ) -> None:
        events = (make_event(0), dataclasses.replace(make_event(1), event_id="evt-0000"))
        with pytest.raises(PerformanceContractError, match="event_id"):
            _capture(runtime_identity, capture_source, meter, events)


class TestClosure:
    def test_a_new_capture_is_open(self, open_capture: RawPerformanceCaptureV1) -> None:
        assert open_capture.completion_state is CaptureCompletionState.IN_PROGRESS
        assert open_capture.is_closed is False

    def test_an_open_capture_must_not_have_an_end_time(
        self, open_capture: RawPerformanceCaptureV1
    ) -> None:
        with pytest.raises(PerformanceContractError, match="must not have ended_at"):
            dataclasses.replace(open_capture, ended_at=T1)

    def test_a_closed_capture_requires_an_end_time(
        self, open_capture: RawPerformanceCaptureV1
    ) -> None:
        with pytest.raises(PerformanceContractError, match="requires ended_at"):
            dataclasses.replace(
                open_capture, completion_state=CaptureCompletionState.COMPLETE
            )

    def test_completion_requires_explicit_closure(
        self, open_capture: RawPerformanceCaptureV1
    ) -> None:
        closed = close_capture(open_capture, ended_at=T1)
        assert closed.is_closed is True
        assert closed.ended_at == T1

    def test_closing_twice_is_refused(self, closed_capture: RawPerformanceCaptureV1) -> None:
        # A late or duplicated stop must not rewrite how a take ended.
        with pytest.raises(PerformanceContractError, match="already closed"):
            close_capture(closed_capture, ended_at=T1)

    def test_closing_with_a_non_terminal_state_is_refused(
        self, open_capture: RawPerformanceCaptureV1
    ) -> None:
        with pytest.raises(PerformanceContractError, match="terminal completion state"):
            close_capture(
                open_capture,
                ended_at=T1,
                completion_state=CaptureCompletionState.IN_PROGRESS,
            )

    @pytest.mark.parametrize(
        "state",
        [
            CaptureCompletionState.COMPLETE,
            CaptureCompletionState.INTERRUPTED,
            CaptureCompletionState.FAILED,
            CaptureCompletionState.CANCELLED,
        ],
    )
    def test_every_terminal_state_is_representable(
        self, open_capture: RawPerformanceCaptureV1, state: CaptureCompletionState
    ) -> None:
        assert close_capture(open_capture, ended_at=T1, completion_state=state).is_closed


class TestImmutability:
    def test_a_closed_capture_cannot_accept_events(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        with pytest.raises(PerformanceContractError, match="cannot accept more events"):
            append_events(closed_capture, (make_event(9),))

    def test_appending_returns_a_new_record(
        self, open_capture: RawPerformanceCaptureV1
    ) -> None:
        grown = append_events(open_capture, (make_event(2),))
        assert grown.event_count == 3
        assert open_capture.event_count == 2

    def test_capture_fields_cannot_be_assigned(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            closed_capture.capture_id = "other"  # type: ignore[misc]

    def test_events_are_a_tuple_not_a_list(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        # A list would let a consumer mutate an "immutable" record in place.
        assert isinstance(closed_capture.events, tuple)


class TestInterruption:
    def test_interruption_is_explicit(
        self, open_capture: RawPerformanceCaptureV1, crash_fault: RuntimeFaultV1
    ) -> None:
        interrupted = mark_capture_interrupted(open_capture, ended_at=T1, fault=crash_fault)
        assert interrupted.completion_state is CaptureCompletionState.INTERRUPTED

    def test_interruption_preserves_accepted_events(
        self, open_capture: RawPerformanceCaptureV1, crash_fault: RuntimeFaultV1
    ) -> None:
        interrupted = mark_capture_interrupted(open_capture, ended_at=T1, fault=crash_fault)
        assert interrupted.event_count == open_capture.event_count

    def test_faults_stay_attached_to_the_capture(
        self, open_capture: RawPerformanceCaptureV1, crash_fault: RuntimeFaultV1
    ) -> None:
        interrupted = mark_capture_interrupted(open_capture, ended_at=T1, fault=crash_fault)
        assert interrupted.faults == (crash_fault,)

    def test_interruption_can_carry_a_warning(
        self, open_capture: RawPerformanceCaptureV1, crash_fault: RuntimeFaultV1
    ) -> None:
        interrupted = mark_capture_interrupted(
            open_capture, ended_at=T1, fault=crash_fault, warning="2 notes still sounding"
        )
        assert interrupted.warnings == ("2 notes still sounding",)


class TestPartialAndMissingData:
    def test_missing_note_offs_are_visible(
        self, runtime_identity: RuntimeIdentityV1, capture_source: CaptureSourceV1, meter: MeterV1
    ) -> None:
        events = (
            make_event(0, MidiEventType.NOTE_ON, note=52, velocity=90),
            make_event(1, MidiEventType.NOTE_ON, note=57, velocity=90),
            make_event(2, MidiEventType.NOTE_OFF, note=52, velocity=0),
        )
        capture = close_capture(
            _capture(runtime_identity, capture_source, meter, events), ended_at=T1
        )
        assert detect_missing_note_offs(capture) == ((0, 57),)

    def test_note_on_with_zero_velocity_counts_as_note_off(
        self, runtime_identity: RuntimeIdentityV1, capture_source: CaptureSourceV1, meter: MeterV1
    ) -> None:
        # MIDI convention; treating it otherwise would report a phantom stuck note.
        events = (
            make_event(0, MidiEventType.NOTE_ON, note=52, velocity=90),
            make_event(1, MidiEventType.NOTE_ON, note=52, velocity=0),
        )
        capture = close_capture(
            _capture(runtime_identity, capture_source, meter, events), ended_at=T1
        )
        assert detect_missing_note_offs(capture) == ()

    def test_repeated_note_ons_are_not_reconciled(
        self, runtime_identity: RuntimeIdentityV1, capture_source: CaptureSourceV1, meter: MeterV1
    ) -> None:
        # Reconciling them would be interpretation, not observation.
        events = (
            make_event(0, MidiEventType.NOTE_ON, note=52, velocity=90),
            make_event(1, MidiEventType.NOTE_ON, note=52, velocity=90),
            make_event(2, MidiEventType.NOTE_OFF, note=52, velocity=0),
        )
        capture = close_capture(
            _capture(runtime_identity, capture_source, meter, events), ended_at=T1
        )
        assert detect_missing_note_offs(capture) == ((0, 52),)

    def test_partial_capture_remains_readable(
        self,
        runtime_identity: RuntimeIdentityV1,
        capture_source: CaptureSourceV1,
        meter: MeterV1,
        crash_fault: RuntimeFaultV1,
    ) -> None:
        events = (make_event(0, MidiEventType.NOTE_ON, note=55, velocity=101),)
        capture = mark_capture_interrupted(
            _capture(runtime_identity, capture_source, meter, events),
            ended_at=T1,
            fault=crash_fault,
        )
        assert capture.event_count == 1
        assert capture.faults


class TestSourceStringEvidence:
    def test_supplied_string_identity_is_preserved(
        self,
        runtime_identity: RuntimeIdentityV1,
        per_string_source: CaptureSourceV1,
        meter: MeterV1,
    ) -> None:
        events = (
            make_event(0, MidiEventType.NOTE_ON, note=40, velocity=100, source_string=0),
            make_event(1, MidiEventType.NOTE_ON, note=47, velocity=98, source_string=1),
        )
        capture = _capture(runtime_identity, per_string_source, meter, events)
        assert [e.source_string for e in capture.events] == [0, 1]

    def test_absent_string_identity_stays_unresolved(
        self, open_capture: RawPerformanceCaptureV1
    ) -> None:
        # Nothing infers a string from channel, pitch, or anything else.
        assert all(e.source_string is None for e in open_capture.events)

    def test_normalization_never_derives_a_string_from_channel(self) -> None:
        event = normalize_midi_event(
            event_id="evt-1",
            sequence_number=0,
            event_type=MidiEventType.NOTE_ON,
            capture_time_ns=0,
            channel=3,
            source_port="p",
            source_device="d",
            note=60,
            velocity=90,
        )
        assert event.source_string is None

    def test_observation_counts_unresolved_string_events(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        observation = derive_performance_observation(
            closed_capture,
            observation_id="obs-1",
            observed_at=T1,
            runtime_state=RuntimeState.READY,
        )
        assert observation.unresolved_string_event_count == 2
        assert observation.source_strings_observed == ()


class TestQuantizationNeverOverwritesRawCapture:
    def test_a_derived_record_is_a_new_object(
        self, closed_capture: RawPerformanceCaptureV1
    ) -> None:
        original_times = [e.capture_time_ns for e in closed_capture.events]
        derived = dataclasses.replace(
            closed_capture,
            capture_id="capture-1-quantized",
            events=tuple(
                dataclasses.replace(e, capture_time_ns=(e.capture_time_ns // 1000) * 1000)
                for e in closed_capture.events
            ),
        )
        assert [e.capture_time_ns for e in closed_capture.events] == original_times
        assert derived.capture_id != closed_capture.capture_id
