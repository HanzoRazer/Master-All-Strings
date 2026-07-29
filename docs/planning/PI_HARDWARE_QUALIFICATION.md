# Raspberry Pi Hardware Qualification

Measurement template for the DO-006 Commit 9 target-hardware tranche.

> **STATUS: NOT EXECUTED. EVERY VALUE BELOW IS `UNMEASURED`.**
>
> No Ardour runtime has been built, started, or measured on any platform. This
> document exists so the measurements have a defined shape before anyone takes them —
> not because any of them have been taken.
>
> **No value here may be filled in from a Windows or macOS machine.** Thresholds are
> set from measured evidence on the target, never invented in an architecture commit
> (DO-006 §8.9). A plausible-looking number from the wrong platform is worse than an
> empty cell, because it reads as proof.

## Test environment (record before measuring)

```text
pi_model                 UNRECORDED   (target: Raspberry Pi 5)
pi_memory                UNRECORDED
storage                  UNRECORDED
power_supply             UNRECORDED
cooling                  UNRECORDED   (passive / active / none)
os_image                 UNRECORDED
kernel                   UNRECORDED
audio_backend            UNRECORDED   (alsa expected)
audio_interface          UNRECORDED
midi_device              UNRECORDED
ardour_version           UNRECORDED   (policy >=9.7,<10)
ardour_build_flags       UNRECORDED
synth                    UNRECORDED   (reasonablesynth.lv2 expected)
sample_rate_hz           UNRECORDED
buffer_frames            UNRECORDED
ambient_temperature      UNRECORDED
measured_by              UNRECORDED
measured_on              UNRECORDED
```

## Measurements

| # | Metric | Unit | Target | Measured | Method |
| --- | --- | --- | --- | --- | --- |
| 1 | Boot to ready | s | TBD from evidence | `UNMEASURED` | power-on to controller reporting ready |
| 2 | Runtime start time | ms | TBD | `UNMEASURED` | start command to READY |
| 3 | Synth load time | ms | TBD | `UNMEASURED` | select_synth to success |
| 4 | MIDI-to-audio latency | ms | TBD | `UNMEASURED` | external measurement; see below |
| 5 | Timestamp jitter | µs | TBD | `UNMEASURED` | stddev of inter-event intervals for a fixed-rate source |
| 6 | CPU usage (idle) | % | TBD | `UNMEASURED` | runtime ready, no playback |
| 7 | CPU usage (capture) | % | TBD | `UNMEASURED` | sustained capture |
| 8 | Memory (RSS) | MB | TBD | `UNMEASURED` | peak during capture |
| 9 | Thermal state | °C | TBD | `UNMEASURED` | peak SoC temperature over the stability run |
| 10 | Thermal throttling | bool | must be false | `UNMEASURED` | throttle flags during stability run |
| 11 | Audio underruns | count/hr | TBD | `UNMEASURED` | backend xrun counter |
| 12 | One-hour stability | pass/fail | must pass | `UNMEASURED` | continuous capture, no fault, no underrun growth |
| 13 | Recovery time | s | TBD | `UNMEASURED` | kill runtime → controller usable again |
| 14 | Offline behavior | pass/fail | must pass | `UNMEASURED` | full flow with networking disabled |

**Targets are `TBD` on purpose.** Filling them in before measuring would invert the
method: the acceptable buffer size, latency, and thermal ceiling are conclusions from
the data, not premises. The one exception is the two boolean rows, which are product
requirements rather than performance figures.

### Latency measurement note

MIDI-to-audio latency cannot be measured from inside the system being measured. It
needs an external capture of the MIDI trigger and the resulting audio on a common
timebase — a second interface, a scope, or a loopback recording. A figure derived
from software timestamps alone measures the software path, not what the player hears,
and must be labelled as such if recorded at all.

## Acceptance criteria for the target-hardware tranche

Independent of the numbers above; these are pass/fail.

| # | Criterion | Status |
| --- | --- | --- |
| 1 | MIDI input works on the Pi | `NOT VERIFIED` |
| 2 | Synth output is audible | `NOT VERIFIED` |
| 3 | Capture succeeds | `NOT VERIFIED` |
| 4 | Raw events transfer into Musical Core | `NOT VERIFIED` (blocked: Core ingestion is a later Dev Order) |
| 5 | Piano roll displays the canonical result | `NOT VERIFIED` (blocked: projection not implemented) |
| 6 | Notation projects from the same revision | `NOT VERIFIED` (blocked) |
| 7 | TAB projects from the same revision | `NOT VERIFIED` (blocked) |
| 8 | Offline operation works | `NOT VERIFIED` |
| 9 | Failure is recoverable | `NOT VERIFIED` |
| 10 | Gap audit complete | `PARTIAL` — 2 source-derived gaps, 0 tested |
| 11 | Fork ruling recorded | `DEFER_FORK_PENDING_EVIDENCE` |

Criteria 4–7 are blocked on Musical Core work, not on hardware. Even a fully
successful Pi spike cannot close them, because there is nothing yet for a capture to
be ingested *into*. That dependency is stated here so a hardware session is not
planned around closing them.

## Recording results

Append a dated results block per run rather than overwriting this template. A
measurement is only meaningful alongside the environment that produced it, and a
regression is only visible if the previous run survives.
