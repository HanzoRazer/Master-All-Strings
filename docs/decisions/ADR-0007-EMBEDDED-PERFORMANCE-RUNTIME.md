# ADR-0007 — Embedded Performance Runtime

- **Status:** Proposed
- **Owner:** DO-006
- **Engine:** Performance Engine
- **Supersedes:** nothing
- **Depends on:** [ADR-0006](ADR-0006-FOUR-ENGINE-ARCHITECTURE.md) (four-engine architecture), [ADR-0003](ADR-0003-MUSIC-CANONICAL.md) (music is canonical)

## Problem

The Smart Guitar needs an embedded runtime that can make sound and record a
performance: a player plugs in a guitar or a guitar-to-MIDI device, hears a
software synthesizer, records what they played, and sees it back as a piano roll,
as standard notation, and as TAB.

Nothing in this repository does that today. Musical Core owns the canonical music
and the semantic projections; the Performance Engine owns capture, playback, and
device integration — but the Performance Engine currently has no contracts, no
port, and no implementation. The first candidate runtime is Ardour hosted on a
Raspberry Pi 5.

Two failure modes are available to us, and both are expensive to reverse:

1. **Master All Strings becomes a general-purpose DAW.** Once a product can record
   audio, the pull toward mixing, buses, automation lanes, comping, and mastering
   is constant, and every one of those features is defensible in isolation. The
   result is a worse version of software that already exists, built by a team whose
   actual advantage is guitar semantics.
2. **Ardour becomes the owner of the music.** If an Ardour session file is where a
   performance lives, then Ardour — not Musical Core — is the canonical store, and
   notation, TAB, MSME, and curriculum all become downstream of a third-party
   session format we do not control.

## Context

The exploratory work that led here was framed as "can Ardour run on a Pi?" That
was the wrong question, and its answer would have been the less useful result. The
question it actually answered was:

> Where is the constitutional boundary between the product and the audio engine?

That reframing is the substance of this ADR. Ardour is not a candidate *component*
of Master All Strings; it is one implementation of an **audio infrastructure
layer** that sits strictly below the four engines:

```text
                    Master All Strings

        Musical Core        (canonical music, projections)
             |
     Creative Engine        (authoring)
             |
   Educational Engine       (interpretation, coaching)
             |
    Performance Engine      (capture, playback, device integration)
             |
             v
    Audio Infrastructure Layer          <-- replaceable, owns no music
      +-- Ardour (first adapter)
      +-- PipeWire / JACK / ALSA
      +-- LV2 plugin hosting
      +-- future lightweight runtime
```

Ardour is exceptionally good at transport, session management, recording, routing,
plugin hosting, editing, and export. It knows nothing about guitars, tunings,
fingering, TAB, MSME, curriculum, or pedagogy. Those are precisely what Master All
Strings already owns. The boundary is therefore not a compromise; it follows the
competence split that already exists.

### Source inspected

Ardour 9.7 source (`libs/ardour/revision.cc` → revision `9.7`, date `2026-06-04`,
GPL v2, SHA-256 `5f3adf00b8991e25d8b8ccb503bf21010a1f08a121be14ca6039d309690ea98c`)
was inspected to ground this decision in the actual integration surface rather than
in documentation. The tree confirms an OSC control surface, a generic-MIDI surface,
Lua scripting, a headless build target, session utilities, ALSA and dummy audio
backends, WebSocket control, LV2 plugin hosting, and two in-tree LV2 synthesizers.
See [ARDOUR_ADAPTER_BOUNDARY.md](../architecture/ARDOUR_ADAPTER_BOUNDARY.md).

The archive is **not vendored** into this repository. It is recorded as external
source evidence in the
[component register](../licensing/EMBEDDED_PERFORMANCE_COMPONENT_REGISTER.md).
Source presence proves an interface exists; it does not prove the interface works.
No Ardour runtime has been built, run, or measured.

## Decision

### D1 — The subsystem is the Embedded Performance Runtime

Architectural name: **Embedded Performance Runtime**. Product-facing name:
**Performance Studio**. The term *DAW Lite* is not used in constitutional documents
or public contracts, because it describes the product by what it is a reduced
version of, and invites exactly the scope expansion this ADR exists to prevent.

The governing boundary:

> The Performance Studio plays, captures, displays, and transfers musical
> performance events. It is not a general-purpose audio-production environment.

### D2 — Ardour is replaceable infrastructure, not an authority

Ardour is the initial runtime candidate and nothing more. It is not a fifth engine,
not a constitutional authority, not the canonical score store, and not the owner of
notation, TAB, or coaching. Master All Strings contracts remain runtime-neutral:
`PerformanceRuntime`, `PerformanceSession`, `TransportState`, `RuntimeHealth`,
`CapturedMidiEvent`. Ardour-specific vocabulary (`ArdourSession`, `ArdourRegion`,
`ArdourTransportState`) is confined to the adapter package and may not cross
`PerformanceRuntimePort`. This is enforced by test, not by convention alone.

### D3 — Integration before modification

Escalation order, exhausted in sequence: unmodified Ardour → prepared session →
configuration → OSC → MIDI routing → supported scripting → sidecar adapter →
Master All Strings UI compensation → documented gap audit → separate fork
authorization. **No source-level Ardour modification is authorized by this ADR.**

### D4 — Process separation is the default

Master All Strings and the runtime are separate processes communicating over
runtime-neutral IPC (OSC, MIDI ports, local files, supported scripting,
process-health inspection). Direct linkage to Ardour internals is not authorized.

### D5 — Musical Core remains canonical

```text
Guitar MIDI -> RawPerformanceCaptureV1 -> canonical ingestion request
            -> Musical Core revision -> piano roll / notation / TAB / MIDI
```

A runtime session file is an operational artifact. It is not the canonical Master
All Strings score. The Performance Engine may *reference* a canonical revision
identifier after Musical Core supplies it; it may not mint one, may not treat a
runtime session ID as one, and may not implement a competing revision model.

### D6 — Raw evidence is preserved

Raw capture survives quantization, cleanup, notation interpretation, TAB fingering
assignment, Creative edits, and Educational analysis. Derived records cite the raw
capture; they never replace it. Capture is immutable once closed.

### D7 — String identity is never invented

If a divided pickup or per-string MIDI source supplies string identity, it is
preserved. If it does not, `source_string` remains unresolved. An inferred string
is a projection, produced later by Musical Core, and is never recorded as observed
fact.

### D8 — The piano roll is not a second score model

The piano roll is a projection and an interaction surface that produces validated
canonical edit commands. It maintains no independent authoritative note collection.
The semantic projection is owned by **Musical Core** (`piano-roll-projection`); the
interactive editing experience is owned by **Creative Engine**; the Performance
Engine may display a projection during review via `ProjectionResultV1` but owns no
note model.

### D9 — Notation and TAB remain Musical Core projections

Piano roll, notation, and TAB are three interpretations of one canonical revision
and must all cite the same revision identifier.

### D10 — Performance emits evidence, not coaching

Performance may report notes captured, timing, duration, velocity, missing
note-offs, latency, device faults, and interrupted capture. It may not report
*beginner*, *poor technique*, *mastered*, *too difficult*, or any curriculum
recommendation. That is Educational Engine authority under Seam 4.

### D11 — Direct guitar-audio pitch detection is deferred

The first runtime accepts MIDI from a MIDI guitar, divided pickup, external
audio-to-MIDI hardware or software, or test fixtures. Native polyphonic
audio-to-MIDI conversion is a separate R&D program.

### D12 — Appliance mode is the primary experience

Normal use requires no Ardour window, no manual JACK or PipeWire configuration, no
track creation, no manual routing, no plugin scanning, no terminal, and no
understanding of DAW buses. The user experience is: power on, select sound, play,
record, review, save.

### D13 — A phone or tablet may be the primary display

The Pi requires no attached display. Mobile, tablet, local web, desktop, hardware
controls, and MIDI control messages are all permitted control surfaces.

### D14 — Configuration is declarative

Runtime configuration is versioned data, validated against a schema. It does not
depend on undocumented shell history or hand-built sessions.

### D15 — Runtime failure cannot create false canonical data

A crash may not mark a partial session complete, invent note endings, overwrite a
prior take, silently discard accepted raw events, or mutate canonical music.
Interrupted sessions are explicit.

This binds every abnormal end, not only a crash. Stopping the runtime while a capture
is active closes that capture as `INTERRUPTED` too — abandoning it would leave a
record permanently `IN_PROGRESS`, claiming to be recording on a runtime that no
longer exists.

Readiness is reported as two questions rather than one: whether the runtime accepts
commands, and whether a session exists such that capture may begin. Health separates
its subsystems the same way. Collapsing them would make `start` → `readiness` →
`prepare session` unreachable, since the session subsystem cannot be ready before the
step that creates it.

### D16 — Licensing is a release gate

Every distributed component — Ardour, OS image, audio and MIDI services, synth,
sound library, fonts, support applications, configuration, and any modification —
is recorded with its distribution status. No commercial image release is authorized
until the register is reviewed.

### D17 — Plugin approval is explicit

Development availability is not redistribution approval. Every bundled synth or
sound library carries exact identity, version, license, source, Pi compatibility,
measured resource use, and distribution status.

### D18 — Runtime replacement must remain possible

A future runtime must be replaceable without changing canonical musical-event
contracts, performance-observation contracts, projection contracts, Creative
contracts, or Educational contracts.

## Consequences

**Accepted willingly.** The adapter boundary costs indirection: every runtime
capability is expressed twice, once as a neutral contract and once as an adapter
translation. Capability discovery is required because runtimes differ in what they
support. A fake runtime must be maintained alongside every real one. This is the
price of D18, and it is cheaper than a migration after coupling.

**Accepted with open risk.** Ardour is GPL v2 and its name and logo are trademarked;
the code license and the branding do not travel together automatically. Commercial
distribution of a Pi image is therefore gated on the component register, not on this
ADR. The `--freebie` build option and the `PACKAGER_README` naming restriction are
recorded as unresolved licensing questions, not as solved ones.

**Deferred deliberately.** No Ardour runtime has been built or measured. Every
latency, jitter, thermal, underrun, and stability figure required by the target
hardware gate is `UNMEASURED`. The fork disposition is `DEFER_FORK_PENDING_EVIDENCE`.
This ADR is architecture; it changes no production behavior.

**Enabled.** Because the boundary is explicit, Ardour can change, PipeWire can
change, JACK can disappear, and a lightweight runtime can take over the daily
practice path — none of which affects MSME, notation, TAB, curriculum, coaching, or
instrument intelligence. The staging plan for that evolution is
[EMBEDDED_RUNTIME_STAGING.md](../planning/EMBEDDED_RUNTIME_STAGING.md).

## Rejected alternatives

**Build a DAW.** Rejected: it spends the project's scarce effort rebuilding
multitrack persistence, non-destructive editing, plugin automation, routing,
timeline editing, export, undo graphs, and crash recovery — all of which exist,
work, and are not the product's differentiation.

**Adopt Ardour as the product architecture.** Rejected: it makes a third-party
session format the canonical musical store, couples the roadmap to an external
project's decisions, and imports a GPL and trademark posture into the product's
core rather than into a replaceable layer.

**Fork Ardour now.** Rejected: no gap has been demonstrated, because no supported
interface has been exercised. D3's escalation ladder must be exhausted first, with
evidence, and a fork requires separate authorization under
[ARDOUR_FORK_GATE.md](../planning/ARDOUR_FORK_GATE.md).

**Name Ardour in the constitutional contracts.** Rejected: it is the specific drift
D18 forbids, and it would have to be undone by the first runtime replacement.

**Make the piano roll a Performance-owned note model.** Rejected under D8: a
Performance-owned editable note collection is one refactor away from being a second
authoritative score, competing with Musical Core.

**Defer the architecture until hardware is available.** Rejected: runtime code
written before the boundary exists is what produces the coupling this ADR prevents.
The fake runtime proves the architecture without hardware.
