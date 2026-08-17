# Master All Strings — MVP 1 Release Report

Commercial milestone: **Master All Strings MVP 1**

This report records the software release-gate result for MVP 1. Publication
history (branch/PR/CI/merge/tag) lives in `MVP1_PUBLICATION_REPORT.md`.

## Software status

```text
MASTER ALL STRINGS MVP 1
SOFTWARE STATUS: COMPLETE
```

Publication status is tracked under DO-010A / DO-010A-R and becomes
**PUBLISHED, RE-CERTIFIED, AND FROZEN** at tag `mvp-1` → `ac38819b23ed9d85b651755e7612f42d7d528ddc`.

## Certified SHAs

| Role | SHA |
| --- | --- |
| Original product | `7a9b68455b84b065fcd6b184c0903b292d090ef7` |
| Original release evidence | `b727cce6da108667d7dc1823df17f85cdeb9d810` |
| Corrected product | `f028549b145bf3f567e936d5d7e29ab2f93f63d3` (capture velocity-0 note-off + session map reset) |
| DO-009 baseline | `92f0f80b46c0c6e8e7acfd8f6f36fd007bfe58ec` |
| DO-008 frozen | `f9018213fb9097cb716a8c91670ae03f7ed1b514` |

## Software gates (original local evidence)

| Gate | Result |
| --- | --- |
| pytest | 1,588 passed / 1 skipped |
| coverage | 95.15% |
| Ruff | PASS |
| strict mypy | PASS |
| JavaScript | 37 passed |
| schemas / governance | PASS |
| DO-009 digest rebuild | match `sha256:c1249457…` |
| Educational golden demo | `SLOW_DOWN` → `ISOLATE_PASSAGE` → `CONTINUE` |
| Lesson→Practice→Results→Next→Continue | PASS |

Source evidence pack: `docs/mvp/DO010_INTEGRATION_EVIDENCE.json` and
`docs/mvp/do010_artifacts/`.

## Release correction (DO-010A-R)

Post-review capture correctness fixes landed after the original product/evidence
baseline. They remain in MVP 1 and require full re-certification:

1. Web MIDI `0x90` velocity `0` classified as `NOTE_OFF`
2. Capture repetition/onset maps reset on start and after close

Corrected product identity: **`f028549b145bf3f567e936d5d7e29ab2f93f63d3`** (not a silent redefinition of `7a9b684`).

PR #18 was squash-merged (`a198c7b`); that tip is preserved under
`recovery/mvp1-squash-merge` and is **not** the release. `main` was repaired to the
intact `release/mvp-1` history before re-certification resumed.

Re-certification evidence and the final release SHA are recorded in
`docs/mvp/MVP1_RECERTIFICATION_REPORT.md` / `MVP1_RECERTIFICATION_EVIDENCE.json`
and finalized in `MVP1_PUBLICATION_*` after green gates.
## Hardware (non-blocking)

| Channel | Status |
| --- | --- |
| Physical MIDI | `UNVERIFIED_PHYSICAL_MIDI_INPUT` |
| Audio output | `UNVERIFIED_AUDIO_OUTPUT` |

## Naming note

Historical labels such as MVP-1F and MVP-2A describe engineering slices that are
now part of commercial **MVP 1**. They do not imply a separate commercial MVP 2
release.


## Final freeze record (DO-010A-R)

| Field | Value |
| --- | --- |
| Tag | `mvp-1` |
| Tag target / release SHA | `ac38819b23ed9d85b651755e7612f42d7d528ddc` |
| Current `main` tip (includes post-tag docs) | `1a3a63aca75d5bb374506a76fbc7db08ab30a3ec` |
| Corrected product | `f028549b145bf3f567e936d5d7e29ab2f93f63d3` |
| Recertification evidence | `d1761d93f2dbbfde4f0551dd981a0d4c064d4749` |

```text
MASTER ALL STRINGS
MVP 1
STATUS: PUBLISHED, RE-CERTIFIED, AND FROZEN
```
