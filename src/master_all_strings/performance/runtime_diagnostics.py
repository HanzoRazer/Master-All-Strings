"""Runtime readiness aggregation and diagnostic rendering.

Read-only throughout. Nothing here starts, stops, installs, or reconfigures anything;
these functions turn what a runtime reports into something a caller or an engineer
can act on.
"""

from __future__ import annotations

from master_all_strings.performance.contracts.runtime import (
    RuntimeCapability,
    RuntimeCapabilitySetV1,
    RuntimeDiagnosticsV1,
    RuntimeHealthV1,
    RuntimeIdentityV1,
    RuntimeReadinessV1,
    RuntimeState,
    SubsystemState,
)

_STATE_MARK = {
    SubsystemState.READY: "ok",
    SubsystemState.UNKNOWN: "??",
    SubsystemState.UNAVAILABLE: "--",
    SubsystemState.FAULTED: "XX",
}


def check_runtime_readiness(health: RuntimeHealthV1) -> RuntimeReadinessV1:
    """Aggregate per-subsystem health into a readiness verdict.

    Ready means every subsystem is ready *and* the runtime state says so. Both are
    required: a runtime can report healthy subsystems while still starting up, and
    treating that as ready is how a caller ends up issuing commands too early.
    """
    blocking = health.blocking_subsystems()
    ready = not blocking and health.state is RuntimeState.READY
    return RuntimeReadinessV1(
        schema_version=RuntimeReadinessV1.SCHEMA_VERSION,
        runtime_id=health.runtime_id,
        ready=ready,
        health=health,
        blocking_subsystems=blocking,
    )


def collect_runtime_diagnostics(
    *,
    identity: RuntimeIdentityV1,
    capabilities: RuntimeCapabilitySetV1,
    health: RuntimeHealthV1,
    collected_at: str,
    notes: tuple[str, ...] = (),
) -> RuntimeDiagnosticsV1:
    """Assemble a diagnostic snapshot.

    Adds a note when the runtime version is unresolved, because an unknown version is
    the condition under which every other reading becomes less trustworthy — and it is
    a real state for Ardour 9.7, whose OSC surface exposes no version (GAP-002).
    """
    derived = list(notes)
    if identity.reported_version is None:
        derived.append("runtime version is unresolved; version-dependent behavior is unverified")
    if not capabilities.supports(RuntimeCapability.PANIC):
        derived.append("runtime does not report the panic capability")
    return RuntimeDiagnosticsV1(
        schema_version=RuntimeDiagnosticsV1.SCHEMA_VERSION,
        runtime_id=identity.runtime_id,
        collected_at=collected_at,
        identity=identity,
        capabilities=capabilities,
        health=health,
        notes=tuple(derived),
    )


def render_diagnostic_report(diagnostics: RuntimeDiagnosticsV1) -> str:
    """Render a diagnostic snapshot as plain text for a human.

    Deterministic: the same snapshot always renders identically, so a report can be
    diffed between runs.
    """
    identity = diagnostics.identity
    health = diagnostics.health
    version = identity.reported_version or "unresolved"
    supported = "yes" if identity.version_supported else "no"

    lines = [
        f"runtime          {identity.runtime_id} ({identity.runtime_kind.value})",
        f"version          {version} (policy {identity.version_policy}; supported: {supported})",
        f"collected_at     {diagnostics.collected_at}",
        f"state            {health.state.value}",
        "",
        "subsystems",
    ]
    for name in RuntimeHealthV1.SUBSYSTEM_FIELDS:
        state: SubsystemState = getattr(health, name)
        lines.append(f"  [{_STATE_MARK[state]}] {name:<14} {state.value}")

    lines.append("")
    capabilities = (
        ", ".join(c.value for c in diagnostics.capabilities.capabilities) or "none reported"
    )
    lines.append(f"capabilities     {capabilities}")

    if health.faults:
        lines.append("")
        lines.append("faults")
        for fault in health.faults:
            recoverable = "recoverable" if fault.recoverable else "unrecoverable"
            lines.append(
                f"  {fault.code.value} [{fault.subsystem}] {fault.detail} ({recoverable})"
            )

    if diagnostics.notes:
        lines.append("")
        lines.append("notes")
        lines.extend(f"  - {note}" for note in diagnostics.notes)

    return "\n".join(lines) + "\n"
