# Master All Strings MVP 1 — Publication Report

Dev Order: **DO-010A** (controlled publication of the certified MVP 1 lineage)

## Status

```text
PR_OPEN_REVIEW_BLOCKERS_ADDRESSED
```

Local release-candidate verification passed. Review blockers for MIDI note-off
classification, capture session map reset, and honest tree-compare labeling are
addressed on this branch. Next steps remain CI, review, fast-forward merge when
permitted, and immutable tag `mvp-1`.

## What this PR is (accurate framing)

This PR **fast-forwards the already-certified MVP 1 lineage onto `main`**.

| Comparison | Expected contents |
| --- | --- |
| `main` → `release/mvp-1` | Full certified product history (DO-008 → DO-009 → MVP 1 product → evidence) **plus** publication docs/CI/release tooling, and a narrow post-freeze correctness allowlist |
| Product `7a9b684` → tip | **Not** “docs-only vs `main`”. Allowed classes only: docs, CI, release tooling, generated governance, and explicit `PRODUCT_CORRECTNESS_PATCH` paths |

The large file count vs `main` is expected: `main` did not yet contain the frozen MVP 1
implementation. That is publication of certified history, not a claim that this PR is a
docs-only delta against `main`.

## Topology

| Item | Value |
| --- | --- |
| Implementation branch | `feat/do-010-mvp-completion` |
| Publication branch | `release/mvp-1` |
| PR base | `main` @ `9ab975632225ee8cb0c26eba501869ea73615c2c` |
| Preferred merge | true fast-forward (no squash / no rebase) |
| Release tag | `mvp-1` |

## Verified lineage (must remain reachable)

```text
f9018213  DO-008
    ↓
92f0f80   DO-009
    ↓
7a9b684   MVP 1 product (capability freeze)
    ↓
b727cce   MVP 1 release evidence
    ↓
publication docs / CI / release tooling
    ↓
PRODUCT_CORRECTNESS_PATCH (localhost MIDI API only; no new capability)
```

## Post-freeze correctness patches (review blockers)

These are **not** new product capability. They are narrow localhost capture-API fixes
required before publication approval:

1. Web MIDI note-on velocity 0 classified as `NOTE_OFF`
2. Capture session maps (`repetitions`, `practice_onsets`) cleared on start and after close
3. Tree-compare script reports honest classes (docs / CI / release tooling / patches)
   instead of collapsing executables into `DOCUMENTATION_ONLY_DIFFERENCE`

Allowlisted product paths vs `7a9b684`:

- `src/master_all_strings/mvp/performance_api.py`
- `tests/mvp/test_performance_api.py`

## Publication progress

| Stage | State |
| --- | --- |
| Local documentation/metadata commits | complete |
| Review-blocker correctness patches | complete |
| Local release-candidate verification | PASS (targeted MVP API + publication utils; full gate re-run before merge) |
| Push `release/mvp-1` | complete (`origin/release/mvp-1`) |
| Open PR | [#18](https://github.com/HanzoRazer/Master-All-Strings/pull/18) |
| GitHub CI | re-verify after blocker fixes |
| Review | in progress |
| Merge | pending (authorized after clean CI/review) |
| Tag `mvp-1` | pending (after merged SHA verification) |

## Final fields

| Field | Value |
| --- | --- |
| PR number / URL | [#18](https://github.com/HanzoRazer/Master-All-Strings/pull/18) |
| Candidate SHA | *see tip of `release/mvp-1`* |
| Merged SHA | *pending* |
| Release SHA | *pending* |
| Tree vs `7a9b684` | `ALLOWED_PUBLICATION_DIFFERENCE_WITH_CORRECTNESS_PATCHES` |
| CI result | *pending re-verify* |

## Explicit exclusions

Do not absorb:

- `feat/do-009-live-midi-alignment`
- `03477a2`
- any other parallel/substitute DO-009 history
