# MVP-2A Release Gate

Run from the repository root:

```bash
python -m pytest --cov=master_all_strings --cov-report=term-missing
python -m ruff check src tests scripts/run_mvp1.py
python -m mypy --strict src
node --test web/mvp1/tests/*.test.js
python scripts/run_mvp1.py --lesson ascending_scale --refresh-fixtures
```

Then launch the local browser experience:

```bash
python scripts/run_mvp1.py --lesson ascending_scale --open
```

Verify Sound on, Play/Pause/Restart/Seek, all four rates, at least three loop wraps,
lesson switching, the unplayable-note demo, and the teacher-override demo. Confirm no
voice remains after pause or a lesson switch. Inspect the scheduler mapping diagnostic
without treating it as a speaker-latency measurement.

The human acoustic check is mandatory when automated capture is unavailable:

1. Select **Ascending Scale**, enable **Sound on**, and set volume to a safe level.
2. Press Play and confirm each pitch sounds as its note reaches the play line.
3. Pause, resume, seek, and switch between 0.50× and 1.50×; pitch must not transpose.
4. Loop `0.00s–0.60s` for at least three repetitions and confirm every pass is audible.
5. Select **Unplayable Note**; confirm F#1 sounds while it appears in the gutter.
6. Select **Teacher Override**; confirm E4 sounds while the override position is shown.
7. Switch lessons during playback and confirm no note continues from the old lesson.
8. Disconnect external networking, reload localhost, and repeat Play plus looping.
