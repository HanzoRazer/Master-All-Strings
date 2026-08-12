"""Deterministic performance-session evidence assembly and export."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from master_all_strings.performance.contracts.alignment import PerformanceAlignmentResultV1
from master_all_strings.performance.contracts.capture import RawPerformanceCaptureV1
from master_all_strings.performance.contracts.live_midi import ObservedMidiNoteV1
from master_all_strings.performance.contracts.session_evidence import (
    PerformanceProvenanceV1,
    PerformanceSessionEvidenceV1,
)
from master_all_strings.performance.export import to_dict


def compute_performance_evidence_digest(
    capture: RawPerformanceCaptureV1,
    observed: tuple[ObservedMidiNoteV1, ...],
    alignment: PerformanceAlignmentResultV1,
) -> str:
    semantic = {
        "raw_capture": to_dict(capture),
        "observed": [to_dict(n) for n in observed],
        "alignment": to_dict(alignment),
    }
    payload = json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def export_performance_session(
    directory: Path,
    *,
    capture: RawPerformanceCaptureV1,
    observed: tuple[ObservedMidiNoteV1, ...],
    alignment: PerformanceAlignmentResultV1,
    assignment_id: str,
    content_id: str,
    provenance: PerformanceProvenanceV1,
) -> PerformanceSessionEvidenceV1:
    directory.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "raw_capture.json": to_dict(capture),
        "observed_events.json": [to_dict(note) for note in observed],
        "alignment.json": to_dict(alignment),
        "provenance.json": to_dict(provenance),
    }
    for name, payload in artifacts.items():
        (directory / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    manifest = PerformanceSessionEvidenceV1(
        "1.0.0",
        assignment_id,
        content_id,
        alignment.performance_session_id,
        capture.capture_id,
        capture.completion_state,
        "raw_capture.json",
        "observed_events.json",
        "alignment.json",
        capture.source_identity.source_id,
        provenance,
        compute_performance_evidence_digest(capture, observed, alignment),
    )
    (directory / "manifest.json").write_text(
        json.dumps(to_dict(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return replace(manifest)
