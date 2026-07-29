# Embedded Performance Runtime

The operational companion to [ADR-0007](../decisions/ADR-0007-EMBEDDED-PERFORMANCE-RUNTIME.md).
The ADR ratifies the boundary; this document explains how the subsystem is built,
how a runtime is driven, and where each responsibility stops.

Product-facing name: **Performance Studio**. Architectural name: **Embedded
Performance Runtime**.

> **Status.** Architecture and contracts only. No runtime has been built, run, or
> measured. Every hardware figure in this repository is `UNMEASURED`. Production
> behavior is unchanged by this tranche.

## Purpose

Let a player plug in a guitar or guitar-to-MIDI device, hear a software
synthesizer, record what they played, and get it back as a piano roll, as standard
notation, and as TAB — without operating a DAW, configuring Linux audio, or
learning what a bus is.

## Scope

**In scope.** One Raspberry Pi 5, one MIDI input device, one MIDI track, one
software synthesizer, one stereo output; play, stop, record, panic, tempo, meter,
optional metronome, optional loop region; MIDI capture; piano-roll, notation, and
TAB projection of the captured result.

**Out of scope.** A full DAW, unrestricted multitrack production, waveform editing,
audio comping, mixing buses, sends, mastering, automation lanes, video sync, time
stretching, audio pitch correction, unrestricted plugin scanning, cloud-required
performance, native polyphonic audio-to-MIDI, an Ardour fork, upstream Ardour
contributions, commercial Pi-image distribution, Educational coaching logic,
Creative composition workflows, and production rollout.

## Engine ownership

The Embedded Performance Runtime is **inside the Performance Engine**. Ardour is
not an engine; it is one implementation of a replaceable audio infrastructure
layer beneath all four engines.

| Concern | Owner |
| --- | --- |
| Canonical music, revisions, MIDI/notation/TAB/piano-roll semantics | Musical Core |
| Capture, playback, transport, devices, runtime lifecycle, diagnostics | Performance Engine |
| Score authoring, interactive piano-roll editing, edit proposals | Creative Engine |
| Coaching, assessment, difficulty, practice metrics | Educational Engine |
| Audio backend, MIDI backend, plugin hosting, process supervision | Audio infrastructure (replaceable) |

## System context

```text
Phone / tablet / hardware controls
              |
              v
     Performance Engine  ── depends on ──>  Musical Core (canonical music)
              |                                   ^
              | PerformanceRuntimePort            | ingestion request
              v                                   |
     Audio infrastructure layer  ─────────────────+
       +-- Ardour adapter (first candidate)
       +-- fake runtime (tests)
       +-- future lightweight runtime
              |
              v
     ALSA / PipeWire / JACK · MIDI devices · LV2 plugins · filesystem
```

Educational consumes `PerformanceObservationV1` as evidence. Creative never
consumes runtime records at all — captured content reaches Creative through
canonical music, never through runtime internals.

> **Diagram numbering** follows the DO-006 §5.1 list, so the numbers are traceable to
> the order. They appear here in *reading* order instead — Diagram 7, the readiness
> state machine, sits with the lifecycle section it explains rather than after
> Diagram 6.

## Diagram 1 — Pi hardware and software stack

```text
+-----------------------------------------------------------+
|  Guitar / guitar-to-MIDI device                            |
|  (MIDI guitar, divided pickup, external audio-to-MIDI)     |
+---------------------------+-------------------------------+
                            | USB / DIN MIDI
+---------------------------v-------------------------------+
|  Raspberry Pi 5                                            |
|                                                            |
|  +------------------------------------------------------+  |
|  |  Master All Strings (Performance Engine)             |  |
|  |    contracts · ports · adapters · diagnostics        |  |
|  +---------------------------+--------------------------+  |
|                              | runtime-neutral IPC         |
|  +---------------------------v--------------------------+  |
|  |  Performance runtime process (Ardour candidate)      |  |
|  |    transport · session · capture · LV2 synth host    |  |
|  +---------------------------+--------------------------+  |
|                              |                              |
|  +---------------------------v--------------------------+  |
|  |  Audio / MIDI services: ALSA · PipeWire · JACK       |  |
|  +---------------------------+--------------------------+  |
+------------------------------|-----------------------------+
                               v
                    Stereo audio output
```

Control surface (phone, tablet, or local web) attaches over the network to Master
All Strings — never directly to the runtime process.

## Process topology

Two processes, always. Master All Strings never links against runtime internals.

## Diagram 2 — Guitar MIDI to synth playback

```text
Guitar MIDI  ->  MIDI input port  ->  runtime MIDI routing  ->  synth plugin
                                                                     |
                                                                     v
                                                          audio output device
```

The Performance Engine selects the port, the routing, and the synth by identifier.
It does not carry the audio or MIDI stream itself.

## Diagram 3 — Runtime process boundary

```text
        Master All Strings process              |   Runtime process
                                                |
  PerformanceRuntimePort  (neutral vocabulary)  |
        |                                       |
        +-- FakeRuntimeAdapter -----------------|  (no process; tests)
        |                                       |
        +-- ArdourRuntimeAdapter ---------------|--> Ardour
              - OSC client                      |     - audio backend
              - process inspection              |     - MIDI backend
              - session template                |     - LV2 synth
              - event extraction                |
                                                |
  Ardour vocabulary may exist ONLY left of this boundary inside the adapter
  package, and may never cross the port.
```

## Runtime lifecycle

`start` → `readiness` → `prepare session` → `arm track` → `transport` →
`capture` → `close capture` → `stop`. Every step is a command contract with a
result contract; no step is implied by another's success.

## Diagram 7 — Startup and readiness state machine

```text
   OFF
    |  start
    v
 STARTING ---- startup timeout ----> FAILED
    |
    | process alive
    v
 PROBING ----- health timeout -----> FAILED
    |
    | infrastructure subsystems report
    v
  READY <-------------------+          ready: accepts commands
    |   |                   | recovered            (session still UNKNOWN)
    |   | prepare session   |
    |   v                   |
    | CAPTURE-READY         |          capture_ready: a session exists
    |                       |
    | subsystem fault       |
    v                       |
 DEGRADED ------------------+
    |
    | unrecoverable
    v
  FAILED
```

Readiness is **two questions, not one**, because they gate different things and
become true at different points:

| | Means | True when |
| --- | --- | --- |
| `ready` | the runtime is up and accepts commands | after `start`, **before** a session exists |
| `capture_ready` | a session is prepared and capture may begin | after `prepare_session` |

`RuntimeHealthV1` splits its seven subsystems to match. The five **infrastructure**
subsystems — process, audio backend, audio output, MIDI input, synth — are what
`RuntimeState.READY` asserts. The two **session-scoped** subsystems — session,
capture — are `UNKNOWN` until a session is prepared, which is a normal point in the
lifecycle rather than a fault.

Folding the session group into `READY` would make the lifecycle above unreachable:
readiness could never be true before `prepare session`, which is the step that
follows it. All seven are still reported separately (ADR-0007 §6.4) — a single
aggregate boolean remains insufficient and is rejected by contract.

## Device discovery

Read-only enumeration of MIDI inputs and audio outputs. Discovery never installs
drivers, never edits system audio settings, and never mutates the operating
system. A configured device that is absent produces an explicit fault; it is never
silently substituted.

## MIDI path

Input port → runtime routing → armed track → synth. Captured events are extracted
from the runtime in their original order with original timing.

## Audio path

Synth output → runtime output routing → configured audio device. Sample rate and
buffer size are declarative configuration; the runtime is asked to honor them and
reports a fault if it cannot.

## Synth path

The synth is selected by `synth_id` against an approved registry. The runtime is
asked to load exactly that plugin. Unrestricted plugin scanning is out of scope: a
synth that is not in the registry cannot be selected. `reasonablesynth.lv2` is the
first-proof default because it needs no soundfont and therefore has no unresolved
sound-library licensing question.

## Transport

Play, stop, record, tempo, meter, optional metronome, optional loop region, and
panic. Panic is a first-class command, not a side effect of stop: a stuck note must
be clearable without ending the session.

## Capture

Every accepted MIDI event becomes a `CapturedMidiEventV1` with a monotonic
`sequence_number` and a non-decreasing `capture_time_ns`. Events accumulate into a
`RawPerformanceCaptureV1`, which is immutable once closed. Completion is explicit:
`IN_PROGRESS`, `COMPLETE`, `INTERRUPTED`, `FAILED`, or `CANCELLED`. A crash yields
`INTERRUPTED`, never `COMPLETE`.

## Diagram 4 — Raw capture to canonical music

```text
  MIDI events from runtime
            |
            v
  CapturedMidiEventV1 (sequence-ordered, original timing)
            |
            v
  RawPerformanceCaptureV1  [immutable once closed]
            |
            +--> PerformanceObservationV1   (facts about the take)
            |
            v
  CanonicalIngestionRequestV1   (Performance produces; Musical Core owns)
            |
            v
  Musical Core  -->  canonical revision id
            |
            v
  raw capture UNCHANGED, cited by everything downstream
```

## Canonical ingestion

The Performance Engine emits a `CanonicalIngestionRequestV1` carrying the capture
identity, its digest, instrument and tuning profile identifiers, tempo and meter
context, and the requested projection types. Musical Core owns the contract and
returns the canonical revision identifier.

Performance **may** reference a revision identifier once supplied. Performance
**may not** mint one, may not treat a runtime session ID as one, and may not
implement a competing revision model.

> Musical Core has no score-document or revision implementation yet. DO-006 proves
> this seam structurally with test doubles. Real revisions, ingestion, and the
> notation, TAB, and MIDI projections are a later Musical Core Dev Order.

## Diagram 5 — Canonical music to piano roll, notation, and TAB

```text
                  canonical revision  R
                          |
        +-----------------+-----------------+
        |                 |                 |
        v                 v                 v
   piano roll         notation             TAB
   (cites R)          (cites R)          (cites R)
        |                 |                 |
   interaction       rhythmic spelling   tuning, range
   surface           rests, measures     string/fret assignment
   (Creative UX)     voices, ties        playability resolution
                     beams, enharmonics
```

Three interpretations, one revision. All three cite `R`. None writes into the raw
capture, and a projection failure never invalidates a capture.

## Piano roll

A projection and an interaction surface that produces validated canonical edit
commands. It maintains no independent authoritative note collection (ADR-0007 D8).
The semantic projection is Musical Core's `piano-roll-projection`; the interactive
editing experience is Creative's; the Performance Engine may display a projection
during review through `ProjectionResultV1` and owns no note model.

## Notation

Musical Core projection. May require rhythmic spelling, rests, measures, voices,
ties, beams, and enharmonic selection. Performance does not spell rhythm.

## TAB

Musical Core projection. May require tuning, instrument range, string and fret
assignment, and playability resolution. Where the capture carries observed
`source_string` evidence, TAB projection may use it; where it does not, the field
stays unresolved and the assignment is a projection, never a recorded observation
(ADR-0007 D7).

## Diagram 6 — Performance observation to Educational interpretation

```text
Performance Engine
    PerformanceObservationV1   (facts: counts, timing, durations, velocity range,
              |                 channels, missing note-offs, faults, runtime state)
              v
Educational Engine
    interpretation of the learner and session
              |
              v
    CoachingRecommendationV1   (cites the observation)
```

This is Seam 4 from the four-engine model. The observation may not contain
*mastery*, *difficulty*, *coaching*, *curriculum recommendation*, or learner
classification. That restriction is enforced by a field allowlist and a governance
test, not by reviewer vigilance.

## Persistence

Raw captures, runtime health snapshots, and observations serialize deterministically
to JSON. Runtime session files are operational artifacts owned by the runtime; they
are never read as canonical music.

## Diagnostics

`RuntimeHealthV1` reports process, audio backend, audio output, MIDI input, synth,
session, and capture separately, split into infrastructure and session-scoped groups
as described under Diagram 7. Diagnostics are read-only and never mutate the
operating system.

## Recovery

## Diagram 8 — Runtime failure and recovery

```text
 capture in progress
        |
        | runtime dies
        v
  fault detected  ---------------------------------+
        |                                          |
        v                                          v
  close capture as INTERRUPTED               health -> FAILED
  attach fault to the capture                       |
        |                                           v
        v                                    operator/controller
  events accepted so far are PRESERVED       may restart runtime
        |                                           |
        v                                           v
  no note endings invented                    new session; prior
  no prior take overwritten                   capture untouched
  no canonical mutation
```

A crash is never represented as an ordinary stop.

## Offline mode

When `offline_required` is true, the configuration is rejected if it declares any
cloud dependency. Performance never requires network access to play, capture, or
save.

## Mobile control

The phone, tablet, or local web surface issues **product** commands
(`start_practice_recording`, `select_sound`, `record`, `save`) to Master All
Strings. It never issues backend commands (`load_lv2_uri`, `connect_port_1_to_bus_3`,
`create_ardour_route`) and never talks to the runtime process directly.

## Security boundary

Configuration is data, not code: no shell command in configuration is ever
executed. Utilities do not install software, download plugins, edit system audio
settings, scan arbitrary user directories, or open outbound network connections.
The OSC surface is a bounded command set, not arbitrary command execution. Raw MIDI
payload size is bounded.

## Licensing boundary

Every distributed component is registered with its distribution status before any
image is released. See
[EMBEDDED_PERFORMANCE_COMPONENT_REGISTER.md](../licensing/EMBEDDED_PERFORMANCE_COMPONENT_REGISTER.md).
Ardour source is referenced, not vendored.

## Replacement strategy

A future runtime is introduced by implementing `PerformanceRuntimePort` and
declaring its capabilities. Because runtimes differ in what they support, the
controller performs **capability discovery** rather than assuming a uniform feature
set. Replacing a runtime must not change canonical musical-event contracts,
performance-observation contracts, projection contracts, Creative contracts, or
Educational contracts (ADR-0007 D18). The staged path from this architecture to a
hybrid practice/studio product is in
[EMBEDDED_RUNTIME_STAGING.md](../planning/EMBEDDED_RUNTIME_STAGING.md).
