"""Deterministic live-MIDI input adapter for tests and browser fallback."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from master_all_strings.performance.contracts.capture import CapturedMidiEventV1
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.ports.midi_input import (
    DisconnectListener,
    MidiMessageListener,
)


class FakeMidiInput:
    def __init__(
        self,
        events: Iterable[CapturedMidiEventV1] = (),
        *,
        device_id: str = "fake-midi-input",
    ) -> None:
        self._events = tuple(events)
        self._device_id = device_id
        self._connected = False
        self._listener: MidiMessageListener | None = None
        self._disconnect_listener: DisconnectListener | None = None

    def devices(self) -> tuple[str, ...]:
        return (self._device_id,)

    def connect(self, device_id: str) -> None:
        if device_id != self._device_id:
            raise PerformanceContractError(f"unknown MIDI input {device_id!r}")
        self._connected = True

    def disconnect(self) -> None:
        was_connected = self._connected
        self._connected = False
        if was_connected and self._disconnect_listener is not None:
            self._disconnect_listener(self._device_id)

    def subscribe(
        self,
        listener: MidiMessageListener,
        disconnect_listener: DisconnectListener,
    ) -> Callable[[], None]:
        self._listener = listener
        self._disconnect_listener = disconnect_listener

        def unsubscribe() -> None:
            self._listener = None
            self._disconnect_listener = None

        return unsubscribe

    def emit_all(self) -> None:
        if not self._connected or self._listener is None:
            raise PerformanceContractError("fake MIDI input must be connected and subscribed")
        for event in self._events:
            self._listener(event)

    def emit(self, event: CapturedMidiEventV1) -> None:
        if not self._connected or self._listener is None:
            raise PerformanceContractError("fake MIDI input must be connected and subscribed")
        self._listener(event)
