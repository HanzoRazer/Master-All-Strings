# Embedded Runtime Staging Plan

How the architecture ratified in [ADR-0007](../decisions/ADR-0007-EMBEDDED-PERFORMANCE-RUNTIME.md)
becomes a product, in order, without building two complete audio engines up front.

> **This document plans; it does not authorize.** DO-006 implements Stage 0 only.
> Every later stage is a separate Dev Order, and nothing here is scheduled,
> committed, or in progress. Stage numbering is dependency order, not a timeline.

## The split that makes this tractable

The product does not divide into "Ardour" and "not Ardour." It divides by **latency,
reliability, and workflow responsibility**:

```text
Phone / tablet / hardware controls
                |
                v
      Smart Guitar Controller
                |
        +-------+--------+
        |                |
        v                v
Lightweight Runtime   Studio Runtime
        |                |
        |                +-- Ardour
        |                    multitrack recording, complex routing,
        |                    editing, mixing, automation, export
        |
        +-- monitoring, tuner, metronome, lesson playback,
            amp/effects, basic looping, MIDI capture,
            preset switching, health supervision
```

**Practice Mode** is the normal startup state and Ardour is not running: fast start,
low latency, low memory, offline, dependable physical controls, minimal
configuration. A player powers on and plays.

**Studio Mode** launches an advanced runtime deliberately, when a workflow needs
capability beyond practice. The player still works through the Smart Guitar
interface; they never operate the native runtime UI during normal embedded use.

### Why hybrid beats either pure option

A pure Ardour product gets mature recording but pays for it constantly during
ordinary guitar use: slower startup, higher memory, more process complexity, a
larger failure surface, stronger coupling to session behavior, and real overhead for
tuning, practicing, monitoring, and changing presets.

A fully custom product gets control but must rebuild multitrack session persistence,
non-destructive editing, plugin automation, routing, timeline editing, export,
undo/redo, and interruption recovery — none of which is the product's
differentiation.

The hybrid builds only what differentiates and borrows the hard infrastructure where
it earns its cost.

## Capability model

Rather than one enormous runtime interface, capabilities are discovered per runtime.
`PerformanceRuntimePort.capabilities()` returns what a runtime actually supports; the
controller never assumes a uniform feature set.

| Group | Capabilities |
| --- | --- |
| Always-on (no Ardour required) | runtime health, device discovery, audio monitoring, input level, preset selection, tuner, metronome, lesson playback, basic looping, MIDI capture, panic |
| Studio (Ardour initially) | multitrack session, track management, advanced transport, complex routing, timeline editing, automation, mixing, bounce, export, session recovery |
| Shared (either runtime) | transport, capture, playback, plugin selection, session identity, diagnostics |

## Canonical music stays outside both runtimes

Neither runtime is ever the authoritative musical model. A take recorded in Practice
Mode and later opened in Studio Mode must refer to **one** musical identity, not two
competing note collections:

```text
raw performance -> RawPerformanceCaptureV1 -> Musical Core ingestion
                -> canonical revision -> piano roll / notation / TAB /
                   MIDI playback / Creative edits / Educational analysis
```

## Stages

### Stage 0 — Runtime constitution and contracts *(DO-006, in progress)*

Architecture, ADR, runtime-neutral port, capability vocabulary, ownership matrix,
raw-capture and runtime-health contracts, adapter rules, licensing register, fork
gate, fake adapters, tests.

Requires no Ardour install, no Pi, no audio output.

**Exit:** the repository can describe and test both runtime roles without depending
on any runtime-specific type.

### Stage 1 — Controller and fake runtimes

`SmartGuitarController`, `FakePracticeRuntime`, `FakeStudioRuntime`,
`RuntimeCapabilityRegistry`, `ModeCoordinator`. Enter and leave each mode, query
readiness, dispatch commands, handle unavailable capabilities, report faults,
preserve state across transitions.

Scenarios: practice available and studio not; studio available and practice not;
both; crash during capture; capability requested from the wrong runtime; mode switch
while recording; repeated start/stop; panic in any state.

**Exit:** product behavior is testable without audio hardware or Ardour.

### Stage 2 — Minimum Practice Runtime (MIDI first)

MIDI discovery and capture, basic synth output, panic, metronome, transport, preset
selection, health, raw event export. MIDI first because it validates deterministically
in a way full audio processing does not.

First real vertical slice: MIDI guitar → MIDI input → synth → audible output → raw
capture → Musical Core handoff.

**Exit:** a player can power on, select a sound, play, capture MIDI, and save the raw
performance — with no Ardour.

### Stage 3 — Practice Mode experience

Phone/tablet control, hardware-control mapping, Teensy events, preset browser, tuner,
metronome controls, lesson playback, recording indicator, input status, battery and
health, error recovery.

The interface issues product commands (`start_practice_recording`, `select_clean_amp`,
`load_lesson`, `repeat_phrase`) and never backend commands (`load_lv2_uri`,
`connect_port_1_to_bus_3`, `create_ardour_route`).

**Exit:** normal practice requires no Ardour knowledge and no Linux configuration.

### Stage 4 — Prepared Ardour adapter

Narrow integration against a **fixed session template** with known routing, one or
two prepared tracks, approved plugin slots, known buses and output routing, stable
OSC configuration, and predictable naming — not a general Ardour control surface.

Adapter supports: launch, identify version, readiness, open prepared session, play,
stop, record, arm known track, tempo, loop, panic, save, close.

**Exit:** the controller operates a prepared studio session without exposing the
Ardour desktop workflow.

### Stage 5 — Practice-to-Studio transition

The most important hybrid seam. Stop or freeze practice capture, close the raw
capture explicitly, ingest or reference canonical music, build a studio session
manifest, launch the runtime, populate prepared tracks, restore tempo/meter/loop,
verify routing, report readiness — and leave the practice session **unchanged**. No
silent conversion, no deletion.

**Exit:** a practice take becomes a studio session without losing raw timing,
provenance, or canonical identity.

### Stage 6 — Lightweight audio monitoring and effects

One input, one output, level monitoring, one approved amp/effects chain, bypass,
preset switching, mute, panic, latency reporting. Implementation may be a minimal LV2
host, PipeWire graph services, JACK clients, or an existing lightweight host behind an
adapter. **Do not build a plugin format or effects framework.**

**Exit:** dependable low-latency monitoring without launching Ardour.

### Stage 7 — Lightweight looper

Bounded v1: one phrase, start, stop, overdub, clear, loop length, count-in, tempo
alignment, export to session artifact. Not: unlimited layers, comping, time
stretching, per-layer effects, complex undo graphs, multitrack arrangement.

**Exit:** quick phrase looping in practice, promotable to Studio Mode for deeper work.

### Stage 8 — Expand Studio Mode from real workflows only

Do not copy a DAW feature list into the roadmap. Add a studio function only when a
documented Smart Guitar workflow needs it — record rhythm and lead, record a teacher
demonstration, compare student takes, add a backing track, trim, balance, export an
assignment, preserve a lesson session.

Each addition answers: is it needed in Practice Mode? Is it already available through
Ardour? Can the adapter expose it? Does it require Ardour UI access? Does it justify a
custom UI? Does it create canonical-data risk? Does it create license or maintenance
risk?

**Exit:** Studio Mode grows around guitar and educational workflows, not generic DAW
completeness.

### Stage 9 — Measure which responsibilities should migrate

Collect evidence: how often Studio Mode is launched, which commands are used, startup
time, memory, CPU, failure rate, session recovery, support burden, user confusion,
unused features, functions duplicated by the lightweight runtime.

Likely migration candidates out of Ardour: tuner, metronome, lesson playback, simple
looping, basic monitoring, amp presets, simple MIDI recording, preset switching.
Likely retainers: multitrack recording, timeline editing, complex routing, automation,
mixing, export, advanced session recovery.

**Exit:** retain-or-replace decisions rest on measured use.

### Stage 10 — Settle the long-term composition

- **Outcome A** — Ardour remains the Studio Runtime; lightweight runtime owns practice.
- **Outcome B** — Ardour becomes an optional advanced module over a lightweight core.
- **Outcome C** — Ardour is gradually replaced, viable only if measurement shows the
  remaining feature set is small enough to replace responsibly.

## Hardware division

The Teensy owns timing-sensitive physical behavior: footswitches, knobs, expression
pedals, pickup/input switching, status LEDs, mute relay, battery monitoring, power
sequencing, watchdog, emergency controls. The Pi owns audio and MIDI services,
application logic, session coordination, networking, the UI API, storage, and runtime
lifecycle.

```text
Footswitch pressed -> Teensy changes LED immediately
                   -> command sent to Pi
                   -> controller routes it (practice looper | studio record)
                   -> acknowledgment returned
```

Physical response stays immediate even when Linux or the runtime is busy.

## Dev Order sequence

| Order | Scope |
| --- | --- |
| **DO-006A** | Runtime constitution and contracts — *this tranche* |
| DO-006B | MIDI Practice Runtime: input, synth output, capture, metronome, panic, diagnostics |
| DO-006C | Practice controller and mobile API: command routing, mode state, phone control, Teensy bridge |
| DO-006D | Ardour Studio adapter: prepared sessions, launch, readiness, transport, record, save, diagnostics |
| DO-006E | Practice-to-Studio promotion: session manifest, artifact transfer, canonical references, recovery |
| DO-006F | Lightweight guitar audio: monitoring, amp/effects host, presets, latency measurement |
| DO-006G | Lightweight looper: phrase capture, overdub, transfer to Studio Mode |
| DO-006H | Pi hardware qualification: startup, latency, thermals, stability, underruns, recovery, offline |

## First useful release

Full Ardour integration is not required for a credible first release:

**Release 1 — Practice Mode.** MIDI guitar input, software synth, tuner, metronome,
lesson playback, MIDI capture, piano roll, notation, TAB, phone control, Teensy
controls.

**Release 2 — Studio Mode.** Launch a prepared Ardour session, multitrack record,
basic edit, save, export.

That order produces user value earlier and stops the Smart Guitar's success from
depending on solving every Ardour and Raspberry Pi integration problem at once.

> **Governing principle.** The lightweight runtime delivers the daily guitar
> experience. Ardour supplies advanced studio infrastructure only when the workflow
> requires it.
