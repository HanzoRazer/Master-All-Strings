# Ardour Adapter Boundary

Ardour-specific concerns only. This document **does not** define constitutional
ownership — that is [ADR-0007](../decisions/ADR-0007-EMBEDDED-PERFORMANCE-RUNTIME.md)
and the [registry](../../governance/engine_architecture_v1.json). Nothing here may
contradict either.

Everything below describes what lives *inside* `performance/adapters/ardour/`. None
of this vocabulary may cross `PerformanceRuntimePort`.

> **Evidence status.** Source-inspected, never executed. Ardour 9.7 source was read
> to establish which integration surfaces exist. No Ardour runtime has been built,
> started, or measured. **Source presence proves an interface exists; it does not
> prove the interface works.** Every claim below is a claim about source code, not
> about behavior.

## Supported versions

```text
runtime_version_policy   >=9.7,<10
verified_source_version  9.7
verified_runtime_versions  []          <-- none; no runtime has passed conformance
```

Ardour 9.7 (`libs/ardour/revision.cc`: revision `9.7`, date `2026-06-04`) is the only
inspected revision. Compatibility with later 9.x releases is **provisional and
untested**. Ardour 10 is outside the range because major-version compatibility has
not been assessed. The adapter must reject an unsupported major version with an
explicit compatibility fault rather than attempting to proceed.

Do not read this range as "all Ardour 9.x is verified." Nothing is verified.

## OSC surface

Extracted from `libs/surfaces/osc/osc.cc` (6,844 lines) in the 9.7 source.

Paths are registered two ways, and both matter when auditing coverage:
statically via `REGISTER_CALLBACK (serv, X_("/path"), ...)`, and dynamically via
sub-path dispatch (`strncmp (sub_path, X_("recenable"), 9)`). **A literal-string
search alone under-reports the surface** — `/strip/recenable` exists only through the
dynamic path and does not appear as a registered literal.

### Paths relevant to the first proof

| Need (§3.2) | OSC path | Source status |
| --- | --- | --- |
| Play | `/transport_play`, `/toggle_roll` | present |
| Stop | `/transport_stop`, `/stop_forget` | present |
| Transport speed | `/set_transport_speed`, `/transport_speed` | present |
| Locate | `/locate`, `/goto_start`, `/goto_end` | present |
| Record arm (global) | `/rec_enable_toggle`, `/toggle_all_rec_enables` | present |
| Record arm (per strip) | `/strip/recenable` | present via dynamic dispatch |
| Recording state | `/is_recording`, `/record_enabled` | present (feedback) |
| Panic / all-notes-off | `/midi_panic` | present |
| Metronome | `/toggle_click`, `/click/level` | present |
| Loop | `/loop_toggle`, `/loop_location` | present |
| Save | `/save_state` | present |
| Session feedback | `/session/loaded`, `/session_name`, `/session/exported` | present |
| Surface configuration | `/set_surface`, `/set_surface/feedback`, `/set_surface/port` | present |
| Arbitrary named action | `/access_action`, `/access_action/<path>` | present |
| **Tempo** | — | **absent** (see GAP-001) |
| **Meter** | — | **absent** (see GAP-001) |
| **Runtime version** | — | **absent** (see GAP-002) |

Every occurrence of "tempo" in `osc.cc` is `temp_mode` / `TempOff`, a surface
temporary-mode concept unrelated to musical tempo. There is no tempo or meter control
in the 9.7 OSC surface.

### Bounded client

The adapter's OSC client is a **bounded command set**, not a general OSC bridge. It
exposes only the paths above. It must not offer arbitrary path execution, and it must
not expose `/access_action` as an open-ended escape hatch to callers — any
`access_action` use is a named, reviewed constant inside the adapter.

## MIDI routing

`libs/surfaces/generic_midi` provides MIDI-based control (D3 step 5).
`libs/backends/alsa` provides native ALSA MIDI on Linux, which is the appliance path:
no JACK daemon required, satisfying D12's "no manual JACK/PipeWire configuration."

## Session template

`share/templates/` in the 9.7 source contains only `.stub` — **Ardour ships no usable
template.** The prepared session template is ours to author, and it carries what OSC
cannot set (see GAP-001): tempo, meter, track layout, routing, and the synth slot.

## Synth loading

Two LV2 synthesizers ship in-tree (`libs/plugins/`):

- **`reasonablesynth.lv2`** — the first-proof default. No soundfont required,
  therefore no unresolved sound-library licensing question.
- **`a-fluidsynth.lv2`** — SF2 soundfont player. Available, but the soundfont
  identity and its redistribution status are unresolved, so it is not the
  acceptance-path synth.

The first proof optimizes for a controlled dependency chain, not for guitar-tone
quality. A musically preferred voice is a later, separate component and licensing
decision.

## Process launch

`headless/` provides a headless build target — Ardour without the GTK GUI, which is
the correct topology for an appliance (D4). `luasession/` and `session_utils/` provide
scripted and command-line session handling (D3 step 6).

The adapter starts and inspects a process; it does not link against Ardour.

## Readiness

Readiness is *not* "the process started." It requires each `RuntimeHealthV1`
subsystem — process, audio backend, audio output, MIDI input, synth, session, capture
— to report ready independently. OSC feedback (`/session/loaded`, `/is_recording`)
supplies part of this; the rest is process and device inspection.

## Failure detection

Process exit, OSC endpoint unavailable, health timeout, startup timeout, missing
device, synth load failure, and unsupported version. Every one produces an explicit
fault. A failure during capture closes the capture as `INTERRUPTED` and attaches the
fault — it is never reported as an ordinary stop (ADR-0007 D15).

## Audio backends

| Backend | Source status | Use |
| --- | --- | --- |
| `alsa` | present | Pi appliance target |
| `dummy` | present | **headless validation with no audio hardware** |
| `jack`, `pulseaudio` | present | alternative Linux configurations |
| `portaudio`, `coreaudio` | present | Windows / macOS — non-target |

The `dummy` backend is what makes a partial desktop spike possible on any Linux
machine without an audio interface: process startup, identity, version checking, OSC
readiness, transport, session loading, MIDI handling, capture, save/close, and
diagnostics. It cannot prove audible output, audio-device compatibility, latency,
thermals, stability, or underrun behavior.

## Unsupported behavior

The adapter does not and will not: install Ardour, download plugins, edit system
audio settings, scan arbitrary plugin directories, run shell commands from
configuration, drive the Ardour GUI, read Ardour session files as canonical music, or
modify Ardour source.

## Known coupling

Accepted, and each is recorded so a runtime replacement knows what to re-solve:

1. **OSC path names** are Ardour's, confined to the adapter's bounded client.
2. **The session template format** is Ardour's; a replacement runtime needs its own.
3. **Tempo and meter arrive through the template**, not through a live command
   (GAP-001), so changing them mid-session is not currently expressible.
4. **Version detection is out-of-band** (GAP-002), currently process inspection.
5. **Capture extraction** depends on where Ardour writes captured MIDI.

## Fallback behavior

If OSC is unavailable, the adapter reports a fault; it does not fall back to driving
a GUI. If the configured synth cannot load, the session does not silently substitute
another. If a MIDI device is absent, capture does not start. Nothing degrades
silently — every reduced state is an explicit fault a caller can see.

## Open gaps

Tracked in [ARDOUR_GAP_AUDIT.md](../planning/ARDOUR_GAP_AUDIT.md). Fork disposition is
`DEFER_FORK_PENDING_EVIDENCE` per [ARDOUR_FORK_GATE.md](../planning/ARDOUR_FORK_GATE.md).
