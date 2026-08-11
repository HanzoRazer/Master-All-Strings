# MVP-1 Architecture

## Layering

```text
resources/mvp1/demo_lessons   (bundled LessonAssignmentV1 + MIDI)
        ↓
mvp.application / mvp.orchestrator   (application adapter)
        ↓
lesson.*  →  core.musical_events / MSME / score.musical_timeline
        ↓
FretboardScrollProjectionV1   (product delivery projection)
        ↓
web/mvp1   (zero-authority DOM renderer + presentation clock)
```

`mvp/` is an **application / adapter** layer. It composes public Lesson and Core
contracts into a runnable local product slice. It is not a new constitutional
engine and is **not** registered in `engine_architecture_v1.json`.

## Authority boundaries

| Concern | Owner | Notes |
|---|---|---|
| Tick ↔ seconds under tempo maps | `core.score.musical_timeline` | Piecewise tempo; no silent 120 BPM |
| MSME candidates | Core spatial mapping | Unchanged |
| Automatic selection scaffold | `lesson.auto_select` (`enumeration_v1`) | Deterministic, not “optimal” |
| Teacher overrides | `lesson.overrides` | Physically validated via MSME |
| Soft unplayable rows | **`MvpLessonOrchestrator` only** | `lesson.pipeline` still hard-fails |
| FretboardScrollProjectionV1 | `mvp.projection` | Product delivery, not Core contract |
| Presentation clock | `web/mvp1/transport.js` | Anchor-derived seconds only |
| DOM rendering | `web/mvp1/renderer.js` | Draws projection fields only |

## Timing rule (2C)

Core owns musical timeline conversion via:

- `normalize_tempo_map`
- `ticks_to_seconds` / `ticks_to_microseconds`
- `seconds_to_ticks`

MVP projection builders call these helpers and emit **seconds** on every note.
JavaScript never performs tempo or tick math.

Missing tempo is an error. There is no default BPM.

## Unplayable softening (3A)

`lesson.pipeline.run_mvp_lesson_pipeline` continues to raise when an event has
zero MSME candidates.

`MvpLessonOrchestrator` converts the same condition into projection rows with
`status: "unplayable"` so the product UI can show them without changing the
lesson-domain contract.

## Projection contract

`FretboardScrollProjectionV1` is documented and schema’d under
`resources/mvp1/schema/`. It is a delivery artifact for the local web UI and
CLI export path. Governance registry ownership is intentionally unchanged (4A).

## Local delivery

```text
scripts/run_mvp1.py --lesson <demo_id> [--open]
  → writes web/mvp1/projection.json
  → writes web/mvp1/demos.json + instruments.json
  → prefetches web/mvp1/projections/<demo_id>.json
  → optional localhost static server
```
