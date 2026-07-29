"""Session, track, transport, loop, and metronome contracts.

The first proof is bounded to one MIDI track and one synth (DO-006 §3.2). That bound
is expressed here as a validated invariant rather than left to reviewer discipline,
because "just one more track" is how a Performance Studio becomes a DAW.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from master_all_strings.performance.contracts.errors import (
    PerformanceContractError,
    require_bool,
    require_identifier,
    require_nonnegative_int,
    require_positive_int,
    require_range,
    require_schema_version,
    require_tuple,
    require_unique,
)

# The first-target bound from DO-006 §3.2. Raising this is a product decision that
# belongs in a Dev Order, not an implementation detail.
MAX_TRACKS_FIRST_TARGET = 1

# Tempo bounds. Wide enough for any musical use, narrow enough that a corrupt value
# fails at construction rather than producing an unusable session.
MIN_TEMPO_BPM = 20.0
MAX_TEMPO_BPM = 400.0


class TransportMode(StrEnum):
    """What the transport is doing."""

    STOPPED = "stopped"
    PLAYING = "playing"
    RECORDING = "recording"


class SessionState(StrEnum):
    """Lifecycle of a prepared performance session."""

    UNPREPARED = "unprepared"
    PREPARING = "preparing"
    PREPARED = "prepared"
    ACTIVE = "active"
    CLOSED = "closed"
    FAILED = "failed"


class TrackKind(StrEnum):
    """What kind of material a track carries.

    Only ``MIDI`` is in scope for the first proof. ``AUDIO`` exists so the enum does
    not have to change when Stage 6 adds monitoring, but a config declaring it is
    rejected until that work is authorized.
    """

    MIDI = "midi"
    AUDIO = "audio"


@dataclass(frozen=True)
class MeterV1:
    """A time signature."""

    schema_version: str
    beats_per_bar: int
    beat_unit: int

    SCHEMA_VERSION = "1.0.0"
    # Powers of two: a beat unit of 5 or 7 is not a meaningful note value.
    SUPPORTED_BEAT_UNITS = (1, 2, 4, 8, 16, 32)

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_range(self.beats_per_bar, "beats_per_bar", 1, 64)
        if self.beat_unit not in self.SUPPORTED_BEAT_UNITS:
            raise PerformanceContractError(
                f"beat_unit must be one of {list(self.SUPPORTED_BEAT_UNITS)}"
            )


@dataclass(frozen=True)
class LoopRegionV1:
    """An optional loop region, in ticks."""

    schema_version: str
    start_tick: int
    end_tick: int
    enabled: bool

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_nonnegative_int(self.start_tick, "start_tick")
        require_nonnegative_int(self.end_tick, "end_tick")
        require_bool(self.enabled, "enabled")
        if self.end_tick <= self.start_tick:
            raise PerformanceContractError("end_tick must be greater than start_tick")


@dataclass(frozen=True)
class MetronomeConfigV1:
    """Optional metronome and count-in."""

    schema_version: str
    enabled: bool
    count_in_bars: int
    level: float

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_bool(self.enabled, "enabled")
        require_nonnegative_int(self.count_in_bars, "count_in_bars")
        if isinstance(self.level, bool) or not isinstance(self.level, (int, float)):
            raise PerformanceContractError("level must be a number")
        if not 0.0 <= float(self.level) <= 1.0:
            raise PerformanceContractError("level must be between 0.0 and 1.0")


@dataclass(frozen=True)
class TransportStateV1:
    """Transport position and tempo context."""

    schema_version: str
    mode: TransportMode
    position_tick: int
    tempo_bpm: float
    meter: MeterV1
    ticks_per_quarter: int
    loop: LoopRegionV1 | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        if not isinstance(self.mode, TransportMode):
            raise PerformanceContractError("mode must be a TransportMode")
        require_nonnegative_int(self.position_tick, "position_tick")
        if isinstance(self.tempo_bpm, bool) or not isinstance(self.tempo_bpm, (int, float)):
            raise PerformanceContractError("tempo_bpm must be a number")
        if not MIN_TEMPO_BPM <= float(self.tempo_bpm) <= MAX_TEMPO_BPM:
            raise PerformanceContractError(
                f"tempo_bpm must be between {MIN_TEMPO_BPM} and {MAX_TEMPO_BPM}"
            )
        if not isinstance(self.meter, MeterV1):
            raise PerformanceContractError("meter must be a MeterV1")
        require_positive_int(self.ticks_per_quarter, "ticks_per_quarter")
        if self.loop is not None and not isinstance(self.loop, LoopRegionV1):
            raise PerformanceContractError("loop must be a LoopRegionV1 or None")


@dataclass(frozen=True)
class PerformanceTrackConfigV1:
    """One track in a prepared session."""

    schema_version: str
    track_id: str
    name: str
    kind: TrackKind
    midi_input: str | None
    synth_id: str | None
    record_armed: bool
    channel: int | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.track_id, "track_id")
        require_identifier(self.name, "name")
        if not isinstance(self.kind, TrackKind):
            raise PerformanceContractError("kind must be a TrackKind")
        require_bool(self.record_armed, "record_armed")
        if self.kind is TrackKind.AUDIO:
            raise PerformanceContractError(
                "audio tracks are out of scope for the first target (DO-006 §3.2)"
            )
        if self.midi_input is not None:
            require_identifier(self.midi_input, "midi_input")
        if self.synth_id is not None:
            require_identifier(self.synth_id, "synth_id")
        if self.channel is not None:
            require_range(self.channel, "channel", 0, 15)
        # An armed MIDI track with no input silently records nothing, which is the
        # worst possible outcome of a take: the player believes it worked.
        if self.record_armed and self.midi_input is None:
            raise PerformanceContractError("a record-armed track must declare a midi_input")


@dataclass(frozen=True)
class PerformanceSessionConfigV1:
    """A prepared session: what to create before the player touches anything."""

    schema_version: str
    session_id: str
    runtime_id: str
    tracks: tuple[PerformanceTrackConfigV1, ...]
    transport: TransportStateV1
    metronome: MetronomeConfigV1
    template_id: str

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.session_id, "session_id")
        require_identifier(self.runtime_id, "runtime_id")
        require_identifier(self.template_id, "template_id")
        require_tuple(self.tracks, "tracks")
        if not self.tracks:
            raise PerformanceContractError("tracks must declare at least one track")
        for track in self.tracks:
            if not isinstance(track, PerformanceTrackConfigV1):
                raise PerformanceContractError("tracks must contain PerformanceTrackConfigV1")
        require_unique([t.track_id for t in self.tracks], "track_id")
        if len(self.tracks) > MAX_TRACKS_FIRST_TARGET:
            raise PerformanceContractError(
                f"the first target permits at most {MAX_TRACKS_FIRST_TARGET} track(s); "
                "multitrack is out of scope (DO-006 §3.2)"
            )
        if not isinstance(self.transport, TransportStateV1):
            raise PerformanceContractError("transport must be a TransportStateV1")
        if not isinstance(self.metronome, MetronomeConfigV1):
            raise PerformanceContractError("metronome must be a MetronomeConfigV1")


@dataclass(frozen=True)
class PerformanceSessionStateV1:
    """What the session is doing right now."""

    schema_version: str
    session_id: str
    runtime_id: str
    state: SessionState
    transport: TransportStateV1
    armed_track_ids: tuple[str, ...] = ()
    active_capture_id: str | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.session_id, "session_id")
        require_identifier(self.runtime_id, "runtime_id")
        if not isinstance(self.state, SessionState):
            raise PerformanceContractError("state must be a SessionState")
        if not isinstance(self.transport, TransportStateV1):
            raise PerformanceContractError("transport must be a TransportStateV1")
        require_tuple(self.armed_track_ids, "armed_track_ids")
        for track_id in self.armed_track_ids:
            require_identifier(track_id, "armed_track_ids entry")
        require_unique(self.armed_track_ids, "armed_track_ids")
        if self.active_capture_id is not None:
            require_identifier(self.active_capture_id, "active_capture_id")
        # Recording without an active capture would mean events are being produced
        # with nowhere to land.
        if self.transport.mode is TransportMode.RECORDING and self.active_capture_id is None:
            raise PerformanceContractError(
                "transport mode RECORDING requires an active_capture_id"
            )
