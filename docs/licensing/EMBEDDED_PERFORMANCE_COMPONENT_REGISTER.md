# Embedded Performance Component Register

Every component that would ship in a Performance Studio image, with its distribution
status. This is a **release gate** (ADR-0007 D16): no commercial image release is
authorized until every row is reviewed and no row is `UNRESOLVED`.

> **Status: nothing is approved.** Development availability is not redistribution
> approval (ADR-0007 D17). Most rows below are `UNRESOLVED` because no Pi image has
> been built and no component has been reviewed for distribution. A row that says
> `UNRESOLVED` is a question, not a problem — recording it is the point.

## Field definitions

```text
component            exact identity, not a category
version              exact version, not a range
purpose              why it would ship
license              SPDX identifier or explicit statement
source               where it came from
modified             have we changed it?
distribution_form    source | binary | image | not distributed
source_obligation    must we offer source?
notice_obligation    must we reproduce a notice?
commercial_status    APPROVED | UNRESOLVED | PROHIBITED
Pi_compatibility     VERIFIED | UNVERIFIED | INCOMPATIBLE
review_status        who reviewed it and when
evidence             what supports the entry
```

## Register

### Ardour source

```text
component            Ardour
version              9.7 (revision.cc: revision "9.7", date "2026-06-04")
purpose              First candidate performance runtime (transport, session,
                     capture, LV2 plugin hosting)
license              GPL-2.0 (COPYING in source tree)
source               Ardour-9.7.0.tar.bz2, 18,118,247 bytes,
                     SHA-256 5f3adf00b8991e25d8b8ccb503bf21010a1f08a121be14ca6039d309690ea98c
modified             NO - no source modification is authorized (ARDOUR_FORK_GATE.md)
distribution_form    NOT DISTRIBUTED - referenced as external source evidence only;
                     deliberately NOT vendored into this repository
source_obligation    UNRESOLVED - applies if a binary is ever distributed
notice_obligation    UNRESOLVED
commercial_status    UNRESOLVED
Pi_compatibility     UNVERIFIED - not built, not run, not measured on any platform
review_status        Source inspected 2026-07; not reviewed for distribution
evidence             docs/architecture/ARDOUR_ADAPTER_BOUNDARY.md
```

**Two open licensing questions, recorded rather than assumed away.** The GPL v2
covers the code. Independently, the Ardour name and logo are trademarked, and
`PACKAGER_README` restricts distributing VST-enabled builds under the name "ardour"
or any case variant. The build system carries a `--freebie` option described as
"Build a version suitable for distribution as a zero-cost binary." Code license and
branding do not travel together automatically. **This applies to distributing
unmodified Ardour in a commercial image, not only to forking.**

Why not vendored: committing 18 MB of GPL v2 C++ into a repository that is currently
pure Python with zero runtime dependencies would extend GPL distribution obligations
to this repository for no engineering benefit. The archive stays external; the
SHA-256 above is the provenance record.

### Raspberry Pi operating system

```text
component            Raspberry Pi OS
version              UNRESOLVED - no image selected
purpose              Host operating system for the Pi 5 appliance
license              UNRESOLVED - composite; requires per-package review
source               UNRESOLVED
modified             UNRESOLVED - appliance configuration will modify it
distribution_form    image (if a commercial image ships)
source_obligation    UNRESOLVED
notice_obligation    UNRESOLVED
commercial_status    UNRESOLVED
Pi_compatibility     n/a (it is the platform)
review_status        Not started
evidence             none
```

### Audio backend

```text
component            ALSA (candidate); PipeWire / JACK alternatives
version              UNRESOLVED
purpose              Audio device access; ALSA is the appliance candidate because it
                     needs no separate daemon (ADR-0007 D12)
license              UNRESOLVED
source               OS distribution
modified             NO
distribution_form    image
source_obligation    UNRESOLVED
notice_obligation    UNRESOLVED
commercial_status    UNRESOLVED
Pi_compatibility     UNVERIFIED
review_status        Not started
evidence             Ardour 9.7 libs/backends/{alsa,jack,pulseaudio,dummy} present
```

### MIDI backend

```text
component            ALSA MIDI (candidate)
version              UNRESOLVED
purpose              MIDI device input from guitar or guitar-to-MIDI device
license              UNRESOLVED
source               OS distribution
modified             NO
distribution_form    image
source_obligation    UNRESOLVED
notice_obligation    UNRESOLVED
commercial_status    UNRESOLVED
Pi_compatibility     UNVERIFIED
review_status        Not started
evidence             none
```

### Reference synthesizer (default)

```text
component            reasonablesynth.lv2
version              ships in-tree with Ardour 9.7
purpose              First-proof synthesizer. Selected because it requires NO
                     soundfont, so the acceptance path has no unresolved
                     sound-library licensing question at all.
license              UNRESOLVED - in-tree with Ardour; per-plugin license unverified
source               Ardour 9.7 libs/plugins/reasonablesynth.lv2
modified             NO
distribution_form    UNRESOLVED
source_obligation    UNRESOLVED
notice_obligation    UNRESOLVED
commercial_status    UNRESOLVED
Pi_compatibility     UNVERIFIED
measured_cpu         UNMEASURED
measured_memory      UNMEASURED
review_status        Identified 2026-07; license not yet read
evidence             Ardour 9.7 libs/plugins/ listing
```

### Reference synthesizer (secondary)

```text
component            a-fluidsynth.lv2
version              ships in-tree with Ardour 9.7
purpose              SF2 soundfont player. Better musical result, worse dependency
                     chain. NOT the acceptance-path synth.
license              UNRESOLVED - in-tree with Ardour; per-plugin license unverified
source               Ardour 9.7 libs/plugins/a-fluidsynth.lv2
modified             NO
distribution_form    UNRESOLVED
source_obligation    UNRESOLVED
notice_obligation    UNRESOLVED
commercial_status    UNRESOLVED
Pi_compatibility     UNVERIFIED
measured_cpu         UNMEASURED
measured_memory      UNMEASURED
review_status        Identified 2026-07
evidence             Ardour 9.7 libs/plugins/ listing
```

### Sound library / soundfont

```text
component            UNRESOLVED - no SF2 selected
version              UNRESOLVED
purpose              Would supply the actual instrument voice for a-fluidsynth
license              UNRESOLVED - soundfont licensing varies widely and is a common
                     source of redistribution problems
source               UNRESOLVED
modified             UNRESOLVED
distribution_form    UNRESOLVED
source_obligation    UNRESOLVED
notice_obligation    UNRESOLVED
commercial_status    UNRESOLVED
Pi_compatibility     UNVERIFIED
review_status        Not started - deliberately deferred
evidence             none
```

Deferring this is why `reasonablesynth.lv2` is the default: the first proof needs a
controlled dependency chain more than it needs a good guitar tone. A musically
preferred voice is a separate component and licensing decision, made later.

### Fonts

```text
component            UNRESOLVED - none selected
version              UNRESOLVED
purpose              Notation and TAB rendering, UI text
license              UNRESOLVED - music fonts frequently carry embedding restrictions
source               UNRESOLVED
modified             UNRESOLVED
distribution_form    UNRESOLVED
source_obligation    UNRESOLVED
notice_obligation    UNRESOLVED
commercial_status    UNRESOLVED
Pi_compatibility     UNVERIFIED
review_status        Not started
evidence             none
```

### Control interface (optional)

```text
component            UNRESOLVED - phone/tablet/web surface not selected
version              UNRESOLVED
purpose              Primary display and control (ADR-0007 D13)
license              UNRESOLVED
source               UNRESOLVED
modified             UNRESOLVED
distribution_form    UNRESOLVED
source_obligation    UNRESOLVED
notice_obligation    UNRESOLVED
commercial_status    UNRESOLVED
Pi_compatibility     UNVERIFIED
review_status        Not started
evidence             Ardour 9.7 libs/surfaces/{websockets,mcp_http} exist but are
                     Ardour's own surfaces, not a product UI
```

### Master All Strings configuration

```text
component            Performance runtime configuration and session template
version              v1 (this tranche)
purpose              Declarative runtime configuration (ADR-0007 D14)
license              MIT (this repository)
source               resources/performance/
modified             n/a - authored here
distribution_form    image
source_obligation    none
notice_obligation    none
commercial_status    APPROVED - our own work under the repository license
Pi_compatibility     UNVERIFIED
review_status        Authored DO-006
evidence             resources/performance/
```

Ardour ships no usable session template — `share/templates/` in the 9.7 source
contains only `.stub` — so the template is our own work rather than a derivative.

## Summary

| Status | Count |
| --- | --- |
| `APPROVED` | 1 (our own configuration) |
| `UNRESOLVED` | 9 |
| `PROHIBITED` | 0 |
| Pi compatibility `VERIFIED` | 0 |
| Components measured on target hardware | 0 |

**Release gate: CLOSED.** No commercial image release is authorized.

## Review procedure

For each `UNRESOLVED` row, in this order: identify the exact component and version;
read its actual license text rather than assuming from the project's headline
license; determine whether the distribution form triggers source or notice
obligations; verify Pi compatibility on target hardware; measure CPU and memory; and
record the reviewer and date. A row moves to `APPROVED` only when every field is
filled from evidence.
