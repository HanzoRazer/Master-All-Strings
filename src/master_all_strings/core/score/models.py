"""Canonical score document and revision contracts (ADR-0008).

Two objects with different lifetimes. ``ScoreDocumentV1`` is the continuing identity of
a work and survives every edit; ``CanonicalScoreRevisionV1`` is one immutable state of
it and never changes.

Neither type is the normal construction path. A caller builds revisions through
``CanonicalRevisionService`` (A4), which owns lineage and numbering. The validation here
is structural: it makes an invalid revision unrepresentable, so the service cannot
create one by mistake and a hand-built one in a test cannot be quietly wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from master_all_strings.core.musical_events.models import MusicalEvent
from master_all_strings.core.score.errors import (
    REVISION_ID_DIGEST_PREFIX,
    REVISION_ID_PREFIX,
    ScoreContractError,
    require_digest,
    require_identifier,
    require_optional_identifier,
    require_positive_int,
    require_prose,
    require_schema_version,
    require_tuple,
    require_unique,
    require_utc_timestamp,
)
from master_all_strings.core.score.meter import MeterChangeV1
from master_all_strings.core.score.provenance import RevisionProvenanceV1
from master_all_strings.core.score.tempo import TempoChangeV1

# Ticks per quarter note. 960 is the DO-007 conversion basis; the contract permits the
# conventional range so a future import policy is not boxed in.
SUPPORTED_TICKS_PER_QUARTER = (96, 120, 192, 240, 384, 480, 960, 1920)
FIRST_REVISION_NUMBER = 1


@dataclass(frozen=True)
class ScoreDocumentV1:
    """The stable identity of a musical work.

    Holds identity and a pointer to the current revision, and deliberately nothing
    else. It carries no events, tempo, or meter: duplicating revision content here
    would create a second place for the music to live, and the two would drift.
    """

    schema_version: str
    document_id: str
    created_at: str
    current_revision_id: str
    revision_count: int
    title: str | None = None
    description: str | None = None
    external_reference: str | None = None

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.document_id, "document_id")
        require_utc_timestamp(self.created_at, "created_at")
        require_identifier(self.current_revision_id, "current_revision_id")
        require_positive_int(self.revision_count, "revision_count")
        # Title and description are prose; external_reference is a key into some other
        # system and is held to identifier rules. Title was validated as an identifier
        # too, which forbade the inner formatting a real title may carry for no benefit:
        # nothing keys on a title and the digest excludes it, so an identifier rule was
        # borrowed strictness with no invariant behind it.
        if self.title is not None:
            require_prose(self.title, "title")
        if self.description is not None:
            require_prose(self.description, "description")
        require_optional_identifier(self.external_reference, "external_reference")

    def with_revision(
        self, *, current_revision_id: str, revision_count: int
    ) -> ScoreDocumentV1:
        """Return a copy advanced to a new current revision.

        The count must strictly increase. Refusing a decrease stops a stale write from
        silently undoing an accepted revision; refusing an *equal* count closes the
        other half of the same hole. ``revision_count`` is how many revisions the
        document has, so repointing at a different revision without advancing it would
        leave the number disagreeing with the history the repository can list, and would
        describe adding a revision as if none had been added. Advancing the pointer is
        the only reason to call this, and every advance is a new revision.
        """
        require_identifier(current_revision_id, "current_revision_id")
        require_positive_int(revision_count, "revision_count")
        if revision_count <= self.revision_count:
            raise ScoreContractError(
                f"revision_count must increase ({revision_count} does not follow "
                f"{self.revision_count})"
            )
        return ScoreDocumentV1(
            schema_version=self.schema_version,
            document_id=self.document_id,
            created_at=self.created_at,
            current_revision_id=current_revision_id,
            revision_count=revision_count,
            title=self.title,
            description=self.description,
            external_reference=self.external_reference,
        )


@dataclass(frozen=True)
class CanonicalScoreRevisionV1:
    """One immutable state of a score document.

    Every collection is a tuple and the dataclass is frozen, so a revision cannot be
    edited after construction — only superseded by a new revision that cites it as
    parent.
    """

    schema_version: str
    revision_id: str
    document_id: str
    revision_number: int
    parent_revision_id: str | None
    created_at: str
    ticks_per_quarter: int
    content_digest: str
    provenance: RevisionProvenanceV1
    events: tuple[MusicalEvent, ...] = ()
    tempo_changes: tuple[TempoChangeV1, ...] = ()
    meter_changes: tuple[MeterChangeV1, ...] = ()

    SCHEMA_VERSION = "1.0.0"

    def __post_init__(self) -> None:
        require_schema_version(self.schema_version, self.SCHEMA_VERSION)
        require_identifier(self.revision_id, "revision_id")
        require_identifier(self.document_id, "document_id")
        require_positive_int(self.revision_number, "revision_number")
        require_utc_timestamp(self.created_at, "created_at")
        require_digest(self.content_digest, "content_digest")

        if self.ticks_per_quarter not in SUPPORTED_TICKS_PER_QUARTER:
            raise ScoreContractError(
                f"ticks_per_quarter must be one of {list(SUPPORTED_TICKS_PER_QUARTER)}"
            )
        if not isinstance(self.provenance, RevisionProvenanceV1):
            raise ScoreContractError("provenance must be a RevisionProvenanceV1")

        self._validate_lineage()
        self._validate_revision_id()
        self._validate_events()
        self._validate_tempo_map()
        self._validate_meter_map()

    def _validate_lineage(self) -> None:
        first = self.revision_number == FIRST_REVISION_NUMBER
        if first and self.parent_revision_id is not None:
            raise ScoreContractError(
                "revision 1 is the origin of a document and must have no parent"
            )
        if not first and self.parent_revision_id is None:
            raise ScoreContractError(
                f"revision {self.revision_number} requires a parent_revision_id"
            )
        if self.parent_revision_id is not None:
            require_identifier(self.parent_revision_id, "parent_revision_id")
            if self.parent_revision_id == self.revision_id:
                raise ScoreContractError("a revision must not be its own parent")

    def _validate_revision_id(self) -> None:
        # The id is derived from the digest, so a mismatch means one of the two was
        # edited independently -- which would break every citation of this revision.
        expected = REVISION_ID_PREFIX + self.content_digest[:REVISION_ID_DIGEST_PREFIX]
        if self.revision_id != expected:
            raise ScoreContractError(
                f"revision_id must be derived from content_digest; expected {expected!r}"
            )

    def _validate_events(self) -> None:
        require_tuple(self.events, "events")
        for event in self.events:
            if not isinstance(event, MusicalEvent):
                raise ScoreContractError("events must contain MusicalEvent values")
        require_unique([event.event_id for event in self.events], "event_id")

    def _validate_tempo_map(self) -> None:
        require_tuple(self.tempo_changes, "tempo_changes")
        for change in self.tempo_changes:
            if not isinstance(change, TempoChangeV1):
                raise ScoreContractError("tempo_changes must contain TempoChangeV1 values")
        if not self.tempo_changes:
            raise ScoreContractError("tempo_changes must declare a tempo at tick 0")
        if self.tempo_changes[0].tick != 0:
            raise ScoreContractError("the first tempo change must be at tick 0")
        self._require_strictly_increasing(
            [change.tick for change in self.tempo_changes], "tempo_changes"
        )

    def _validate_meter_map(self) -> None:
        require_tuple(self.meter_changes, "meter_changes")
        for change in self.meter_changes:
            if not isinstance(change, MeterChangeV1):
                raise ScoreContractError("meter_changes must contain MeterChangeV1 values")
        if not self.meter_changes:
            raise ScoreContractError("meter_changes must declare a meter at tick 0")
        if self.meter_changes[0].tick != 0:
            raise ScoreContractError("the first meter change must be at tick 0")
        self._require_strictly_increasing(
            [change.tick for change in self.meter_changes], "meter_changes"
        )

    @staticmethod
    def _require_strictly_increasing(ticks: list[int], field_name: str) -> None:
        for previous, current in zip(ticks, ticks[1:], strict=False):
            if current <= previous:
                raise ScoreContractError(
                    f"{field_name} ticks must strictly increase; {current} followed {previous}"
                )

    @property
    def is_origin(self) -> bool:
        """Whether this is the first revision of its document."""
        return self.revision_number == FIRST_REVISION_NUMBER

    @property
    def event_count(self) -> int:
        """How many canonical events this revision holds."""
        return len(self.events)

    def tempo_at_tick(self, tick: int) -> TempoChangeV1:
        """The tempo in effect at ``tick``."""
        effective = self.tempo_changes[0]
        for change in self.tempo_changes:
            if change.tick <= tick:
                effective = change
            else:
                break
        return effective

    def meter_at_tick(self, tick: int) -> MeterChangeV1:
        """The meter in effect at ``tick``."""
        effective = self.meter_changes[0]
        for change in self.meter_changes:
            if change.tick <= tick:
                effective = change
            else:
                break
        return effective
