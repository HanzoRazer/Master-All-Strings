# Ardour Gap Audit

Every workflow Master All Strings needs that unmodified Ardour does not provide
through a supported interface. This is the evidence base for
[ARDOUR_FORK_GATE.md](ARDOUR_FORK_GATE.md): a fork may only be considered for gaps
recorded here with the escalation ladder demonstrably exhausted.

> **Status: source-inspection only.** Two gaps below were found by reading Ardour 9.7
> source. **No Ardour runtime has been built, started, or exercised**, so no gap has a
> tested disposition and no mitigation has been proven to work. `interface_attempted`
> is `NONE` for every row. Executable verification is the Commit 8 desktop spike,
> which has not run.

## Record format

Each gap carries these fields:

```text
gap_id                   stable identifier, never reused
required_workflow        what the product needs
observed_behavior        what Ardour does, and how we know
expected_behavior        what the product needs instead
target_runtime_version   which Ardour revision the observation applies to
interface_attempted      which escalation rungs have actually been exercised
configuration_possible   session template / config can solve it?
OSC_possible             OSC surface can solve it?
MIDI_possible            MIDI control can solve it?
script_possible          Lua scripting can solve it?
sidecar_possible         an external helper process can solve it?
UI_compensation_possible Master All Strings UI can absorb it?
source_change_required   is modifying Ardour the only remaining option?
severity                 BLOCKING | MAJOR | MINOR | COSMETIC
evidence                 file:line or measurement reference
disposition              how it is resolved, or OPEN
```

`*_possible` values are `YES` (demonstrated), `CANDIDATE` (plausible, untested),
`NO` (ruled out with evidence), or `UNKNOWN`.

---

## GAP-001 — No tempo or meter control over OSC

```text
gap_id                   GAP-001
required_workflow        Set session tempo and meter (DO-006 §3.2 first target)
observed_behavior        Ardour 9.7's OSC surface exposes no tempo or meter path.
                         Every "tempo" occurrence in osc.cc is temp_mode / TempOff,
                         a control-surface temporary mode unrelated to musical tempo.
expected_behavior        The adapter can set tempo and meter for a prepared session,
                         and ideally change tempo between takes.
target_runtime_version   9.7
interface_attempted      NONE (source inspection only)
configuration_possible   CANDIDATE - a prepared session template can carry tempo and
                         meter, which covers the first proof but not mid-session change
OSC_possible             NO - no such path exists in the 9.7 surface
MIDI_possible            CANDIDATE - MIDI clock / song position is a different mechanism
                         with its own semantics; not equivalent to setting session tempo
script_possible          CANDIDATE - Lua has session access; untested
sidecar_possible         CANDIDATE - /access_action can invoke named Ardour actions;
                         no specific tempo action has been identified
UI_compensation_possible CANDIDATE - Master All Strings can present tempo per take and
                         prepare a template per tempo, avoiding live change entirely
source_change_required   NO - not established; three unexercised rungs remain
severity                 MAJOR (first proof survives via template; live tempo does not)
evidence                 libs/surfaces/osc/osc.cc - no tempo/meter path among either
                         REGISTER_CALLBACK literals or dynamic sub-path dispatch
disposition              OPEN - resolve at Commit 8 by testing template, Lua, and
                         access_action in that order
```

---

## GAP-002 — No runtime version identification over OSC

```text
gap_id                   GAP-002
required_workflow        Identify the running Ardour version and reject unsupported
                         majors with an explicit compatibility fault (adapter boundary,
                         version policy >=9.7,<10)
observed_behavior        The 9.7 OSC surface exposes no version path.
expected_behavior        The adapter can determine the runtime version before trusting
                         any other command.
target_runtime_version   9.7
interface_attempted      NONE (source inspection only)
configuration_possible   NO - configuration states the expected version; it cannot
                         observe the actual one
OSC_possible             NO - no such path exists in the 9.7 surface
MIDI_possible            NO - wrong channel for this concern
script_possible          CANDIDATE - Lua can report the Ardour version; untested
sidecar_possible         CANDIDATE - process inspection (`ardour --version`) out of band
UI_compensation_possible NO - this is a safety check, not a presentation concern
source_change_required   NO - two unexercised rungs remain
severity                 MAJOR (proceeding against an unknown version risks
                         misinterpreting every later command)
evidence                 libs/surfaces/osc/osc.cc - no version path
disposition              OPEN - resolve at Commit 8; process inspection is the expected
                         answer and needs no Ardour change
```

---

## Gaps awaiting executable verification

The following cannot be assessed by reading source. Each becomes a gap record only if
the Commit 8 desktop spike or the Commit 9 Pi spike demonstrates a shortfall. Listing
them here is a checklist, **not** a claim that a gap exists.

| Candidate area | Why source inspection cannot settle it |
| --- | --- |
| Capture extraction fidelity | Where and how Ardour writes captured MIDI, and whether original timing survives, is runtime behavior |
| Readiness signalling | Whether OSC feedback arrives reliably and in what order |
| Synth load failure reporting | Whether a failed LV2 load is distinguishable from a slow one |
| Panic completeness | Whether `/midi_panic` clears every stuck note in every state |
| Interrupted-capture behavior | What Ardour leaves behind after a crash mid-record |
| Session template stability | Whether a prepared template survives Ardour version drift |
| Startup time | Measurement |
| Latency, jitter, underruns, thermals | Measurement, target hardware only |

## Summary

| Metric | Value |
| --- | --- |
| Gaps recorded | 2 |
| Gaps with tested disposition | 0 |
| Gaps requiring an Ardour source change | 0 |
| Escalation rungs exercised | 0 of 9 |
| Fork disposition | `DEFER_FORK_PENDING_EVIDENCE` |

No gap currently justifies modifying Ardour. Both recorded gaps have unexercised
mitigations at the configuration, scripting, or sidecar level — which is exactly the
situation ADR-0007 D3 requires be exhausted before a fork is even discussed.
