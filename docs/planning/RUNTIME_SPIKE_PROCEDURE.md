# Runtime Spike Procedure

How to execute DO-006 Commits 8–11 when a Linux target or a Raspberry Pi 5 is
available. Written so the work can be done by someone who was not part of the
architecture tranche.

> **STATUS: NOT EXECUTED.** No step below has been performed. This is a procedure,
> not a record.

## Prerequisites

Ardour 9.7 source is **not vendored** into this repository, deliberately: 18 MB of
GPL v2 C++ would extend distribution obligations to a repository that currently has
zero runtime dependencies. Obtain it separately and verify it:

```text
Ardour-9.7.0.tar.bz2
SHA-256  5f3adf00b8991e25d8b8ccb503bf21010a1f08a121be14ca6039d309690ea98c
size     18,118,247 bytes
license  GPL v2 (COPYING)
version  libs/ardour/revision.cc -> revision "9.7", date "2026-06-04"
```

Nothing in this repository installs it. No utility here may install a runtime,
download a plugin, or change a system audio setting (ADR-0007 §7).

## Platform rules

**A Windows or macOS build produces no admissible evidence for the Pi gate.** Ardour
on Windows uses PortAudio/WASAPI and a different MIDI stack; its readiness timing,
latency, jitter, and underrun behaviour describe a different system. If a Windows
machine is used at all, label every artefact:

```text
WINDOWS_ONLY_NON_TARGET_EVIDENCE
```

Permitted on Windows: contract development, fake-adapter tests, source inspection,
OSC message construction, serialization tests, process-boundary design, and
documentation. Nothing that fills a cell in
[PI_HARDWARE_QUALIFICATION.md](PI_HARDWARE_QUALIFICATION.md).

---

## Commit 8 — Desktop spike (Linux)

Goal: prove the minimum adapter surface against a real Ardour, with no source
modification.

The `dummy` audio backend (`libs/backends/dummy`, present in 9.7) makes most of this
possible on any Linux machine **without an audio interface**. It cannot prove audible
output, device compatibility, latency, thermals, or underruns.

### Steps

1. Build Ardour 9.7 from source on the Linux target. Record the exact configure
   flags — they belong in the component register, and a build with different flags is
   a different artefact.
2. Confirm the version: `ardour9 --version`, or read `libs/ardour/revision.cc`.
   Version detection is out of band because GAP-002 means OSC does not provide it.
3. Enable the OSC surface and record the port and feedback configuration.
4. Author a prepared session template with one MIDI track, known routing, and a
   `reasonablesynth.lv2` slot. Ardour ships no usable template — `share/templates/`
   contains only `.stub` — so this is our own work.
5. Implement only the minimum in
   `src/master_all_strings/performance/adapters/ardour/adapter.py`: identity, version,
   readiness, transport, synth selection, record arm, capture, event retrieval, panic.
   The bounded OSC client and process-inspection boundary already exist.
6. Run the existing conformance suite against the Ardour adapter instead of the fake:

   ```text
   tests/performance/test_fake_runtime_conformance.py
   ```

   The suite is written against `PerformanceRuntimePort`, not against the fake's
   internals, so it should be reusable with a different fixture. Where it is not,
   that is itself a finding worth recording.
7. Record **every** unresolved behaviour in
   [ARDOUR_GAP_AUDIT.md](ARDOUR_GAP_AUDIT.md), including ones that turn out fine —
   `interface_attempted` changing from `NONE` to a tested value is the point.

### Resolve the two known gaps, in this order

**GAP-001 (no OSC tempo or meter).** Try in order, stopping at the first that works:
(a) prepared session template carrying tempo and meter — expected to cover the first
proof; (b) Lua scripting; (c) `/access_action` with a named action. Record which
worked and which did not.

**GAP-002 (no OSC version).** Try process inspection first (`ardour9 --version`),
then Lua. Process inspection is the expected answer and needs no Ardour change.

### Gate

No Ardour source modification. If a workflow appears to require one, stop and follow
[ARDOUR_FORK_GATE.md](ARDOUR_FORK_GATE.md) — a `FORK_CANDIDATE` ruling needs eight
recorded items and separate owner authorization.

---

## Commit 9 — Raspberry Pi spike

Goal: measured evidence on the target.

1. Build or install Ardour 9.7 on the Pi 5. Record how, exactly.
2. Replace every `REPLACE_WITH_` placeholder in a **local copy** of
   `resources/performance/examples/pi_ardour_reference_v1.json` with real device
   identifiers. Do not commit real device names — they are machine-specific.
3. Validate it:

   ```text
   python scripts/validate_performance_runtime_config.py <your-config.json>
   ```

   A deployable config reports `OK`. The committed reference reports four
   placeholder findings, which is correct for a template.
4. Work through [PI_HARDWARE_QUALIFICATION.md](PI_HARDWARE_QUALIFICATION.md), filling
   the environment block first. An unlabelled measurement is not evidence.
5. Measure MIDI-to-audio latency **externally**. Software timestamps measure the
   software path, not what the player hears.
6. Run the one-hour stability test with thermal logging throughout.
7. Set the buffer-size and latency targets *from* the data. They are conclusions, not
   premises.

### Gate

Evidence report completed. Blocked criteria stay marked blocked — criteria 4–7 depend
on Musical Core ingestion and projection, which do not exist yet, so no Pi session can
close them.

---

## Commit 10 — Canonical projection proof

Blocked on a **Musical Core** Dev Order, not on hardware.

DO-006 proves this seam structurally with a test double
(`tests/performance/test_projection_proof.py`): one capture, one revision id, three
projection requests citing it, raw capture unchanged. Real ingestion needs a Musical
Core score-document and revision implementation, plus the notation, TAB, and
piano-roll projections — all currently registered `planned` with no code.

When those exist, replace the double with the real Core and keep every assertion.

---

## Commit 11 — Gap disposition

Classify each gap as: configuration, OSC, MIDI, scripting, sidecar, Master All
Strings UI, deferred, rejected, or source-change candidate. Then record an explicit
ruling in [ARDOUR_FORK_GATE.md](ARDOUR_FORK_GATE.md): `NO_FORK_REQUIRED`,
`DEFER_FORK`, or `FORK_CANDIDATE`.

`NO_FORK_REQUIRED` requires that the ladder was actually exercised. "We did not try
Lua" is disqualifying.

---

## Method note for whoever extends the OSC audit

Ardour registers OSC paths two ways: statically via
`REGISTER_CALLBACK (serv, X_("/path"), ...)`, and dynamically via sub-path dispatch
(`strncmp (sub_path, X_("recenable"), 9)`). `/strip/recenable` exists **only** through
the dynamic route and never appears as a literal string.

A grep-only audit therefore under-reports the surface. Check both before concluding
that something is absent — that is how GAP-001 and GAP-002 were established as real
rather than assumed.
