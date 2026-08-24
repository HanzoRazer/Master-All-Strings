"""Standard-notation projection from a canonical revision (DO-013).

Notation reads canonical music and nothing else. It never sees a string or a
fret, which is what makes the same melody the same notation however it is
fingered.

The hard part is not drawing notes; it is declining to invent them. Three places
offer a plausible guess and refuse it:

* a duration that does not divide exactly becomes an unsupported feature rather
  than the nearest note value;
* a rest is derived only where nothing at all is sounding, never from the gap
  between one note's start and the next;
* a note crossing a barline reports that a tie would be needed rather than
  fabricating one.

Each refusal is recorded, so the gap stays visible instead of shipping notation
that renders cleanly and misstates the music.
"""

from __future__ import annotations

from fractions import Fraction

from master_all_strings.core.musical_events import MusicalEvent
from master_all_strings.core.projections.contracts import (
    DISPLAY_DURATION_QUARTER_FRACTIONS,
    PROJECTION_SCHEMA_VERSION,
    DisplayDuration,
    NotationDisplayPolicy,
    NotationEventKind,
    NotationEventV1,
    NotationMeasureV1,
    NotationProjectionV1,
    ProjectionUnsupportedFeatureV1,
    RestDerivation,
    UnsupportedFeatureCode,
)
from master_all_strings.core.score.errors import (
    ScoreContractError,
    require_positive_int,
)
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.models import CanonicalScoreRevisionV1

__all__ = [
    "SHARP_PREFERRED_PITCH_CLASSES",
    "build_notation_projection",
    "derive_display_duration",
    "derive_global_silence_intervals",
    "measure_length_ticks",
    "partition_events_into_measures",
    "spell_display_pitch",
]

#: Sharp-preferred display spelling. Presentation only -- the canonical model
#: carries no enharmonic evidence, so this names a convention rather than a fact
#: about the music. When Core gains spelling authority, that supersedes this.
SHARP_PREFERRED_PITCH_CLASSES = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)


def spell_display_pitch(midi_note: int) -> str:
    """Spell a MIDI note for display, sharp-preferred, with octave.

    Middle C (MIDI 60) is C4, the convention the rest of the product already
    displays.
    """

    if isinstance(midi_note, bool) or not isinstance(midi_note, int):
        raise ScoreContractError("midi_note must be an integer")
    if not 0 <= midi_note <= 127:
        raise ScoreContractError("midi_note must be between 0 and 127")
    pitch_class = SHARP_PREFERRED_PITCH_CLASSES[midi_note % 12]
    octave = midi_note // 12 - 1
    return f"{pitch_class}{octave}"


def derive_display_duration(
    duration_ticks: int, *, ticks_per_quarter: int
) -> DisplayDuration | None:
    """Map ticks to an exact note value, or ``None`` when none is exact.

    Exact means exact. A duration of 500 ticks at 480 PPQ is not "about a
    quarter"; it is a duration this notation model cannot write down, and saying
    so is more useful than drawing a quarter note that is wrong by 20 ticks.

    Fractions throughout: comparing floats would let a value that is nearly
    representable slip through as representable, which is the failure this whole
    policy exists to prevent.
    """

    require_positive_int(duration_ticks, "duration_ticks")
    require_positive_int(ticks_per_quarter, "ticks_per_quarter")
    quarters = Fraction(duration_ticks, ticks_per_quarter)
    for duration, fraction in DISPLAY_DURATION_QUARTER_FRACTIONS.items():
        if quarters == fraction:
            return duration
    return None


def measure_length_ticks(meter: MeterChangeV1, *, ticks_per_quarter: int) -> int:
    """Ticks in one measure of ``meter``.

    ``numerator`` beats of a ``1/denominator`` note each, expressed in quarters.
    A meter whose measure is not a whole number of ticks at this PPQ is refused
    rather than rounded -- every subsequent barline would inherit the error.
    """

    require_positive_int(ticks_per_quarter, "ticks_per_quarter")
    exact = Fraction(meter.numerator * 4, meter.denominator) * ticks_per_quarter
    if exact.denominator != 1:
        raise ScoreContractError(
            f"meter {meter.numerator}/{meter.denominator} does not divide evenly at "
            f"{ticks_per_quarter} PPQ"
        )
    return int(exact)


def _normalized_meter_map(
    meter_changes: tuple[MeterChangeV1, ...],
) -> tuple[MeterChangeV1, ...]:
    if not meter_changes:
        raise ScoreContractError(
            "notation requires a meter map; refusing to assume one"
        )
    by_tick = {change.tick: change for change in meter_changes}
    ordered = tuple(by_tick[tick] for tick in sorted(by_tick))
    if ordered[0].tick != 0:
        raise ScoreContractError("meter map must begin at tick 0")
    return ordered


def _total_ticks(events: tuple[MusicalEvent, ...]) -> int:
    return max((event.start_tick + event.duration_ticks for event in events), default=0)


def derive_global_silence_intervals(
    events: tuple[MusicalEvent, ...], *, total_ticks: int
) -> tuple[tuple[int, int], ...]:
    """Spans in ``[0, total_ticks)`` where no canonical note is sounding.

    The complement of the union of sounding intervals -- deliberately not the gap
    between consecutive note starts. With overlapping notes those differ: a
    second voice entering while the first is held leaves a gap between onsets and
    no silence at all, and the naive reading would write a rest through a held
    note.
    """

    if total_ticks <= 0 or not events:
        return ()

    spans = sorted(
        (event.start_tick, event.start_tick + event.duration_ticks) for event in events
    )
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    silences: list[tuple[int, int]] = []
    cursor = 0
    for start, end in merged:
        if start > cursor:
            silences.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < total_ticks:
        silences.append((cursor, total_ticks))
    return tuple(silences)


def _has_overlapping_notes(events: tuple[MusicalEvent, ...]) -> bool:
    spans = sorted(
        (event.start_tick, event.start_tick + event.duration_ticks) for event in events
    )
    for index in range(1, len(spans)):
        if spans[index][0] < spans[index - 1][1]:
            return True
    return False


def partition_events_into_measures(
    *,
    events: tuple[MusicalEvent, ...],
    meter_changes: tuple[MeterChangeV1, ...],
    ticks_per_quarter: int,
    total_ticks: int,
) -> tuple[tuple[int, int, MeterChangeV1], ...]:
    """Measure spans as ``(start_tick, end_tick, meter)``.

    Barlines restart at each meter change: a new meter begins a new measure
    rather than continuing the previous one part-filled, which is what the meter
    map is asserting.
    """

    meter_map = _normalized_meter_map(meter_changes)
    span_end = max(total_ticks, 1)
    measures: list[tuple[int, int, MeterChangeV1]] = []

    for index, meter in enumerate(meter_map):
        section_start = meter.tick
        section_end = (
            meter_map[index + 1].tick if index + 1 < len(meter_map) else span_end
        )
        if section_end <= section_start:
            continue
        length = measure_length_ticks(meter, ticks_per_quarter=ticks_per_quarter)
        cursor = section_start
        while cursor < section_end:
            measures.append((cursor, cursor + length, meter))
            cursor += length
    return tuple(measures)


def _measure_index_for(measures: tuple[tuple[int, int, MeterChangeV1], ...], tick: int) -> int:
    for index, (start, end, _meter) in enumerate(measures):
        if start <= tick < end:
            return index
    return len(measures) - 1


def build_notation_projection(
    revision: CanonicalScoreRevisionV1,
    *,
    display_policy: NotationDisplayPolicy = NotationDisplayPolicy.SHARP_PREFERRED_V1,
) -> NotationProjectionV1:
    """Project one canonical revision as standard notation."""

    if not isinstance(revision, CanonicalScoreRevisionV1):
        raise ScoreContractError("expected CanonicalScoreRevisionV1")

    ppq = revision.ticks_per_quarter
    events = tuple(sorted(revision.events, key=lambda e: (e.start_tick, e.event_id)))
    total = _total_ticks(events)
    measures = partition_events_into_measures(
        events=events,
        meter_changes=revision.meter_changes,
        ticks_per_quarter=ppq,
        total_ticks=total,
    )

    unsupported: list[ProjectionUnsupportedFeatureV1] = []
    buckets: dict[int, list[NotationEventV1]] = {index: [] for index in range(len(measures))}

    # --- notes ---------------------------------------------------------------
    for event in events:
        index = _measure_index_for(measures, event.start_tick)
        measure_end = measures[index][1]
        display = derive_display_duration(event.duration_ticks, ticks_per_quarter=ppq)
        if display is None:
            unsupported.append(
                ProjectionUnsupportedFeatureV1(
                    schema_version=PROJECTION_SCHEMA_VERSION,
                    code=UnsupportedFeatureCode.UNSUPPORTED_DISPLAY_DURATION,
                    detail=(
                        f"{event.duration_ticks} ticks at {ppq} PPQ is not an exact "
                        "simple or single-dotted note value"
                    ),
                    canonical_event_id=event.event_id,
                    start_tick=event.start_tick,
                )
            )
        if event.start_tick + event.duration_ticks > measure_end:
            # Writing this faithfully needs a tie across the barline, and nothing
            # in the canonical model says these are one sounded event.
            unsupported.append(
                ProjectionUnsupportedFeatureV1(
                    schema_version=PROJECTION_SCHEMA_VERSION,
                    code=UnsupportedFeatureCode.TIE_NOT_SUPPORTED,
                    detail=(
                        "note crosses a barline and would need a tie to be written "
                        "exactly; exact duration_ticks retained"
                    ),
                    canonical_event_id=event.event_id,
                    start_tick=event.start_tick,
                )
            )
        buckets[index].append(
            NotationEventV1(
                schema_version=PROJECTION_SCHEMA_VERSION,
                event_kind=NotationEventKind.NOTE,
                start_tick=event.start_tick,
                duration_ticks=event.duration_ticks,
                canonical_event_id=event.event_id,
                midi_note=event.midi_note,
                display_pitch=spell_display_pitch(event.midi_note),
                display_duration=display,
            )
        )

    # --- rests ---------------------------------------------------------------
    for silence_start, silence_end in derive_global_silence_intervals(
        events, total_ticks=total
    ):
        for index, (measure_start, measure_end, _meter) in enumerate(measures):
            start = max(silence_start, measure_start)
            end = min(silence_end, measure_end)
            if end <= start:
                continue
            # Split at the barline: a rest is written per measure, not as one span
            # straddling a barline.
            display = derive_display_duration(end - start, ticks_per_quarter=ppq)
            if display is None:
                unsupported.append(
                    ProjectionUnsupportedFeatureV1(
                        schema_version=PROJECTION_SCHEMA_VERSION,
                        code=UnsupportedFeatureCode.UNSUPPORTED_DISPLAY_DURATION,
                        detail=(
                            f"rest of {end - start} ticks at {ppq} PPQ is not an exact "
                            "simple or single-dotted note value"
                        ),
                        start_tick=start,
                    )
                )
            buckets[index].append(
                NotationEventV1(
                    schema_version=PROJECTION_SCHEMA_VERSION,
                    event_kind=NotationEventKind.REST,
                    start_tick=start,
                    duration_ticks=end - start,
                    display_duration=display,
                    derivation=RestDerivation.GLOBAL_SILENCE,
                )
            )

    if _has_overlapping_notes(events):
        # Only global silence is representable without voices, and voice_id is
        # null throughout the corpus. Saying so beats allocating notes to voices
        # nobody declared.
        unsupported.append(
            ProjectionUnsupportedFeatureV1(
                schema_version=PROJECTION_SCHEMA_VERSION,
                code=UnsupportedFeatureCode.VOICE_SPECIFIC_REST_INFERENCE_UNAVAILABLE,
                detail=(
                    "revision contains overlapping notes with no voice assignment; "
                    "only global-silence rests are projected"
                ),
            )
        )

    built = tuple(
        NotationMeasureV1(
            schema_version=PROJECTION_SCHEMA_VERSION,
            measure_index=index,
            start_tick=start,
            end_tick=end,
            meter=meter,
            events=tuple(
                sorted(
                    buckets[index],
                    key=lambda e: (e.start_tick, e.event_kind.value, e.canonical_event_id or ""),
                )
            ),
        )
        for index, (start, end, meter) in enumerate(measures)
    )

    return NotationProjectionV1(
        schema_version=PROJECTION_SCHEMA_VERSION,
        canonical_revision_id=revision.revision_id,
        ticks_per_quarter=ppq,
        display_policy=display_policy,
        measures=built,
        unsupported_features=tuple(unsupported),
    )
