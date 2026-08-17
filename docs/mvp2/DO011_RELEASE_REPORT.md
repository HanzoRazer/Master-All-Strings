# DO-011 Release Report — MVP 2A Lesson Media Foundation

## Status

```text
DO-011 / MVP 2A
EVIDENCE FROZEN — PR ONLY (no MVP 2 tag/release)
```

## Baseline

| Field | Value |
| --- | --- |
| `mvp1_release_sha` | `ac38819b23ed9d85b651755e7612f42d7d528ddc` |
| `do011_base_sha` | `042b5d5b38ca83c72429f7bd865cf87249079200` |
| Branch | `cursor/mvp2a-lesson-media-90b8` |

`mvp-1` remains immutable and reachable.

## What landed

* Versioned Lesson Media contracts (`TEXT` / `IMAGE` / `VIDEO`)
* Sidecar catalog keyed by lesson identity (`LessonAssignmentV1` untouched)
* Safe local resolver + catalog validation
* Localhost `GET /api/v1/lessons/{lesson_id}/media` + `/media/assets/...`
* Modest Teaching Media panel in `web/mvp1`
* Video play/pause/seek/rate/segment-loop + cue navigation
* Golden demo: **Half Steps on One String**
* Architecture doc: media is presentation-only (no engine registry row)

## Verification

| Gate | Result |
| --- | --- |
| pytest | 1616 passed / 2 skipped |
| coverage | 95.14% |
| Ruff | PASS |
| Strict mypy | PASS |
| Node (`web/mvp1`) | 38 passed |
| Media catalog validation | PASS |
| DO-008 | 48 / 48 |
| DO-009 digest | exact match |
| Musical non-interference | PASS |
| Browser smoke | PASS |

## Hardware (unchanged)

* `UNVERIFIED_PHYSICAL_MIDI_INPUT`
* `UNVERIFIED_AUDIO_OUTPUT`

## Explicit non-goals retained

No recovered corpus migration, avatars, cloud streaming, frame-accurate A/V sync,
or MVP 2 release declaration.

Machine-readable pack: `docs/mvp2/DO011_INTEGRATION_EVIDENCE.json`.
