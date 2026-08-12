#!/usr/bin/env python3
# ruff: noqa: E402
"""Build a deterministic, transport-neutral DO-009 return-path artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from master_all_strings.core.musical_events import MusicalEvent  # noqa: E402
from master_all_strings.core.score.tempo import TempoChangeV1  # noqa: E402
from master_all_strings.performance.alignment import align_performance  # noqa: E402
from master_all_strings.performance.capture_normalization import (
    build_raw_capture,
    close_capture,
    normalize_midi_event,
)  # noqa: E402
from master_all_strings.performance.contracts.alignment import (
    PerformanceAlignmentPolicyV1,
)
from master_all_strings.performance.contracts.capture import (  # noqa: E402
    CapturedMidiEventV1,
    CaptureSourceV1,
    MidiEventType,
)
from master_all_strings.performance.contracts.runtime import (  # noqa: E402
    RuntimeIdentityV1,
    RuntimeKind,
)
from master_all_strings.performance.contracts.session import MeterV1  # noqa: E402
from master_all_strings.performance.contracts.session_evidence import (
    PerformanceProvenanceV1,
)
from master_all_strings.performance.note_pairing import pair_midi_notes  # noqa: E402
from master_all_strings.performance.session_evidence import (  # noqa: E402
    export_performance_session,
)
from master_all_strings.performance.transport_correlation import (
    PracticeTransportAnchorV1,
    locate_observed_notes,
)  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    expected = tuple(
        MusicalEvent(f"expected-{i}", pitch, i * 480, 480, 80)
        for i, pitch in enumerate((60, 62, 64))
    )
    raw: list[CapturedMidiEventV1] = []
    for i, (pitch, on) in enumerate(((60, 0), (63, 500_000_000), (67, 1_000_000_000))):
        raw.extend(
            (
                normalize_midi_event(
                    event_id=f"raw-{i}-on",
                    sequence_number=2 * i,
                    event_type=MidiEventType.NOTE_ON,
                    capture_time_ns=on,
                    channel=0,
                    source_port="fake",
                    source_device="deterministic-fake",
                    note=pitch,
                    velocity=90,
                ),
                normalize_midi_event(
                    event_id=f"raw-{i}-off",
                    sequence_number=2 * i + 1,
                    event_type=MidiEventType.NOTE_OFF,
                    capture_time_ns=on + 250_000_000,
                    channel=0,
                    source_port="fake",
                    source_device="deterministic-fake",
                    note=pitch,
                    velocity=0,
                ),
            )
        )
    capture = close_capture(
        build_raw_capture(
            capture_id="do009-capture",
            session_id="do009-session",
            runtime_identity=RuntimeIdentityV1(
                "1.0.0", "fake", RuntimeKind.FAKE, "1", "test", True
            ),
            source_identity=CaptureSourceV1("1.0.0", "fake", "fake", "deterministic-fake", False),
            started_at="2026-08-12T10:00:00Z",
            tempo_context=120,
            meter_context=MeterV1("1.0.0", 4, 4),
            events=tuple(raw),
        ),
        ended_at="2026-08-12T10:00:02Z",
    )
    paired = pair_midi_notes(capture, observed_id_factory=lambda i: f"observed-{i}")
    tempo = (TempoChangeV1("1.0.0", 0, 500000),)
    located = locate_observed_notes(
        paired.observed_notes,
        (PracticeTransportAnchorV1(0, 0, 1, 0, True),),
        ticks_per_quarter=480,
        tempo_changes=tempo,
    )
    alignment = align_performance(
        assignment_id="do009-assignment",
        content_id="do009-return-path",
        performance_session_id="do009-session",
        expected=expected,
        observed=located,
        policy=PerformanceAlignmentPolicyV1(),
        ticks_per_quarter=480,
        tempo_changes=tempo,
    )
    manifest = export_performance_session(
        a.output,
        capture=capture,
        observed=located,
        alignment=alignment,
        assignment_id="do009-assignment",
        content_id="do009-return-path",
        provenance=PerformanceProvenanceV1("master-all-strings", "0.1.0", "2026-08-12T10:00:02Z"),
    )
    print(
        json.dumps(
            {
                "evidence_digest": manifest.evidence_digest,
                "aligned": len(alignment.aligned_events),
                "statuses": [r.status.value for r in alignment.aligned_events],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
