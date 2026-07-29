"""Shared fixtures for Performance Engine tests.

Every fixture is deterministic: no clock is read, no randomness is used, and no test
depends on the environment. A capture built twice from these fixtures is identical,
which is what makes digest and serialization assertions meaningful.
"""

from __future__ import annotations

import pytest
from helpers import T0, T1, make_event  # noqa: F401

from master_all_strings.performance.capture_normalization import (
    build_raw_capture,
    close_capture,
)
from master_all_strings.performance.contracts.capture import (
    CaptureSourceV1,
    MidiEventType,
    RawPerformanceCaptureV1,
)
from master_all_strings.performance.contracts.runtime import (
    FaultCode,
    RuntimeFaultV1,
    RuntimeIdentityV1,
    RuntimeKind,
)
from master_all_strings.performance.contracts.session import MeterV1
from master_all_strings.performance.session_builder import build_meter


@pytest.fixture
def meter() -> MeterV1:
    return build_meter()


@pytest.fixture
def runtime_identity() -> RuntimeIdentityV1:
    return RuntimeIdentityV1(
        schema_version=RuntimeIdentityV1.SCHEMA_VERSION,
        runtime_id="fake",
        runtime_kind=RuntimeKind.FAKE,
        reported_version="1.0.0",
        version_policy="1.0.0",
        version_supported=True,
    )


@pytest.fixture
def capture_source() -> CaptureSourceV1:
    return CaptureSourceV1(
        schema_version=CaptureSourceV1.SCHEMA_VERSION,
        source_id="midi-in-0",
        port="port-0",
        device="generic-midi-guitar",
        supplies_string_identity=False,
    )


@pytest.fixture
def per_string_source() -> CaptureSourceV1:
    return CaptureSourceV1(
        schema_version=CaptureSourceV1.SCHEMA_VERSION,
        source_id="midi-in-0",
        port="port-0",
        device="divided-pickup-6",
        supplies_string_identity=True,
    )


@pytest.fixture
def open_capture(
    runtime_identity: RuntimeIdentityV1, capture_source: CaptureSourceV1, meter: MeterV1
) -> RawPerformanceCaptureV1:
    return build_raw_capture(
        capture_id="capture-1",
        session_id="session-001",
        runtime_identity=runtime_identity,
        source_identity=capture_source,
        started_at=T0,
        tempo_context=120.0,
        meter_context=meter,
        events=(
            make_event(0, MidiEventType.NOTE_ON, note=64, velocity=96),
            make_event(1, MidiEventType.NOTE_OFF, note=64, velocity=0),
        ),
        provenance=(("fixture", "open_capture"),),
    )


@pytest.fixture
def closed_capture(open_capture: RawPerformanceCaptureV1) -> RawPerformanceCaptureV1:
    return close_capture(open_capture, ended_at=T1)


@pytest.fixture
def crash_fault() -> RuntimeFaultV1:
    return RuntimeFaultV1(
        schema_version=RuntimeFaultV1.SCHEMA_VERSION,
        fault_id="fault-0001",
        code=FaultCode.RUNTIME_CRASHED,
        subsystem="process",
        detail="runtime process exited during capture",
        occurred_at="2026-07-24T10:00:09Z",
        recoverable=False,
    )
