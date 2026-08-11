# MVP-1 Browser Smoke Report

**Date:** 2026-08-11  
**URL:** `http://127.0.0.1:8765/index.html`  
**Launch:** `PYTHONPATH=src python3 scripts/run_mvp1.py --lesson ascending_scale --no-browser --port 8765`  
**Result:** PASS (ruling 5C)

## Checklist

| Step | Result |
|---|---|
| Initial load (Ascending Scale) | PASS |
| Play (clock advances, notes scroll) | PASS |
| Pause (clock freezes) | PASS |
| Seek | PASS |
| Rate 0.50× | PASS |
| Rate 1.50× | PASS |
| Demo → Unplayable Note (gutter + warning) | PASS |
| Demo → Teacher Override (override styling / B-string E4@5) | PASS |
| Resize narrow (~375px) | PASS |
| Resize wide (~1280px) | PASS |
| Restart | PASS |

## Artifacts

Screenshots in `docs/mvp/smoke_artifacts/`:

- `01_initial_load.png` … `10_resized_wide.png`

Walkthrough recording (agent artifact, not committed):

- `/opt/cursor/artifacts/mvp1-browser-smoke-walkthrough.mp4`

## Headless gates also green

- `ruff check src tests scripts/run_mvp1.py`
- `mypy` (strict)
- `pytest --cov` → 95.55% (floor 95%), 1414 passed / 1 skipped
