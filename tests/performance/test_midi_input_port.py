from __future__ import annotations

import pytest
from helpers import make_event

from master_all_strings.performance.adapters.fake_midi_input import FakeMidiInput
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.ports.midi_input import PerformanceMidiInputPort


def test_fake_input_conforms_and_emits_deterministically() -> None:
    events = (make_event(0), make_event(1))
    adapter = FakeMidiInput(events)
    received = []
    disconnected = []
    adapter.subscribe(received.append, disconnected.append)
    adapter.connect("fake-midi-input")

    adapter.emit_all()
    adapter.disconnect()

    assert isinstance(adapter, PerformanceMidiInputPort)
    assert received == list(events)
    assert disconnected == ["fake-midi-input"]


def test_unknown_device_and_unconnected_emission_fail_explicitly() -> None:
    adapter = FakeMidiInput()
    with pytest.raises(PerformanceContractError, match="unknown MIDI"):
        adapter.connect("missing")
    with pytest.raises(PerformanceContractError, match="connected and subscribed"):
        adapter.emit(make_event(0))


def test_unsubscribe_stops_delivery() -> None:
    adapter = FakeMidiInput()
    received = []
    unsubscribe = adapter.subscribe(received.append, lambda _: None)
    adapter.connect("fake-midi-input")
    unsubscribe()
    with pytest.raises(PerformanceContractError, match="connected and subscribed"):
        adapter.emit(make_event(0))
