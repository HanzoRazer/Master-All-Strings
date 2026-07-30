"""``DIRECT_EVENT_IMPORT_V1`` — the only ingestion policy in DO-007.

It does four things and refuses to do anything else: pair note-ons with note-offs,
convert nanoseconds to ticks, build canonical events, and record the evidence for each
conversion.

What it explicitly does **not** do, per ADR-0008 D8 and the DO-007 scope:

* no musical quantization — only tick-grid rounding, which A3 performs;
* no humanization, swing, or groove inference;
* no fingering or spatial mapping;
* no pedagogical interpretation of any kind;
* no synthesis of a missing note-off;
* no mapping of MIDI channel to ``voice_id``.

That last one deserves its reason. A channel may carry a divided-pickup string, device
routing, or an articulation; voices may share a channel and channels get reused.
Equating them would manufacture musical structure from a transport detail, and once
recorded it would be indistinguishable from a real voice assignment. ``voice_id`` stays
``None`` and the channel goes to provenance.

Pairing is **FIFO by (channel, MIDI note)**, documented and tested rather than inferred.
When a pitch is retriggered on the same channel before release, the oldest open note
takes the next release. Any other rule is defensible, but silence about which one is
not.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from master_all_strings.core.ingestion.contracts import (
    CanonicalIngestionRequestV1,
    SourceMidiEventV1,
)
from master_all_strings.core.ingestion.results import (
    IngestionRejectionV1,
    IngestionWarningCode,
    IngestionWarningV1,
    RejectionReason,
)
from master_all_strings.core.musical_events.models import MusicalEvent
from master_all_strings.core.score.errors import ScoreContractError
from master_all_strings.core.score.provenance import (
    RoundingPolicy,
    SourceEventProvenanceV1,
)
from master_all_strings.core.score.timing import (
    DEFAULT_TICKS_PER_QUARTER,
    convert_duration,
    convert_elapsed,
)

POLICY_VERSION = "DIRECT_EVENT_IMPORT_V1"


@dataclass(frozen=True)
class ImportOutcome:
    """Everything the policy produced from one request."""

    events: tuple[MusicalEvent, ...]
    event_provenance: tuple[SourceEventProvenanceV1, ...]
    warnings: tuple[IngestionWarningV1, ...]
    rejections: tuple[IngestionRejectionV1, ...]

    @property
    def accepted_count(self) -> int:
        """How many canonical events were produced."""
        return len(self.events)

    @property
    def rejected_count(self) -> int:
        """How many source events were refused."""
        return sum(len(r.source_event_ids) for r in self.rejections)


@dataclass(frozen=True)
class _OpenNote:
    """A sounding note waiting for its release."""

    source_event: SourceMidiEventV1
    ordinal: int


def _rejection(
    reason: RejectionReason, detail: str, source_event_ids: tuple[str, ...]
) -> IngestionRejectionV1:
    return IngestionRejectionV1(
        schema_version=IngestionRejectionV1.SCHEMA_VERSION,
        reason=reason,
        detail=detail,
        source_event_ids=source_event_ids,
    )


def import_direct_events(request: CanonicalIngestionRequestV1) -> ImportOutcome:
    """Convert a request's source events into canonical events and provenance."""
    ticks_per_quarter = request.ticks_per_quarter or DEFAULT_TICKS_PER_QUARTER
    mpq = request.tempo_microseconds_per_quarter
    origin = request.capture_origin_ns

    events: list[MusicalEvent] = []
    provenance: list[SourceEventProvenanceV1] = []
    warnings: list[IngestionWarningV1] = []
    rejections: list[IngestionRejectionV1] = []

    open_notes: defaultdict[tuple[int, int], deque[_OpenNote]] = defaultdict(deque)
    unresolved_string_ids: list[str] = []
    rounded_ids: list[str] = []

    # Order by capture time, then by the source order the capture recorded. A capture
    # already guarantees non-decreasing timestamps, so this is a stability measure
    # rather than a correction.
    ordered = sorted(
        enumerate(request.source_events), key=lambda pair: (pair[1].capture_time_ns, pair[0])
    )

    for ordinal, event in ordered:
        if event.capture_time_ns < origin:
            rejections.append(
                _rejection(
                    RejectionReason.EVENT_BEFORE_CAPTURE_ORIGIN,
                    f"event at {event.capture_time_ns} ns precedes capture origin {origin}",
                    (event.source_event_id,),
                )
            )
            continue

        key = (event.channel, event.midi_note)
        if event.releases_a_note:
            queue = open_notes[key]
            if not queue:
                rejections.append(
                    _rejection(
                        RejectionReason.UNMATCHED_NOTE_OFF,
                        f"release for channel {event.channel} note {event.midi_note} "
                        "has no open note",
                        (event.source_event_id,),
                    )
                )
                continue
            onset = queue.popleft()  # FIFO
            converted = _convert_note(
                onset.source_event,
                event,
                origin=origin,
                ticks_per_quarter=ticks_per_quarter,
                mpq=mpq,
            )
            if isinstance(converted, IngestionRejectionV1):
                rejections.append(converted)
                continue
            musical_event, event_provenance = converted
            events.append(musical_event)
            provenance.append(event_provenance)
            if onset.source_event.observed_source_string is None:
                unresolved_string_ids.append(onset.source_event.source_event_id)
            if event_provenance.rounding_delta_start_ns or (
                event_provenance.rounding_delta_duration_ns
            ):
                rounded_ids.append(musical_event.event_id)
            continue

        open_notes[key].append(_OpenNote(source_event=event, ordinal=ordinal))

    # Anything still sounding never got a release. DO-006 preserved those deliberately
    # as evidence; inventing an ending here would destroy that.
    still_open = tuple(
        note.source_event.source_event_id
        for queue in open_notes.values()
        for note in queue
    )
    if still_open:
        rejections.append(
            _rejection(
                RejectionReason.UNMATCHED_NOTE_ON,
                f"{len(still_open)} note-on event(s) were never released; "
                "refusing to synthesize a note-off",
                tuple(sorted(still_open)),
            )
        )

    if unresolved_string_ids:
        warnings.append(
            IngestionWarningV1(
                schema_version=IngestionWarningV1.SCHEMA_VERSION,
                code=IngestionWarningCode.SOURCE_STRING_UNRESOLVED,
                detail=(
                    f"{len(unresolved_string_ids)} event(s) carried no observed source "
                    "string; TAB projection will compute candidates instead"
                ),
                source_event_ids=tuple(sorted(unresolved_string_ids)),
            )
        )
    if rounded_ids:
        warnings.append(
            IngestionWarningV1(
                schema_version=IngestionWarningV1.SCHEMA_VERSION,
                code=IngestionWarningCode.ROUNDING_APPLIED,
                detail=(
                    f"{len(rounded_ids)} event(s) required tick-grid rounding; "
                    "the residue is recorded per event in provenance"
                ),
                source_event_ids=tuple(sorted(rounded_ids)),
            )
        )
    if any(event.channel != 0 for event in request.source_events):
        warnings.append(
            IngestionWarningV1(
                schema_version=IngestionWarningV1.SCHEMA_VERSION,
                code=IngestionWarningCode.CHANNEL_NOT_MAPPED_TO_VOICE,
                detail=(
                    "MIDI channel is recorded in provenance and not mapped to voice_id; "
                    "channel and musical voice are not equivalent"
                ),
            )
        )

    return ImportOutcome(
        events=tuple(events),
        event_provenance=tuple(provenance),
        warnings=tuple(warnings),
        rejections=tuple(rejections),
    )


def _convert_note(
    onset: SourceMidiEventV1,
    release: SourceMidiEventV1,
    *,
    origin: int,
    ticks_per_quarter: int,
    mpq: int,
) -> tuple[MusicalEvent, SourceEventProvenanceV1] | IngestionRejectionV1:
    """Build one canonical event, or explain why it cannot exist."""
    start = convert_elapsed(
        onset.capture_time_ns - origin,
        ticks_per_quarter=ticks_per_quarter,
        microseconds_per_quarter=mpq,
    )
    try:
        duration = convert_duration(
            onset.capture_time_ns,
            release.capture_time_ns,
            ticks_per_quarter=ticks_per_quarter,
            microseconds_per_quarter=mpq,
        )
    except ScoreContractError as exc:
        if "DURATION_BELOW_ONE_TICK" not in str(exc):
            raise
        return _rejection(
            RejectionReason.DURATION_BELOW_ONE_TICK,
            str(exc),
            (onset.source_event_id, release.source_event_id),
        )

    # Event ids are derived from the onset, so re-ingesting the same capture produces
    # the same canonical ids and therefore the same digest.
    canonical_event_id = f"ev-{onset.source_event_id}"
    musical_event = MusicalEvent(
        event_id=canonical_event_id,
        midi_note=onset.midi_note,
        start_tick=start.ticks,
        duration_ticks=duration.ticks,
        velocity=onset.velocity,
        voice_id=None,  # never derived from channel
    )
    event_provenance = SourceEventProvenanceV1(
        schema_version=SourceEventProvenanceV1.SCHEMA_VERSION,
        canonical_event_id=canonical_event_id,
        source_capture_event_ids=(onset.source_event_id, release.source_event_id),
        source_channel=onset.channel,
        observed_source_string=onset.observed_source_string,
        source_capture_time_ns=onset.capture_time_ns,
        source_release_time_ns=release.capture_time_ns,
        converted_start_tick=start.ticks,
        converted_duration_ticks=duration.ticks,
        rounding_delta_start_ns=start.rounding_delta_ns,
        rounding_delta_duration_ns=duration.rounding_delta_ns,
        rounding_policy=RoundingPolicy.ROUND_HALF_AWAY_FROM_ZERO,
        ticks_per_quarter=ticks_per_quarter,
        microseconds_per_quarter=mpq,
    )
    return musical_event, event_provenance
