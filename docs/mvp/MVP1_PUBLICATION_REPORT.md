# Master All Strings MVP 1 — Publication Report

Dev Order: **DO-010A** then **DO-010A-R** (topology repair + re-certification)

## Status

```text
RECERTIFICATION_GATES_GREEN_PENDING_TAG
```

## PR #18 squash-merge incident

PR [#18](https://github.com/HanzoRazer/Master-All-Strings/pull/18) was **squash-merged** into
`main` as:

```text
a198c7b30370d077e7213b4ebeab170c769aaaff
```

That commit preserved the intended **tree** but destroyed the certified **ancestry**:
DO-008 → DO-009 → original product → evidence became unreachable from `main`.

Tag creation for `mvp-1` was **halted** because a squash tip is not release authority.

### Topology repair (completed before DO-010A-R resumed)

Stages 1–3 of DO-010A-R were completed prior to this tranche resume and are **not**
replayed:

| Item | Value |
| --- | --- |
| Recovery ref | `recovery/mvp1-squash-merge` → `a198c7b…` |
| Repair method | force-update `main` → intact `release/mvp-1` tip |
| Tree check | `git diff a198c7b origin/release/mvp-1` empty |
| Repaired tip at resume | `2f8c0f05ae1fff4c9fd665111a097cc758d426a7` |
| Squash as release head | **no** (preserved only via recovery ref) |

Certified SHAs are again reachable from `main` / `release/mvp-1`.

## What this publication is

Fast-forward publication of the certified MVP 1 lineage onto `main`, plus
publication metadata and an explicit post-freeze capture correctness patch that
requires re-certification.

| Field | SHA / value |
| --- | --- |
| `original_product_sha` | `7a9b68455b84b065fcd6b184c0903b292d090ef7` |
| `original_release_evidence_sha` | `b727cce6da108667d7dc1823df17f85cdeb9d810` |
| `corrected_product_sha` | `f028549b145bf3f567e936d5d7e29ab2f93f63d3` (Web MIDI velocity-0 note-off + session map reset) |
| `recertification_evidence_sha` | `d1761d93f2dbbfde4f0551dd981a0d4c064d4749` |
| `final_release_sha` / `mvp-1` | *pending after green gates* |

## Correctness patch (retained, not grandfathered)

`f028549b145bf3f567e936d5d7e29ab2f93f63d3` (`f028549`) remains in MVP 1 and is treated as `PRODUCT_CORRECTNESS_PATCH`:

1. MIDI `0x90` + velocity `0` → `NOTE_OFF`
2. Capture `repetitions` / `practice_onsets` cleared on start and after close

These change Performance capture semantics relative to `7a9b684`, so the final
release product identity is **`corrected_product_sha = f028549`**, not the original
product SHA.

## Classifier hardening (DO-010A-R)

- `governance/engine_architecture_v1.json` (and other `governance/` sources) →
  `ARCHITECTURE_DIFFERENCE` (fails publication compare unless authorized)
- `docs/architecture/ENGINE_*` → `GENERATED_GOVERNANCE_ONLY_DIFFERENCE`
- Correctness allowlist remains narrow to the reviewed capture API paths only

## Topology

| Item | Value |
| --- | --- |
| Implementation branch | `feat/do-010-mvp-completion` |
| Publication branch | `release/mvp-1` |
| Preferred merge | true fast-forward into `main` (no squash; no rebase) |
| Release tag | `mvp-1` (immutable; create only after DO-010A-R gates) |

## Verified lineage (required)

```text
f9018213  DO-008
    ↓
92f0f80   DO-009
    ↓
7a9b684   original MVP 1 product
    ↓
b727cce   original MVP 1 evidence
    ↓
f028549   corrected product (capture correctness)
    ↓
publication / classifier / docs tooling
    ↓
<recertification evidence>
    ↓
final release tip → tag mvp-1
```

## Explicit exclusions

- `feat/do-009-live-midi-alignment` / `03477a2`
- treating `a198c7b` as release SHA or tag target
- Windows deterministic-newline work (deferred to DO-010B)
- any new MVP product capability
