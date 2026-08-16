# Master All Strings MVP 1 — Release Baseline

Commercial milestone: **Master All Strings MVP 1**

This document freezes the SHA lineage and verification state that justify publishing
MVP 1. It does not redefine product behavior.

## Frozen lineage

```text
DO-008 frozen
f9018213fb9097cb716a8c91670ae03f7ed1b514
    ↓
DO-009 verified baseline
92f0f80b46c0c6e8e7acfd8f6f36fd007bfe58ec
    ↓
MVP 1 product
7a9b68455b84b065fcd6b184c0903b292d090ef7
    ↓
MVP 1 release evidence
b727cce6da108667d7dc1823df17f85cdeb9d810
```

| Role | SHA |
| --- | --- |
| `do008_sha` | `f9018213fb9097cb716a8c91670ae03f7ed1b514` |
| `do009_sha` | `92f0f80b46c0c6e8e7acfd8f6f36fd007bfe58ec` |
| `product_sha` | `7a9b68455b84b065fcd6b184c0903b292d090ef7` |
| `evidence_sha` | `b727cce6da108667d7dc1823df17f85cdeb9d810` |
| `merged_sha` | *pending publication* |
| `release_tag` | `mvp-1` (*pending*) |
| `release_sha` | *pending publication* |

Historical engineering names such as MVP-1F, MVP-2A, DO-008, DO-009, and DO-010 remain
valid history identifiers. They do **not** imply that commercial MVP 2 already exists.

## Software verification (recorded at evidence SHA)

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

Authoritative local evidence: `docs/mvp/DO010_INTEGRATION_EVIDENCE.json`.

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
