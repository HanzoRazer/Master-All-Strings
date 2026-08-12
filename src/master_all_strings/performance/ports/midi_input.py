"""Transport-neutral live MIDI input boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from master_all_strings.performance.contracts.capture import CapturedMidiEventV1

MidiMessageListener = Callable[[CapturedMidiEventV1], None]
DisconnectListener = Callable[[str], None]


@runtime_checkable
class PerformanceMidiInputPort(Protocol):
    def devices(self) -> tuple[str, ...]: ...

    def connect(self, device_id: str) -> None: ...

    def disconnect(self) -> None: ...

    def subscribe(
        self,
        listener: MidiMessageListener,
        disconnect_listener: DisconnectListener,
    ) -> Callable[[], None]: ...
