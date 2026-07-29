"""A bounded OSC command surface for Ardour.

Deliberately **not** a general OSC bridge. It exposes a closed set of named
operations mapped to the OSC paths verified present in Ardour 9.7 source, and there
is no method that sends an arbitrary path. An open-ended bridge would make the
adapter boundary meaningless, because any caller could then reach anything Ardour
exposes.

No socket code lives here. Transport is injected as a Protocol, so the command
surface is fully testable without a network, a runtime, or a machine that has Ardour
on it. Building the wire layer is Commit 8 work.

Paths below were extracted from ``libs/surfaces/osc/osc.cc`` in the Ardour 9.7
source. Two required operations have no path at all — tempo/meter (GAP-001) and
version (GAP-002) — and are represented as absent rather than guessed at.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class OscOperation(StrEnum):
    """The closed set of operations this client may perform."""

    PLAY = "play"
    STOP = "stop"
    LOCATE = "locate"
    RECORD_ARM_TOGGLE = "record_arm_toggle"
    STRIP_RECORD_ARM = "strip_record_arm"
    PANIC = "panic"
    METRONOME_TOGGLE = "metronome_toggle"
    METRONOME_LEVEL = "metronome_level"
    LOOP_TOGGLE = "loop_toggle"
    SAVE = "save"
    SET_SURFACE_FEEDBACK = "set_surface_feedback"


# Verified present in Ardour 9.7 source. A path here is a claim about source code,
# not about behaviour: none has been exercised against a running Ardour.
OSC_PATHS: dict[OscOperation, str] = {
    OscOperation.PLAY: "/transport_play",
    OscOperation.STOP: "/transport_stop",
    OscOperation.LOCATE: "/locate",
    OscOperation.RECORD_ARM_TOGGLE: "/rec_enable_toggle",
    OscOperation.STRIP_RECORD_ARM: "/strip/recenable",
    OscOperation.PANIC: "/midi_panic",
    OscOperation.METRONOME_TOGGLE: "/toggle_click",
    OscOperation.METRONOME_LEVEL: "/click/level",
    OscOperation.LOOP_TOGGLE: "/loop_toggle",
    OscOperation.SAVE: "/save_state",
    OscOperation.SET_SURFACE_FEEDBACK: "/set_surface/feedback",
}

# Operations the product needs that Ardour 9.7's OSC surface does not provide.
# Named here so the absence is a fact in code, not a discovery someone makes later.
UNSUPPORTED_OPERATIONS: dict[str, str] = {
    "set_tempo": "GAP-001: Ardour 9.7 exposes no OSC tempo path",
    "set_meter": "GAP-001: Ardour 9.7 exposes no OSC meter path",
    "runtime_version": "GAP-002: Ardour 9.7 exposes no OSC version path",
}


class OscTransport(Protocol):
    """Sends one OSC message. Implemented by a real socket at Commit 8."""

    def send(self, path: str, args: tuple[object, ...]) -> None:
        """Send ``args`` to ``path``."""
        ...


class BoundedOscClient:
    """Sends only the operations in ``OSC_PATHS``.

    Refuses anything else, including the operations Ardour genuinely lacks — those
    fail with the gap that explains why, rather than with a generic error.
    """

    def __init__(self, transport: OscTransport) -> None:
        self._transport = transport
        self.sent: list[tuple[str, tuple[object, ...]]] = []

    def send(self, operation: OscOperation, *args: object) -> str:
        """Send a permitted operation and return the path used."""
        if not isinstance(operation, OscOperation):
            raise ValueError(f"unknown operation {operation!r}; the OSC surface is bounded")
        path = OSC_PATHS[operation]
        self._transport.send(path, args)
        self.sent.append((path, args))
        return path

    @staticmethod
    def why_unsupported(name: str) -> str | None:
        """Explain why a named operation is unavailable, or ``None`` if it is not known."""
        return UNSUPPORTED_OPERATIONS.get(name)
