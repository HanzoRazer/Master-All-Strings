"""Ardour adapter (scaffold).

**No public exports.** Nothing here is exported until the adapter passes the
conformance suite the fake runtime already satisfies. Import submodules directly if
you are working on the adapter itself.

Everything in this package is adapter-private. Ardour vocabulary lives here and
nowhere else, and may never cross ``PerformanceRuntimePort`` (ADR-0007 D2).

Status: scaffold only. No Ardour runtime has been built, started, or measured. See
``README.md`` in this package and
``docs/architecture/ARDOUR_ADAPTER_BOUNDARY.md``.
"""

from __future__ import annotations

__all__: list[str] = []
