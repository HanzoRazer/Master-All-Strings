"""English MVP message catalog keyed by Educational ``message_key``.

Prose lives here — not inside evaluation rules — so localization can replace the
catalog later without changing finding semantics.
"""

from __future__ import annotations

MESSAGE_CATALOG_V1: dict[str, str] = {
    "finding.early_entry": "This note entered earlier than the lesson timing.",
    "finding.late_entry": "This note entered later than the lesson timing.",
    "finding.pitch_difference": "This pitch differed from the expected lesson note.",
    "finding.expected_note_missing": "An expected lesson note was not observed.",
    "finding.unexpected_note": "An extra note was observed that was not expected.",
    "finding.duration_short": "This note was shorter than expected.",
    "finding.duration_long": "This note was longer than expected.",
    "finding.repetition_improved": "Later repetitions showed fewer findings than earlier ones.",
    "finding.repetition_regressed": "Later repetitions showed more findings than earlier ones.",
    "finding.findings_concentrated": "Findings are concentrated in one passage.",
    "action.continue": "Continue — no immediate repetition required under this policy.",
    "action.repeat": "Repeat the passage.",
    "action.slow_down": "Practice slower at a supported rate.",
    "action.isolate_passage": "Isolate the passage that needs focus.",
    "action.view_one_string": "View this passage on one string.",
    "action.enable_zone_view": "Enable Zone Harmony colors for this passage.",
}
