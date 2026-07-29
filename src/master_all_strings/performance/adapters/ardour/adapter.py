"""The Ardour ``PerformanceRuntimePort`` implementation.

Not implemented. Per DO-006 §5.6 the adapter is written only after the fake adapter
and the contract suite are stable, and per ADR-0007 D3 no rung of the escalation
ladder has been exercised against a running Ardour.

Implementing this is Commit 8 (desktop spike) and Commit 9 (Raspberry Pi spike). The
scaffolding it will build on already exists: ``osc_client`` holds the bounded command
surface with its paths verified against Ardour 9.7 source, ``process`` holds the
version-detection boundary, and ``models`` holds the adapter-private types.

Two known gaps must be resolved before this can satisfy the conformance suite:
GAP-001 (no OSC tempo or meter) and GAP-002 (no OSC version). Both are recorded in
``docs/planning/ARDOUR_GAP_AUDIT.md`` with untested mitigations.
"""

from __future__ import annotations

NOT_IMPLEMENTED_REASON = (
    "The Ardour adapter is a scaffold. No Ardour runtime has been built, started, or "
    "measured, and no escalation rung has been exercised. See "
    "docs/planning/ARDOUR_GAP_AUDIT.md and docs/planning/ARDOUR_FORK_GATE.md."
)


class ArdourRuntimeNotImplementedError(NotImplementedError):
    """Raised when the Ardour adapter is used before it exists."""


def build_ardour_runtime() -> None:
    """Construct the Ardour runtime adapter.

    Always raises. A scaffold that silently returned a partly working object would be
    worse than one that refuses: a caller could believe it had a runtime.
    """
    raise ArdourRuntimeNotImplementedError(NOT_IMPLEMENTED_REASON)
