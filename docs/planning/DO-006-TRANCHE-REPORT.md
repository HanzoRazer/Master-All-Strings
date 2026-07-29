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
| 5 | 7 JSON schemas, 38 fixtures under `resources/performance/` (21 invalid) |
| 6 | Configuration, session builder, capture normalization, observations, diagnostics, export, ingestion, fake runtime, Ardour scaffold, 2 read-only CLIs |
| 7 | 501 tests across 8 modules |
| 8 | Pi qualification template, spike procedure, this report |
| 9 | Review-pass fixes: readiness lifecycle, stop-during-capture, port API, version parsing |

**Verification:** 818 tests pass, coverage 96.94% (floor 95%), ruff clean, mypy
strict clean, governance validator `OK`, generated views match the registry, 0 broken
doc links.

> **Base.** This tranche is stacked on the DO-005 re-land (PR #12), not on `main`
> directly. `main` had reverted DO-005 (PR #10, a procedural revert of a premature
> merge), and DO-006 depends on the registry and validator that re-land restores.

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

## ⚠️ Commit history: do not bisect through this tranche

The branch head is correct. Six of the intermediate commits are not, in two different
ways, and neither is visible from the commit messages. Anyone running `git bisect`,
cherry-picking, or reverting part of this range needs this table.

| Commit | | Tests | Coverage | `pytest --cov` | State |
| --- | --- | --- | --- | --- | --- |
| `868f40a` | C1 architecture | 329 | 98.85% | exit 0 | clean |
| `4b51dd5` | C2 governance | 329 | 98.85% | exit 0 | clean |
| `49e27a3` | C3 licensing | 329 | 98.85% | exit 0 | clean |
| `f568446` | C4 contracts | 329 | **39.62%** | **exit 1** | **fails the 95% gate** |
| `7968b03` | C5 schemas | 329 | **39.62%** | **exit 1** | **fails the 95% gate** |
| `8bf6d6d` | C6 utilities + fake runtime | 329 | **28.04%** | **exit 1** | **fails the 95% gate** |
| `ddc63c5` | C7 tests | 789 | 97.05% | exit 0 | **green but defective** |
| `312e69c` | C8 spike prep | 789 | 97.05% | exit 0 | **green but defective** |
| `e59bb3a` | review fixes | 830 | 96.96% | exit 0 | clean |
| `ae19a1a` | full-review fixes | 844 | 96.96% | exit 0 | clean |

**C4–C6 fail CI in isolation.** The rollout order placed all tests in Commit 7, so
three commits carry new code with no tests behind it. The repository's own 95%
coverage floor rejects them. CI never caught this because the `verify` workflow runs
on the pull-request head, not on each commit. This was a known trade-off at the time
and it was the wrong call: the order specified test *content* for Commit 7, not that
the tree had to be red to get there. Shipping each module's tests alongside the module
would have kept every commit green.

**C7–C8 are worse, because they look fine.** Both report a passing suite while two
defects are live:

```text
$ git checkout ddc63c5
after start -> readiness.ready = False        # docs say start -> readiness -> prepare
after stop during capture -> completion_state = in_progress   is_closed = False
```

The second is a capture permanently claiming to record on a runtime that no longer
exists — the exact false state ADR-0007 D15 forbids. C7 also contains a test
(`test_started_but_unprepared_runtime_is_not_ready`) that *asserts the readiness bug is
correct behaviour*, with a comment rationalising it. A red commit announces itself; a
green one asserting a defect does not.

Both defects are fixed in `e59bb3a`. Nothing reaches `main` broken.

**Why this history was not rewritten.** Squashing the fixes back into their origin
commits would mean rewriting `feat/do-005-reland`, which was already merged to `main`.
Rewriting merged history is a larger hazard than the one it removes, so the history
stands and this table is the mitigation.

**Practical guidance.** Bisect from `ae19a1a` or later. If you must land inside the
range, treat `f568446`–`8bf6d6d` as build-red and `ddc63c5`–`312e69c` as
verified-but-wrong, and take the readiness and capture-closure behaviour from
`e59bb3a` or later regardless of what the suite says at the commit you are on.

## Decisions a reviewer should check

1. `piano-roll-projection` is **Musical Core**, not Performance, even though recording
   happens in Performance. Creative owns the interactive editing experience;
   Performance owns no note model and reaches projections via `ProjectionResultV1`.
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
