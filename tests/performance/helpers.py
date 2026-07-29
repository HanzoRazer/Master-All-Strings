"""Shared constants and builders for Performance Engine tests.

Kept out of ``conftest.py`` so test modules can import them directly; the repository
does not use ``__init__.py`` under ``tests/``, so a relative import is unavailable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from master_all_strings.performance.capture_normalization import normalize_midi_event
from master_all_strings.performance.contracts.capture import (
    CapturedMidiEventV1,
    MidiEventType,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RESOURCE_DIR = REPO_ROOT / "resources" / "performance"
SCHEMA_DIR = RESOURCE_DIR / "schema"
EXAMPLE_DIR = RESOURCE_DIR / "examples"

T0 = "2026-07-24T10:00:00Z"
T1 = "2026-07-24T10:00:12Z"


def make_event(
    sequence: int,
    event_type: MidiEventType = MidiEventType.NOTE_ON,
    *,
    time_ns: int | None = None,
    note: int | None = 64,
    velocity: int | None = 96,
    channel: int = 0,
    source_string: int | None = None,
    controller: int | None = None,
    controller_value: int | None = None,
    pitch_bend: int | None = None,
) -> CapturedMidiEventV1:
    """Build a captured event, defaulting to a plain note-on."""
    if event_type not in (MidiEventType.NOTE_ON, MidiEventType.NOTE_OFF):
        note = None
        velocity = None
    return normalize_midi_event(
        event_id=f"evt-{sequence:04d}",
        sequence_number=sequence,
        event_type=event_type,
        capture_time_ns=sequence * 100_000_000 if time_ns is None else time_ns,
        channel=channel,
        source_port="port-0",
        source_device="generic-midi-guitar",
        note=note,
        velocity=velocity,
        controller=controller,
        controller_value=controller_value,
        pitch_bend=pitch_bend,
        source_string=source_string,
    )


def load_json(path: Path) -> Any:
    """Read a JSON document from ``path``."""
    return json.loads(path.read_text(encoding="utf-8"))
