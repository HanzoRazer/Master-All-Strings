from __future__ import annotations

import json

import pytest

from master_all_strings.performance.contracts.alignment import (
    PerformanceAlignmentPolicyV1,
    PerformanceAlignmentResultV1,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.contracts.session_evidence import PerformanceProvenanceV1
from master_all_strings.performance.session_evidence import export_performance_session


def test_export_is_deterministic_and_complete(tmp_path, closed_capture):  # type: ignore[no-untyped-def]
    alignment = PerformanceAlignmentResultV1(
        "1.0.0", "a", "c", "session-001", PerformanceAlignmentPolicyV1(), (), (), ()
    )
    provenance = PerformanceProvenanceV1("mas", "0.1.0", "2026-08-12T10:00:00Z")
    one = export_performance_session(
        tmp_path / "one",
        capture=closed_capture,
        observed=(),
        alignment=alignment,
        assignment_id="a",
        content_id="c",
        provenance=provenance,
    )
    two = export_performance_session(
        tmp_path / "two",
        capture=closed_capture,
        observed=(),
        alignment=alignment,
        assignment_id="a",
        content_id="c",
        provenance=provenance,
    )
    assert one.evidence_digest == two.evidence_digest
    assert {p.name for p in (tmp_path / "one").iterdir()} == {
        "manifest.json",
        "raw_capture.json",
        "observed_events.json",
        "alignment.json",
        "provenance.json",
    }
    assert (
        json.loads((tmp_path / "one/manifest.json").read_text())["evidence_digest"]
        == one.evidence_digest
    )


def test_latency_compensation_is_not_authorized():
    with pytest.raises(PerformanceContractError, match="latency"):
        PerformanceProvenanceV1("mas", "1", "now", latency_compensation_ns=1)
