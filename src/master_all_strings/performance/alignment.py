"""Rule-ordered performance alignment; measurement, never judgment."""

from __future__ import annotations

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.score.musical_timeline import ticks_to_seconds
from master_all_strings.core.score.tempo import TempoChangeV1
from master_all_strings.performance.contracts.alignment import (
    AlignedPerformanceEventV1,
    AlignmentStatus,
    PerformanceAlignmentPolicyV1,
    PerformanceAlignmentResultV1,
)
from master_all_strings.performance.contracts.live_midi import (
    ObservedMidiNoteStatus,
    ObservedMidiNoteV1,
)


def align_performance(
    *,
    assignment_id: str,
    content_id: str,
    performance_session_id: str,
    expected: tuple[MusicalEvent, ...],
    observed: tuple[ObservedMidiNoteV1, ...],
    policy: PerformanceAlignmentPolicyV1,
    ticks_per_quarter: int,
    tempo_changes: tuple[TempoChangeV1, ...],
    repetition_count: int = 1,
) -> PerformanceAlignmentResultV1:
    remaining = set(range(len(observed)))
    rows = []
    missing = []
    for rep in range(repetition_count):
        for event in expected:
            expected_s = ticks_to_seconds(
                event.start_tick, ticks_per_quarter=ticks_per_quarter, tempo_changes=tempo_changes
            )
            candidates = []
            for i in remaining:
                note = observed[i]
                if note.repetition_index != rep or note.practice_onset_seconds is None:
                    continue
                delta = round((note.practice_onset_seconds - expected_s) * 1000)
                pitch = note.midi_note - event.midi_note
                if -policy.early_window_ms <= delta <= policy.late_window_ms and (
                    pitch == 0
                    or (
                        policy.allow_pitch_mismatch
                        and abs(pitch) <= policy.maximum_pitch_distance_semitones
                    )
                ):
                    candidates.append(
                        (pitch != 0, abs(delta), note.observed_event_id, i, delta, pitch)
                    )
            key = f"{event.event_id}@{rep}"
            if not candidates:
                missing.append(key)
                rows.append(
                    AlignedPerformanceEventV1(
                        AlignmentStatus.EXPECTED_NOT_OBSERVED,
                        event.event_id,
                        None,
                        rep,
                        expected_start_tick=event.start_tick,
                    )
                )
                continue
            _, _, _, i, delta, pitch = min(candidates)
            remaining.remove(i)
            note = observed[i]
            status = (
                AlignmentStatus.MATCHED_EXACT_PITCH
                if pitch == 0
                else AlignmentStatus.MATCHED_PITCH_DIFFERENCE
            )
            if note.status is ObservedMidiNoteStatus.UNMATCHED_NOTE_ON:
                status = AlignmentStatus.UNRESOLVED_CAPTURE
            rows.append(
                AlignedPerformanceEventV1(
                    status,
                    event.event_id,
                    note.observed_event_id,
                    rep,
                    delta,
                    pitch,
                    expected_start_tick=event.start_tick,
                    observed_estimated_tick=note.estimated_start_tick,
                )
            )
    extra = []
    for i in sorted(remaining):
        note = observed[i]
        extra.append(note.observed_event_id)
        rows.append(
            AlignedPerformanceEventV1(
                AlignmentStatus.OBSERVED_NOT_EXPECTED,
                None,
                note.observed_event_id,
                note.repetition_index,
            )
        )
    return PerformanceAlignmentResultV1(
        "1.0.0",
        assignment_id,
        content_id,
        performance_session_id,
        policy,
        tuple(rows),
        tuple(missing),
        tuple(extra),
    )
