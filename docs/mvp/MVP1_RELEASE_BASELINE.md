# Master All Strings MVP 1 — Release Baseline

Commercial milestone: **Master All Strings MVP 1**

This document freezes the SHA lineage and verification state that justify publishing
MVP 1. It does not redefine product behavior beyond the authorized capture
correctness patch.

## Frozen lineage (DO-010A-R)

```text
DO-008 frozen
f9018213fb9097cb716a8c91670ae03f7ed1b514
    ↓
DO-009 verified baseline
92f0f80b46c0c6e8e7acfd8f6f36fd007bfe58ec
    ↓
original MVP 1 product
7a9b68455b84b065fcd6b184c0903b292d090ef7
    ↓
original MVP 1 release evidence
b727cce6da108667d7dc1823df17f85cdeb9d810
    ↓
corrected product (capture correctness patch)
f028549b145bf3f567e936d5d7e29ab2f93f63d3
    ↓
publication / classifier / docs tooling
    ↓
recertification evidence
d1761d93f2dbbfde4f0551dd981a0d4c064d4749
    ↓
final release tip / tag mvp-1
ac38819b23ed9d85b651755e7612f42d7d528ddc
```

| Role | SHA |
| --- | --- |
| `do008_sha` | `f9018213fb9097cb716a8c91670ae03f7ed1b514` |
| `do009_sha` | `92f0f80b46c0c6e8e7acfd8f6f36fd007bfe58ec` |
| `original_product_sha` | `7a9b68455b84b065fcd6b184c0903b292d090ef7` |
| `original_release_evidence_sha` | `b727cce6da108667d7dc1823df17f85cdeb9d810` |
| `corrected_product_sha` | `f028549b145bf3f567e936d5d7e29ab2f93f63d3` |
| `recertification_evidence_sha` | `d1761d93f2dbbfde4f0551dd981a0d4c064d4749` |
| `final_release_sha` | `ac38819b23ed9d85b651755e7612f42d7d528ddc` |
| `release_tag` | `mvp-1` |
| `release_sha` | `ac38819b23ed9d85b651755e7612f42d7d528ddc` |
| `final_main_sha` | `e9f10c0433cfd7f2a76fca1db1a6d8f6c66836a6` |
| `squash_merge_sha` | `a198c7b30370d077e7213b4ebeab170c769aaaff` |
| `recovery_ref` | `recovery/mvp1-squash-merge` |
| `main_repair_method` | `force-update-to-release-tip` (completed before DO-010A-R resumed) |

`original_product_sha` remains historically valid. Final release product identity for
tagging is **`corrected_product_sha`**, because Performance capture semantics changed.

## Topology repair note

PR #18 was squash-merged (`a198c7b`). That tip is **not** release authority. It is
preserved under `recovery/mvp1-squash-merge`. `main` was repaired to the intact
`release/mvp-1` history before DO-010A-R resumed. See `MVP1_PUBLICATION_REPORT.md`.

## Software verification (original evidence SHA)

| Gate | Result |
| --- | --- |
| Python | 1,588 passed / 1 skipped |
| Coverage | 95.15% |
| Ruff | PASS |
| Strict mypy | PASS |
| JavaScript (`web/mvp1/tests`) | 37 passed |
| Schemas / governance | PASS |
| DO-009 return digest | `sha256:c1249457…` exact rebuild match |
| Educational golden demo | `SLOW_DOWN` → `ISOLATE_PASSAGE` → `CONTINUE` |
| Product flow Lesson→…→Continue | PASS |

Authoritative original evidence: `docs/mvp/DO010_INTEGRATION_EVIDENCE.json`.
Re-certification results for `f028549` are recorded in
`docs/mvp/MVP1_RECERTIFICATION_*` after the full gate.

## Hardware verification

| Channel | Status |
| --- | --- |
| Physical MIDI input | `UNVERIFIED_PHYSICAL_MIDI_INPUT` |
| Audio output | `UNVERIFIED_AUDIO_OUTPUT` |

These states are non-blocking for publishing MVP 1 software and must not be promoted
to PASS from simulation alone.

## Known limitations

See `docs/mvp/DO010_KNOWN_LIMITATIONS.md` and `docs/mvp/MVP1_KNOWN_LIMITATIONS.md`.
Publication does not close those limitations.

## Non-authoritative history

Do not merge, cherry-pick, or otherwise absorb parallel substitute implementations
(for example `feat/do-009-live-midi-alignment` / `03477a2`) into this baseline.
Do not tag or treat `a198c7b` as the MVP 1 release.
