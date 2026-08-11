# MVP-1 Demo Library

Bundled under `resources/mvp1/demo_lessons/`.

Manifest: `manifest.json`  
Assignments: `assignments/*.json`  
Optional MIDI twin: `midi/ascending_scale.mid`

Each manifest entry pins:

- `expected_behavior_digest` — LessonAssignment behavior digest
- `expected_projection_digest` — FretboardScrollProjectionV1 digest

## Demos

| demo_id | Demonstrates |
|---|---|
| `ascending_scale` | Ascending fragment + `enumeration_v1` |
| `descending_scale` | Descending fragment |
| `open_strings` | Open-string preference |
| `first_position` | Soft first-position region |
| `position_shift` | Register / position change |
| `string_crossing` | String crossing |
| `simultaneous_notes` | Same-onset events; documents `chord_aware_selection` gap |
| `multiple_candidates` | Multiple MSME candidates → deterministic pick |
| `unplayable_note` | Visible unplayable row among playable neighbors |
| `teacher_override` | Valid override origin vs automatic |

## Language

Automatic selection uses the `enumeration_v1` scaffold. UI and docs say
**selected / deterministic**, never “optimal”.

## Regenerating digests

After intentional musical/spatial changes:

```bash
PYTHONPATH=src python3 scripts/run_mvp1.py --lesson ascending_scale
# then update manifest expected_* digests from CLI output / tests
PYTHONPATH=src python3 -m pytest tests/mvp/test_mvp_demos.py -q
```
