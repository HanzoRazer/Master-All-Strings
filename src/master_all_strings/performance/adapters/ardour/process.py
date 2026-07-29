"""Runtime-process inspection boundary for Ardour.

Read-only and test-double driven in this tranche. Nothing here starts a process,
installs anything, or changes a system setting; process control arrives at Commit 8
behind the same interface.

Version detection lives here rather than in the OSC client because Ardour 9.7 exposes
no version over OSC (GAP-002), so the only available route is out of band.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from master_all_strings.performance.adapters.ardour.models import is_supported_version


@dataclass(frozen=True)
class ProcessStatus:
    """What the adapter can observe about a runtime process."""

    running: bool
    pid: int | None
    reported_version: str | None

    @property
    def version_supported(self) -> bool:
        """Whether the reported version is within the supported policy range."""
        return is_supported_version(self.reported_version)


class ProcessInspector(Protocol):
    """Observes a runtime process. Implemented against the OS at Commit 8."""

    def status(self) -> ProcessStatus:
        """Return the current process status."""
        ...


class StaticProcessInspector:
    """A fixed inspector for tests and for modelling a known state."""

    def __init__(self, status: ProcessStatus) -> None:
        self._status = status

    def status(self) -> ProcessStatus:
        """Return the configured status."""
        return self._status
