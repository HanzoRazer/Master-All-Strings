# Ardour adapter (scaffold)

**Status: not implemented.** No Ardour runtime has been built, started, or measured.
`adapter.build_ardour_runtime()` always raises.

Constitutional position: Ardour is one implementation of a replaceable audio
infrastructure layer, not an engine and not an authority
([ADR-0007](../../../../../docs/decisions/ADR-0007-EMBEDDED-PERFORMANCE-RUNTIME.md)).
Everything in this package is adapter-private and may not cross
`PerformanceRuntimePort`.

## What exists

| Module | Purpose | State |
| --- | --- | --- |
| `models.py` | Adapter-private Ardour types; version policy `>=9.7,<10` | usable |
| `osc_client.py` | Bounded OSC command surface, transport injected | usable, no wire layer |
| `process.py` | Process and version-detection boundary | usable, test-double driven |
| `adapter.py` | The port implementation | **raises** |

## Why the OSC surface is bounded

`osc_client` exposes a closed set of named operations, not an arbitrary path sender.
An open bridge would let any caller reach anything Ardour exposes, which would make
the adapter boundary decorative. Paths were extracted from
`libs/surfaces/osc/osc.cc` in Ardour 9.7 source.

Two required operations have no path at all, and are recorded as absent rather than
approximated:

- **GAP-001** — no OSC tempo or meter control. Every `tempo` occurrence in `osc.cc`
  is `temp_mode`/`TempOff`, a control-surface concept unrelated to musical tempo.
- **GAP-002** — no OSC version path, which is why version detection lives in
  `process.py` instead.

A methodological note for whoever extends this: OSC paths register two ways, as
`REGISTER_CALLBACK` literals *and* via dynamic sub-path dispatch. `/strip/recenable`
exists only through the dynamic route and never appears as a literal string, so a
grep-only audit under-reports the surface.

## What must happen before `adapter.py` is written

1. The fake adapter and contract suite are stable — done.
2. Ardour builds and runs on a Linux target. The `dummy` audio backend allows
   partial validation without an audio interface.
3. GAP-001 and GAP-002 get tested dispositions, trying configuration, then Lua, then
   sidecar, in that order.
4. Findings enter [ARDOUR_GAP_AUDIT.md](../../../../../docs/planning/ARDOUR_GAP_AUDIT.md).

## What is forbidden here

No Ardour source modification (fork disposition is `DEFER_FORK_PENDING_EVIDENCE`), no
installing Ardour, no downloading plugins, no editing system audio settings, no
arbitrary OSC path execution, no reading Ardour session files as canonical music, and
no Ardour type in any signature reachable from outside this package.
