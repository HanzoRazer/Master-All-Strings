"""Builders for prepared sessions.

Convenience only: every builder produces a validated contract, so nothing here can
construct a session the contracts would reject. Builders take explicit arguments and
read no clock, so a session built twice from the same inputs is identical.
"""

from __future__ import annotations

from master_all_strings.performance.contracts.session import (
    LoopRegionV1,
    MeterV1,
    MetronomeConfigV1,
    PerformanceSessionConfigV1,
    PerformanceTrackConfigV1,
    TrackKind,
    TransportMode,
    TransportStateV1,
)

DEFAULT_TICKS_PER_QUARTER = 960
DEFAULT_TEMPO_BPM = 120.0
DEFAULT_TEMPLATE_ID = "single-midi-track-v1"


def build_meter(beats_per_bar: int = 4, beat_unit: int = 4) -> MeterV1:
    """Build a validated meter."""
    return MeterV1(
        schema_version=MeterV1.SCHEMA_VERSION,
        beats_per_bar=beats_per_bar,
        beat_unit=beat_unit,
    )


def build_loop_region(start_tick: int, end_tick: int, *, enabled: bool = True) -> LoopRegionV1:
    """Build a validated loop region."""
    return LoopRegionV1(
        schema_version=LoopRegionV1.SCHEMA_VERSION,
        start_tick=start_tick,
        end_tick=end_tick,
        enabled=enabled,
    )


def build_metronome_config(
    *, enabled: bool = False, count_in_bars: int = 0, level: float = 0.5
) -> MetronomeConfigV1:
    """Build a validated metronome configuration."""
    return MetronomeConfigV1(
        schema_version=MetronomeConfigV1.SCHEMA_VERSION,
        enabled=enabled,
        count_in_bars=count_in_bars,
        level=level,
    )


def build_transport_state(
    *,
    mode: TransportMode = TransportMode.STOPPED,
    position_tick: int = 0,
    tempo_bpm: float = DEFAULT_TEMPO_BPM,
    meter: MeterV1 | None = None,
    ticks_per_quarter: int = DEFAULT_TICKS_PER_QUARTER,
    loop: LoopRegionV1 | None = None,
) -> TransportStateV1:
    """Build a validated transport state."""
    return TransportStateV1(
        schema_version=TransportStateV1.SCHEMA_VERSION,
        mode=mode,
        position_tick=position_tick,
        tempo_bpm=tempo_bpm,
        meter=meter or build_meter(),
        ticks_per_quarter=ticks_per_quarter,
        loop=loop,
    )


def build_single_track_session(
    *,
    session_id: str,
    runtime_id: str,
    midi_input: str,
    synth_id: str,
    track_id: str = "track-1",
    track_name: str = "Guitar MIDI",
    channel: int | None = 0,
    record_armed: bool = True,
    transport: TransportStateV1 | None = None,
    metronome: MetronomeConfigV1 | None = None,
    template_id: str = DEFAULT_TEMPLATE_ID,
) -> PerformanceSessionConfigV1:
    """Build the one-track, one-synth session of the DO-006 §3.2 first target.

    There is deliberately no ``build_multitrack_session``. Multitrack is out of scope,
    and the absence of a builder is the cheapest place to say so.
    """
    track = PerformanceTrackConfigV1(
        schema_version=PerformanceTrackConfigV1.SCHEMA_VERSION,
        track_id=track_id,
        name=track_name,
        kind=TrackKind.MIDI,
        midi_input=midi_input,
        synth_id=synth_id,
        record_armed=record_armed,
        channel=channel,
    )
    return PerformanceSessionConfigV1(
        schema_version=PerformanceSessionConfigV1.SCHEMA_VERSION,
        session_id=session_id,
        runtime_id=runtime_id,
        tracks=(track,),
        transport=transport or build_transport_state(),
        metronome=metronome or build_metronome_config(),
        template_id=template_id,
    )
