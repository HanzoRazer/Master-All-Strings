# DO-010 release gate

Product base: verified DO-009 snapshot `92f0f80` (`origin/evidence/do-009-local-snapshot`).
DO-009A reconciliation is external verification history and is not required product
content on this branch.

Run the complete Python suite with coverage, Ruff over `src tests scripts`, strict
mypy over `src`, and Node tests under `web/mvp1/tests`. Confirm education package
coverage and the golden three-attempt demo:

```text
Attempt 1 → SLOW_DOWN
Attempt 2 → ISOLATE_PASSAGE
Attempt 3 → CONTINUE
```

via `LocalPracticeEvaluationApi.golden_demo` / `?devGolden=1` in the browser shell.

Hardware classifications remain:

- `UNVERIFIED_PHYSICAL_MIDI_INPUT`
- `UNVERIFIED_AUDIO_OUTPUT`

Neither blocks deterministic software MVP completion. Neither may be promoted to PASS
from simulation alone.

Publication (push/PR) is authorized only after this gate is satisfied.
