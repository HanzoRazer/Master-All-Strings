# DO-010 release gate

Product base: verified DO-009 snapshot `92f0f80` (`origin/evidence/do-009-local-snapshot`).
DO-009A reconciliation is external verification history and is not required product
content on this branch.

## Required evidence pass

1. Confirm ancestry `f9018213` → `92f0f80` → DO-010 HEAD and authorized scope only
2. Rerun full Python suite with coverage, Ruff, strict mypy, and Node tests from that HEAD
3. Rebuild DO-009 return artifact and confirm digest match
4. Rebuild DO-010 evaluation evidence via `scripts/build_do010_evidence.py`
5. Exercise golden three-attempt demo (API + browser `?devGolden=1`):

```text
Attempt 1 → SLOW_DOWN
Attempt 2 → ISOLATE_PASSAGE
Attempt 3 → CONTINUE
```

6. Confirm product flow:

```text
Lesson → See/Hear → Practice → Perform → Results
  → evidence-backed feedback → apply next action → repeat → Continue
```

7. Regression-check DO-008/DO-009, Zone, one-string, transport, and audio scheduling
8. Validate education schemas/governance and Performance↛Education import direction
9. Record hardware exactly as:

- `UNVERIFIED_PHYSICAL_MIDI_INPUT`
- `UNVERIFIED_AUDIO_OUTPUT`

## Gate status

Recorded in `DO010_INTEGRATION_EVIDENCE.json` against product HEAD
`7a9b68455b84b065fcd6b184c0903b292d090ef7`.

Software MVP status after a matching evidence pack: **COMPLETE**.

Publication (push/PR) remains a separate authorized operation and must not be mixed
into implementation.
