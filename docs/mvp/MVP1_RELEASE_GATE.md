# MVP-1 Release Gate

## Required (ruling 5C)

Both must pass before the PR is marked ready for review:

1. **Headless / unit**
   - `ruff check src tests`
   - `mypy` (strict, `src`)
   - `pytest --cov` with repository `fail_under = 95`
   - Demo digest pins green (`tests/mvp/test_mvp_demos.py`)
   - Lesson pipeline hard-fail regression still green
2. **Browser walkthrough** with screenshots or equivalent review artifacts covering:
   - Play
   - Pause
   - Seek
   - Rate changes
   - Demo switching
   - Unplayable display
   - Teacher override styling
   - Resize

## Architecture gates

- Core owns tick↔seconds; JS receives seconds only; no silent 120 BPM
- Soft unplayable only in MVP orchestrator
- No `engine_architecture_v1.json` change for the MVP projection
- Renderer contains no fingering / tempo / candidate authority

## Launch command for review

```bash
PYTHONPATH=src python3 scripts/run_mvp1.py --lesson ascending_scale --open
```
