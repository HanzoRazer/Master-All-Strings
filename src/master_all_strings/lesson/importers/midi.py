"""MIDI → LessonAssignmentV1 import adapter.

MIDI remains an import format. This module never calls MSME, selects fingering,
infers difficulty, or creates screen positions.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

from master_all_strings.lesson.enums import (
    LessonContentFormat,
    LessonSourceType,
    OpenStringPreference,
)
from master_all_strings.lesson.errors import LessonValidationError
from master_all_strings.lesson.models import (
    LESSON_ASSIGNMENT_SCHEMA_ID,
    LESSON_ASSIGNMENT_SCHEMA_VERSION,
    LessonAssignmentV1,
    LessonIdentityV1,
    LessonInstructionV1,
    LessonMusicalContentV1,
    LessonPlaybackPolicyV1,
    LessonProvenanceV1,
    LessonSpatialGuidanceV1,
    SerializedCanonicalEventV1,
    SerializedMeterChangeV1,
    SerializedTempoChangeV1,
)

__all__ = [
    "MidiLessonImportResultV1",
    "MidiLessonImporter",
    "build_assignment_from_midi",
]


@dataclass(frozen=True)
class MidiLessonImportResultV1:
    """Result of importing a MIDI file into a portable assignment."""

    assignment: LessonAssignmentV1
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _RawNote:
    midi_note: int
    start_tick: int
    duration_ticks: int
    velocity: int
    channel: int


def build_assignment_from_midi(
    midi_bytes: bytes,
    *,
    assignment_id: str,
    content_id: str | None = None,
    title: str | None = None,
    source_name: str | None = None,
    created_by: str = "midi_importer",
    created_at_utc: str = "1970-01-01T00:00:00Z",
    instrument_profile_id: str = "guitar-standard-6",
    fingering_policy_id: str = "enumeration_v1",
    loop_enabled: bool = False,
    start_tick: int | None = None,
    end_tick: int | None = None,
    preferred_fret_min: int | None = None,
    preferred_fret_max: int | None = None,
) -> MidiLessonImportResultV1:
    """Create a valid LessonAssignmentV1 from local MIDI bytes."""

    return MidiLessonImporter().import_bytes(
        midi_bytes,
        assignment_id=assignment_id,
        content_id=content_id,
        title=title,
        source_name=source_name,
        created_by=created_by,
        created_at_utc=created_at_utc,
        instrument_profile_id=instrument_profile_id,
        fingering_policy_id=fingering_policy_id,
        loop_enabled=loop_enabled,
        start_tick=start_tick,
        end_tick=end_tick,
        preferred_fret_min=preferred_fret_min,
        preferred_fret_max=preferred_fret_max,
    )


class MidiLessonImporter:
    """Parse MVP-supported Standard MIDI File content into LessonAssignmentV1."""

    def import_path(
        self,
        path: str | Path,
        *,
        assignment_id: str,
        content_id: str | None = None,
        title: str | None = None,
        created_by: str = "midi_importer",
        created_at_utc: str = "1970-01-01T00:00:00Z",
        instrument_profile_id: str = "guitar-standard-6",
        fingering_policy_id: str = "enumeration_v1",
        loop_enabled: bool = False,
        start_tick: int | None = None,
        end_tick: int | None = None,
        preferred_fret_min: int | None = None,
        preferred_fret_max: int | None = None,
        open_string_preference: OpenStringPreference = OpenStringPreference.ALLOW,
    ) -> MidiLessonImportResultV1:
        file_path = Path(path)
        # Only the basename is portable provenance; absolute path never enters the
        # assignment as a required dependency.
        return self.import_bytes(
            file_path.read_bytes(),
            assignment_id=assignment_id,
            content_id=content_id,
            title=title or file_path.stem,
            source_name=file_path.name,
            created_by=created_by,
            created_at_utc=created_at_utc,
            instrument_profile_id=instrument_profile_id,
            fingering_policy_id=fingering_policy_id,
            loop_enabled=loop_enabled,
            start_tick=start_tick,
            end_tick=end_tick,
            preferred_fret_min=preferred_fret_min,
            preferred_fret_max=preferred_fret_max,
            open_string_preference=open_string_preference,
        )

    def import_bytes(
        self,
        midi_bytes: bytes,
        *,
        assignment_id: str,
        content_id: str | None = None,
        title: str | None = None,
        source_name: str | None = None,
        created_by: str = "midi_importer",
        created_at_utc: str = "1970-01-01T00:00:00Z",
        instrument_profile_id: str = "guitar-standard-6",
        fingering_policy_id: str = "enumeration_v1",
        loop_enabled: bool = False,
        start_tick: int | None = None,
        end_tick: int | None = None,
        preferred_fret_min: int | None = None,
        preferred_fret_max: int | None = None,
        open_string_preference: OpenStringPreference = OpenStringPreference.ALLOW,
    ) -> MidiLessonImportResultV1:
        parsed = _parse_smf(midi_bytes)
        digest = hashlib.sha256(midi_bytes).hexdigest()[:16]
        resolved_content_id = content_id or f"midi-{digest}"
        resolved_title = title or (source_name or "Imported MIDI")
        portable_source = Path(source_name).name if source_name else None

        events = tuple(
            SerializedCanonicalEventV1(
                event_id=f"ev-{index + 1}",
                midi_note=note.midi_note,
                start_tick=note.start_tick,
                duration_ticks=note.duration_ticks,
                velocity=note.velocity,
                cents_offset=0.0,
                voice_id=None,
            )
            for index, note in enumerate(parsed.notes)
        )
        if not events:
            raise LessonValidationError(
                "MIDI file contained no note events",
                code="missing_content",
            )

        assignment = LessonAssignmentV1(
            schema_id=LESSON_ASSIGNMENT_SCHEMA_ID,
            schema_version=LESSON_ASSIGNMENT_SCHEMA_VERSION,
            identity=LessonIdentityV1(
                assignment_id=assignment_id,
                content_id=resolved_content_id,
                title=resolved_title,
            ),
            musical_content=LessonMusicalContentV1(
                format=LessonContentFormat.CANONICAL_EVENTS,
                ticks_per_quarter=parsed.ticks_per_quarter,
                events=events,
                tempo_changes=parsed.tempo_changes,
                meter_changes=parsed.meter_changes,
            ),
            playback=LessonPlaybackPolicyV1(
                tempo_override=None,
                start_tick=start_tick,
                end_tick=end_tick,
                loop_enabled=loop_enabled,
            ),
            spatial_guidance=LessonSpatialGuidanceV1(
                instrument_profile_id=instrument_profile_id,
                fingering_policy_id=fingering_policy_id,
                preferred_fret_min=preferred_fret_min,
                preferred_fret_max=preferred_fret_max,
                open_string_preference=open_string_preference,
            ),
            instruction=LessonInstructionV1(),
            provenance=LessonProvenanceV1(
                created_by=created_by,
                created_at_utc=created_at_utc,
                source_type=LessonSourceType.MIDI_IMPORT,
                source_name=portable_source,
            ),
            routing=None,
        )
        return MidiLessonImportResultV1(assignment=assignment, warnings=parsed.warnings)


@dataclass(frozen=True)
class _ParsedSmf:
    ticks_per_quarter: int
    notes: tuple[_RawNote, ...]
    tempo_changes: tuple[SerializedTempoChangeV1, ...]
    meter_changes: tuple[SerializedMeterChangeV1, ...]
    warnings: tuple[str, ...]


def _parse_smf(data: bytes) -> _ParsedSmf:
    if len(data) < 14 or data[0:4] != b"MThd":
        raise LessonValidationError("not a Standard MIDI File", code="invalid_midi")
    header_len = struct.unpack(">I", data[4:8])[0]
    if header_len < 6:
        raise LessonValidationError("invalid MIDI header length", code="invalid_midi")
    fmt, ntrks, division = struct.unpack(">HHH", data[8:14])
    if division & 0x8000:
        raise LessonValidationError(
            "SMPTE time division is not supported",
            code="unsupported_midi",
        )
    ticks_per_quarter = division
    if ticks_per_quarter <= 0:
        raise LessonValidationError("invalid ticks_per_quarter", code="invalid_ppq")

    warnings: list[str] = []
    if fmt not in (0, 1):
        warnings.append(f"MIDI format {fmt} is partially supported; tracks are merged")

    offset = 8 + header_len
    track_events: list[tuple[int, int, bytes]] = []
    for _ in range(ntrks):
        if data[offset : offset + 4] != b"MTrk":
            raise LessonValidationError("missing MTrk chunk", code="invalid_midi")
        track_len = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
        track_data = data[offset + 8 : offset + 8 + track_len]
        offset += 8 + track_len
        track_events.extend(_parse_track(track_data, warnings))

    track_events.sort(key=lambda item: (item[0], item[1]))
    notes, tempo_changes, meter_changes = _collect_notes_and_meta(track_events, warnings)
    return _ParsedSmf(
        ticks_per_quarter=ticks_per_quarter,
        notes=tuple(notes),
        tempo_changes=tuple(tempo_changes),
        meter_changes=tuple(meter_changes),
        warnings=tuple(warnings),
    )


def _parse_track(track_data: bytes, warnings: list[str]) -> list[tuple[int, int, bytes]]:
    events: list[tuple[int, int, bytes]] = []
    pos = 0
    tick = 0
    running_status = 0
    order = 0
    while pos < len(track_data):
        delta, pos = _read_vlq(track_data, pos)
        tick += delta
        if pos >= len(track_data):
            break
        status = track_data[pos]
        if status & 0x80:
            pos += 1
            running_status = status
        else:
            status = running_status
            if status == 0:
                raise LessonValidationError("MIDI running status missing", code="invalid_midi")

        if status == 0xFF:
            if pos >= len(track_data):
                break
            meta_type = track_data[pos]
            pos += 1
            length, pos = _read_vlq(track_data, pos)
            payload = track_data[pos : pos + length]
            pos += length
            events.append((tick, order, bytes([0xFF, meta_type]) + payload))
            order += 1
            continue

        if status in (0xF0, 0xF7):
            length, pos = _read_vlq(track_data, pos)
            pos += length
            warnings.append("sysex event ignored")
            continue

        message = status & 0xF0
        if message in (0xC0, 0xD0):
            pos += 1
            warnings.append(f"unsupported MIDI message {message:#x} ignored")
            continue
        if message in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
            if pos + 1 >= len(track_data):
                break
            data1 = track_data[pos]
            data2 = track_data[pos + 1]
            pos += 2
            events.append((tick, order, bytes([status, data1, data2])))
            order += 1
            continue
        warnings.append(f"unknown MIDI status {status:#x} ignored")
        break
    return events


def _collect_notes_and_meta(
    events: list[tuple[int, int, bytes]],
    warnings: list[str],
) -> tuple[list[_RawNote], list[SerializedTempoChangeV1], list[SerializedMeterChangeV1]]:
    open_notes: dict[tuple[int, int], list[tuple[int, int]]] = {}
    notes: list[_RawNote] = []
    tempos: list[SerializedTempoChangeV1] = []
    meters: list[SerializedMeterChangeV1] = []

    for tick, _order, payload in events:
        if payload[0] == 0xFF:
            meta_type = payload[1]
            meta_data = payload[2:]
            if meta_type == 0x51 and len(meta_data) == 3:
                mpq = (meta_data[0] << 16) | (meta_data[1] << 8) | meta_data[2]
                if mpq > 0:
                    bpm = 60_000_000 / mpq
                    tempos.append(SerializedTempoChangeV1(tick=tick, tempo_bpm=bpm))
            elif meta_type == 0x58 and len(meta_data) >= 2:
                numerator = meta_data[0]
                denom_pow = meta_data[1]
                denominator = 2**denom_pow
                if denominator in (1, 2, 4, 8, 16, 32):
                    meters.append(
                        SerializedMeterChangeV1(
                            tick=tick,
                            numerator=numerator,
                            denominator=denominator,
                        )
                    )
            continue

        status = payload[0]
        message = status & 0xF0
        channel = status & 0x0F
        if message == 0x90 and payload[2] > 0:
            key = (channel, payload[1])
            open_notes.setdefault(key, []).append((tick, payload[2]))
        elif message in (0x80, 0x90):
            key = (channel, payload[1])
            stack = open_notes.get(key)
            if not stack:
                warnings.append(
                    f"note-off without note-on for channel {channel} note {payload[1]}"
                )
                continue
            start_tick, velocity = stack.pop(0)
            duration = tick - start_tick
            if duration <= 0:
                warnings.append("non-positive note duration ignored")
                continue
            notes.append(
                _RawNote(
                    midi_note=payload[1],
                    start_tick=start_tick,
                    duration_ticks=duration,
                    velocity=velocity,
                    channel=channel,
                )
            )
        else:
            warnings.append(f"unsupported channel message {message:#x} ignored")

    for (channel, note), stack in open_notes.items():
        if stack:
            warnings.append(
                f"missing note-off for channel {channel} note {note}; note omitted"
            )
    notes.sort(key=lambda item: (item.start_tick, item.channel, item.midi_note))
    return notes, tempos, meters


def _read_vlq(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if pos >= len(data):
            raise LessonValidationError("truncated variable-length quantity", code="invalid_midi")
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos
    raise LessonValidationError("variable-length quantity too long", code="invalid_midi")
