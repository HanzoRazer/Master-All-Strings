# MVP-1 User Flow

## Launch

```bash
PYTHONPATH=src python3 scripts/run_mvp1.py --lesson ascending_scale --open
```

This exports the active projection, prefetches every bundled demo for offline
demo switching, serves `web/mvp1/` on localhost, and opens a browser.

Headless export only:

```bash
PYTHONPATH=src python3 scripts/run_mvp1.py --lesson ascending_scale
```

MIDI path:

```bash
PYTHONPATH=src python3 scripts/run_mvp1.py --midi path/to/file.mid --instrument guitar-standard-6
```

## First-run experience

1. Browser loads `index.html` and `projection.json`.
2. Fretboard shows string lanes, selected note chips with pitch + fret, play line.
3. Lesson sidebar lists title, instrument, selection policy, digests, warnings.
4. Transport controls: Play, Pause, Restart, Seek, rate buttons (0.5×–1.5×).

## Demo switching

The Demo select loads `./projections/<demo_id>.json` (prefetched by the CLI).
No backend API is required after export.

## Unplayable notes

Unplayable events appear in the dedicated gutter (not on a string lane). Selected
notes remain on their lanes. Mixed lessons keep scrolling.

## Teacher override

Override-selected notes carry `selection_origin: "teacher_override"` and render
with a distinct style so automatic vs teacher choice is visible.

## Instrument select

The instrument dropdown lists available profiles. Bundled demo projections are
exported for each demo’s declared instrument. Guitar (`guitar-standard-6`) is
the primary MVP surface; other profiles are marked experimental.
