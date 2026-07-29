"""Importable entry points behind the performance CLI scripts.

Logic lives here rather than in ``scripts/`` so tests exercise it directly instead of
shelling out, following the ``governance.engine_boundaries`` precedent.

Both commands are strictly read-only. They validate, inspect, and render. Neither
installs a runtime, downloads a plugin, edits a system audio setting, executes a
shell command from configuration, or starts a real runtime process.
"""

from __future__ import annotations

import sys
from pathlib import Path

from master_all_strings.performance.adapters.fake_runtime import (
    FAKE_SYNTH_ID,
    FakeRuntime,
    build_fake_session,
)
from master_all_strings.performance.configuration import (
    EXAMPLE_DIR,
    load_runtime_config,
    load_synth_registry,
    validate_runtime_config,
)
from master_all_strings.performance.contracts.commands import (
    ArmTrackCommandV1,
    PrepareSessionCommandV1,
    SelectSynthCommandV1,
    StartRuntimeCommandV1,
)
from master_all_strings.performance.contracts.errors import PerformanceContractError
from master_all_strings.performance.runtime_diagnostics import render_diagnostic_report

DEFAULT_CONFIG = EXAMPLE_DIR / "pi_ardour_reference_v1.json"


def validate_main(argv: list[str] | None = None) -> int:
    """Validate a runtime configuration. Returns 0 when clean, 1 on any finding."""
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else DEFAULT_CONFIG

    try:
        config = load_runtime_config(path)
        registry = load_synth_registry()
    except PerformanceContractError as exc:
        print(f"invalid: {exc}")
        return 1

    problems = validate_runtime_config(config, registry)
    if not problems:
        print(f"performance runtime config: OK ({config.runtime_id})")
        return 0
    placeholders = [p for p in problems if "placeholder" in p]
    print(f"performance runtime config findings ({config.runtime_id}):")
    for problem in problems:
        print(f"  - {problem}")
    if placeholders and len(placeholders) == len(problems):
        # Expected for a committed reference file; it is a template, not a
        # deployable configuration. Said plainly so the exit code is not read as
        # "the validator is broken".
        print("not deployable: this is a reference template; replace the placeholders")
    return 1


def _render_synth_registry() -> list[str]:
    registry = load_synth_registry()
    lines = ["synth registry"]
    for entry in registry.synths:
        distributable = "distributable" if entry.is_distributable else "NOT distributable"
        lines.append(
            f"  {entry.synth_id:<18} license={entry.license_status:<10} "
            f"distribution={entry.distribution_status:<10} pi={entry.pi_status:<11} "
            f"{distributable}"
        )
    return lines


def _fake_runtime_report() -> list[str]:
    """Drive the fake runtime through a readiness check and render diagnostics."""
    runtime = FakeRuntime()
    runtime.start(
        StartRuntimeCommandV1(
            schema_version=StartRuntimeCommandV1.SCHEMA_VERSION,
            runtime_id=runtime.runtime_id,
            timeout_ms=1000,
        )
    )
    session = build_fake_session()
    runtime.prepare_session(
        PrepareSessionCommandV1(
            schema_version=PrepareSessionCommandV1.SCHEMA_VERSION, session_config=session
        )
    )
    runtime.arm_track(
        ArmTrackCommandV1(
            schema_version=ArmTrackCommandV1.SCHEMA_VERSION,
            session_id=session.session_id,
            track_id=session.tracks[0].track_id,
            armed=True,
        )
    )
    runtime.select_synth(
        SelectSynthCommandV1(
            schema_version=SelectSynthCommandV1.SCHEMA_VERSION,
            session_id=session.session_id,
            track_id=session.tracks[0].track_id,
            synth_id=FAKE_SYNTH_ID,
        )
    )
    readiness = runtime.readiness()
    result = runtime.export_diagnostics()
    if result.diagnostics is None:  # pragma: no cover - defensive
        raise PerformanceContractError("diagnostics export succeeded without diagnostics")
    lines = [
        f"fake runtime readiness: {'ready' if readiness.ready else 'not ready'}",
        f"fake runtime capture-ready: {'yes' if readiness.capture_ready else 'no'}",
    ]
    if readiness.blocking_subsystems:
        lines.append(f"  blocking: {', '.join(readiness.blocking_subsystems)}")
    lines.append("")
    lines.append(render_diagnostic_report(result.diagnostics).rstrip("\n"))
    return lines


def inspect_main(argv: list[str] | None = None) -> int:
    """Report configuration, registry, and fake-runtime diagnostics. Read-only."""
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else DEFAULT_CONFIG

    lines: list[str] = []
    exit_code = 0
    try:
        config = load_runtime_config(path)
        registry = load_synth_registry()
    except PerformanceContractError as exc:
        print(f"invalid: {exc}")
        return 1

    problems = validate_runtime_config(config, registry)
    lines.append(f"configuration    {config.runtime_id} ({config.runtime_kind.value})")
    lines.append(f"version policy   {config.runtime_version_policy}")
    lines.append(f"audio            {config.audio_backend} @ {config.sample_rate_hz} Hz / "
                 f"{config.buffer_frames} frames")
    lines.append(f"synth            {config.synth_id}")
    lines.append(f"offline required {config.offline_required}")
    if problems:
        exit_code = 1
        lines.append("findings")
        lines.extend(f"  - {problem}" for problem in problems)
    else:
        lines.append("findings         none")

    lines.append("")
    lines.extend(_render_synth_registry())
    lines.append("")
    lines.extend(_fake_runtime_report())

    print("\n".join(lines))
    return exit_code
