# Ardour Fork Gate

Whether Master All Strings may modify Ardour source, and what must be true first.

## Current ruling

```text
DEFER_FORK_PENDING_EVIDENCE
```

**No Ardour fork is authorized.** No Ardour source modification is authorized. This
ruling stands until the evidence below exists, and it cannot be changed by a Dev
Order, an implementation decision, or a reviewer — only by separate owner
authorization.

Why `DEFER` rather than `NO_FORK_REQUIRED`: the honest answer is that we do not yet
know. Two gaps are recorded ([ARDOUR_GAP_AUDIT.md](ARDOUR_GAP_AUDIT.md)), zero of nine
escalation rungs have been exercised, and no Ardour runtime has been started. Claiming
"no fork required" would assert a conclusion the evidence does not support, in the same
way that claiming a fork is needed would.

## Possible rulings

| Ruling | Meaning |
| --- | --- |
| `NO_FORK_REQUIRED` | Every required workflow is achievable through supported interfaces. Demonstrated, not assumed. |
| `DEFER_FORK_PENDING_EVIDENCE` | Insufficient evidence either way. The escalation ladder is not exhausted. **← current** |
| `FORK_CANDIDATE` | A blocking gap survives an exhausted ladder. Requires separate authorization; does not itself authorize a fork. |
| `FORK_PROHIBITED` | Forking is ruled out regardless of gaps — for licensing, maintenance, or strategic reasons. |

## Escalation ladder (ADR-0007 D3)

A fork may not be discussed until every rung above it has been **exercised and
documented**, not merely considered.

| # | Rung | Exercised? |
| --- | --- | --- |
| 1 | Unmodified Ardour | ☐ no runtime has been started |
| 2 | Prepared Ardour session | ☐ |
| 3 | Ardour configuration | ☐ |
| 4 | OSC control | ☐ source read only |
| 5 | MIDI routing | ☐ |
| 6 | Supported scripting (Lua) | ☐ |
| 7 | Sidecar adapter | ☐ |
| 8 | Master All Strings UI compensation | ☐ |
| 9 | Documented gap audit | ◐ structure exists; 2 source-derived gaps, 0 tested |
| 10 | **Separate fork authorization** | ☐ **not sought, not granted** |

## Requirements for a `FORK_CANDIDATE` ruling

All eight must be satisfied and recorded. Any one missing keeps the ruling at
`DEFER_FORK_PENDING_EVIDENCE`.

1. **A blocking workflow gap** — severity `BLOCKING` in the gap audit, tied to a
   workflow the product genuinely requires, not one that is merely convenient.
2. **Evidence that supported interfaces were exhausted** — every ladder rung tried,
   with the result recorded. "We did not try Lua" is disqualifying.
3. **Maintenance estimate** — the ongoing cost of carrying a patch across Ardour
   releases, in hours per release and who pays them.
4. **Security review** — what the modification changes about the runtime's exposure.
5. **License review** — GPL v2 obligations for distributing a modified work, including
   source-offer requirements and the trademark position (see below).
6. **Upgrade strategy** — how the patch is rebased, and what happens when upstream
   changes the code it touches.
7. **Rollback plan** — how to return to unmodified Ardour if the fork proves
   unsustainable.
8. **Separate owner authorization** — explicit, recorded, and specific to the gap. A
   general approval to "work on Ardour integration" is not authorization to fork.

## Licensing position

Ardour 9.7 is **GNU GPL v2** (`COPYING` in the source tree). Distributing a modified
Ardour triggers GPL source-availability obligations for the modified work.

Separately and independently of the code license, the Ardour **name and logo are
trademarked**, and the `PACKAGER_README` in the source explicitly restricts
distributing a VST-enabled build under the name "ardour" or any case variant. The
build system also carries a `--freebie` option described as "Build a version suitable
for distribution as a zero-cost binary." The code license and the branding do not
travel together automatically.

None of that is resolved. It is recorded in the
[component register](../licensing/EMBEDDED_PERFORMANCE_COMPONENT_REGISTER.md) as an
open question, and it applies to *distribution* — including distribution of an
unmodified Ardour inside a commercial Pi image, which is a licensing question the
product faces whether or not it ever forks.

## Why the bar is deliberately high

A fork is not a technical decision that happens to have costs; it is a permanent
maintenance commitment traded for a short-term unblock. Once a patch exists, every
Ardour release becomes a rebase, every upstream refactor is a risk, and the option to
replace Ardour with a different runtime — the entire point of ADR-0007 D18 — quietly
gets harder because product behavior now depends on a modification only we have.

The cheapest moment to avoid that is before the first patch. That is what this gate
is for.

## Review triggers

This ruling is re-examined when any of these occurs, and at no other time:

- the Commit 8 desktop spike completes and records tested dispositions;
- the Commit 9 Pi spike completes;
- a gap is raised to severity `BLOCKING` with the ladder exhausted;
- Ardour releases a major version outside the `>=9.7,<10` policy;
- the licensing register resolves the distribution question in either direction;
- the runtime strategy changes (for example, Outcome C in
  [EMBEDDED_RUNTIME_STAGING.md](EMBEDDED_RUNTIME_STAGING.md)).
