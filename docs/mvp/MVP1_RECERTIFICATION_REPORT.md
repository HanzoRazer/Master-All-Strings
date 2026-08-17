# Master All Strings MVP 1 — Re-Certification Report (DO-010A-R)

## Status

```text
GATES_GREEN_PENDING_TAG
```

## Why re-certification

PR #18 was squash-merged (`a198c7b`), which flattened certified ancestry. Topology
was repaired before this tranche resumed (`main` / `release/mvp-1` restored to the
intact history; squash preserved under `recovery/mvp1-squash-merge`).

Additionally, reviewed capture correctness fixes at `corrected_product_sha`
changed Performance runtime semantics relative to `original_product_sha`, so the
original evidence pack is historically valid but not the final release baseline.

## SHA roles

| Role | Value |
| --- | --- |
| `original_product_sha` | `7a9b68455b84b065fcd6b184c0903b292d090ef7` |
| `original_release_evidence_sha` | `b727cce6da108667d7dc1823df17f85cdeb9d810` |
| `corrected_product_sha` | `f028549b145bf3f567e936d5d7e29ab2f93f63d3` |
| `squash_merge_sha` | `a198c7b30370d077e7213b4ebeab170c769aaaff` |
| `recovery_ref` | `recovery/mvp1-squash-merge` |
| `main_repair_method` | `force-update-to-release-tip` (completed before resume) |

## Correctness patch under test

1. MIDI `0x90` + velocity `0` → `NOTE_OFF`
2. Capture `repetitions` / `practice_onsets` cleared on start and after close

## Gate results (this re-certification)

| Gate | Result |
| --- | --- |
| pytest | 1596 passed / 1 skipped |
| coverage | 95.16% (≥95%) |
| Ruff | PASS |
| Strict mypy | PASS |
| JavaScript (`web/mvp1`) | 37 passed |
| Education schemas | PASS |
| Governance | PASS |
| DO-008 semantic vectors | 48 / 48 |
| DO-009 digest rebuild | match `sha256:c1249457…` |
| Golden learner sequence | `SLOW_DOWN` → `ISOLATE_PASSAGE` → `CONTINUE` |
| Tree vs `7a9b684` | `ALLOWED_PUBLICATION_DIFFERENCE_WITH_CORRECTNESS_PATCHES` |
| Lineage / no-squash topology | PASS |
| Browser smoke | PASS |
| Transport (play/pause/seek/rate/loop) | PASS |
| Zone Harmony overlay | PASS |
| One-string teaching view | PASS |
| Fake MIDI capture + attempt reset | PASS |

## Hardware (unchanged / non-blocking)

| Channel | Status |
| --- | --- |
| Physical MIDI | `UNVERIFIED_PHYSICAL_MIDI_INPUT` |
| Audio output | `UNVERIFIED_AUDIO_OUTPUT` |

## Browser smoke notes

Fresh automated browser session against localhost MVP UI:

- Base: `http://127.0.0.1:8765/index.html`
- Dev: `http://127.0.0.1:8765/index.html?fakeMidi=1&devGolden=1`
- Golden demo primary actions observed: SLOW_DOWN → ISOLATE → CONTINUE

Machine-readable pack: `docs/mvp/MVP1_RECERTIFICATION_EVIDENCE.json`.
