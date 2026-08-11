# MVP-1 Known Limitations

- **No audio.** Transport is a presentation clock only.
- **Guitar primary.** Other instrument profiles are experimental listings.
- **No chord-aware selection.** Simultaneous onsets are projected as independent
  events; demos that include them set `unsupported_features: ["chord_aware_selection"]`.
- **`enumeration_v1` is a scaffold**, not DO-004 / ADR-0005 constitutional selection.
  Language: selected/deterministic, not optimal.
- **`lesson.pipeline` still hard-fails** on zero-candidate events. Soft unplayable
  rows exist only in `MvpLessonOrchestrator` for the product UI.
- **Vanilla static UI.** No React/npm build; demo switching uses prefetched JSON.
- **Instrument dropdown does not re-orchestrate** in the browser. Re-export via
  CLI to change instrument for a lesson.
- **Fretboard design HTML artifact** (`Master All Strings - MVP1 Fretboard.dc.html`)
  may land later as reference polish; it is not an MVP blocker (ruling 1B).
- **No governance registry entry** for `FretboardScrollProjectionV1` (ruling 4A).
