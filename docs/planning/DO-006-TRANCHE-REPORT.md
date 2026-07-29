# DO-006 Tranche Report

What was delivered, what was not, and what remains open. Written so a fresh engineer
can reconstruct the state without conversation history (acceptance criterion 30).

**Tranche:** DO-006 Commits 1–7, plus unexecuted scaffolding for 8–11.
**Engine:** Performance Engine. **Base:** `main` after PR #8 (`e8ff0cd`).
**Production behavior:** unchanged.

## Delivered

| Commit | Content |
| --- | --- |
| 1 | ADR-0007 (Proposed), embedded-runtime architecture with 8 diagrams, responsibility matrix, staging plan; four-engine model updated |
| 2 | 9 capabilities + 6 contracts + ADR-0007 in the governance registry; views regenerated |
| 3 | Component register, Ardour adapter boundary, gap audit, fork gate |
| 4 | Runtime-neutral contracts and `PerformanceRuntimePort` |
| 5 | 7 JSON schemas, 30 fixtures under `resources/performance/` |
| 6 | Configuration, session builder, capture normalization, observations, diagnostics, export, ingestion, fake runtime, Ardour scaffold, 2 read-only CLIs |
| 7 | 460 tests across 8 modules |
| — | Pi qualification template, spike procedure, this report |

**Verification:** 772 tests pass, coverage 97.01% (floor 95%), ruff clean, mypy
strict clean, governance validator `OK`, generated views match the registry.

## Not delivered, and why

**Commits 8–11 were not executed.** They require a built Ardour, audio hardware, a
MIDI device, and a Raspberry Pi 5. None was available, and this repository's
utilities are forbidden from installing runtimes or changing system audio settings.
Their artefacts ship as structure with every hardware-dependent field marked
`UNMEASURED` and the fork disposition `DEFER_FORK_PENDING_EVIDENCE`.

No latency, jitter, thermal, underrun, audible-output, or stability figure exists
anywhere in this repository. No Ardour runtime has been built, started, or measured
on any platform.

**Real canonical ingestion was not built.** Musical Core has no score-document,
no revision identity, and `notation-projection`, `tab-projection`, `midi-projection`,
and `piano-roll-projection` are all registered `planned` with no code. DO-006 defines
the Performance side of the handoff only; the seam is proved structurally with a test
double. Building Core stubs here to make the tranche look end-to-end complete was
explicitly declined.

## Evidence from the Ardour 9.7 source

Source-inspected, never executed. SHA-256
`5f3adf00b8991e25d8b8ccb503bf21010a1f08a121be14ca6039d309690ea98c`; not vendored.

**Present:** OSC surface, generic-MIDI surface, Lua scripting (180 script entries),
headless build target, session utilities, ALSA and dummy audio backends, WebSocket
control, LV2 hosting, and two in-tree synths (`reasonablesynth.lv2`,
`a-fluidsynth.lv2`).

**Absent, and now recorded as gaps:**

- **GAP-001** — no OSC tempo or meter control. Every `tempo` occurrence in `osc.cc` is
  `temp_mode`/`TempOff`, unrelated to musical tempo. Tempo is in the first proof's
  required feature set. Untested mitigations: session template, Lua, `access_action`.
- **GAP-002** — no OSC version path. Version detection must be out of band. Untested
  mitigations: process inspection, Lua.

**Also found:** `share/templates/` contains only `.stub`, so the session template is
our own work rather than a derivative.

**Method note.** OSC paths register both as `REGISTER_CALLBACK` literals and via
dynamic sub-path dispatch; `/strip/recenable` exists only through the latter. A
grep-only audit under-reports the surface.

## Licensing status

Release gate **CLOSED**: 9 components `UNRESOLVED`, 1 approved (our own
configuration), 0 verified on target hardware.

Ardour is GPL v2, but its name and logo are trademarked separately and
`PACKAGER_README` restricts naming. Code license and branding do not travel together.
This applies to shipping *unmodified* Ardour in a commercial image, not only to
forking. `reasonablesynth.lv2` is the first-proof default because it needs no
soundfont, keeping the acceptance path clear of the sound-library licensing question
most likely to stall it.

## Fork status

`DEFER_FORK_PENDING_EVIDENCE`. Zero of nine escalation rungs exercised. No Ardour
source modification is authorized, and neither recorded gap implies one — both have
untested mitigations at the configuration, scripting, or sidecar level.

## Decisions a reviewer should check

1. `piano-roll-projection` is **Musical Core**, not Performance, even though recording
   happens in Performance. Creative owns the interactive editing experience;
   Performance owns no note model and reaches projections via `ProjectionResult`.
2. `CanonicalIngestionRequestV1` is **Core-owned, Performance-produced**, mirroring
   `ScoreEditCommandSet`. `with_revision` refuses to overwrite and refuses a revision
   id equal to the session id.
3. Performance resources live under `resources/performance/{schema,examples}`
   following the `resources/instruments` precedent; top-level `schemas/` stays
   constitutional. No `config/` tree was created.
4. One of 21 invalid fixtures is Python-only — strictly increasing sequence numbers
   is not expressible in JSON Schema. The manifest records which validator rejects
   each fixture rather than implying the schema catches everything.
5. The one-track bound and the audio-track rejection are enforced by contract, not
   documented as intent.

## Next authorized work

Per [EMBEDDED_RUNTIME_STAGING.md](EMBEDDED_RUNTIME_STAGING.md), this tranche is
**Stage 0 / DO-006A**. It authorizes nothing further.

Two independent tracks are now unblocked:

- **Hardware** — Commits 8–11 via
  [RUNTIME_SPIKE_PROCEDURE.md](RUNTIME_SPIKE_PROCEDURE.md), needing a Linux target
  and a Pi 5.
- **Musical Core** — score-document, revision identity, and the four projections, so
  the ingestion seam can be proved against real Core instead of a double.

Neither is scheduled. ADR-0007 remains **Proposed** and becomes Accepted only through
normal repository governance.
