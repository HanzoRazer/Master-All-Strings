"""Document identity, from an injected authority.

A document id survives every revision, so it cannot be content-addressed the way a
revision id is. It has to come from somewhere, and that somewhere is injected rather
than reached for globally.

Production code must never call ``uuid4`` or ``random`` inline. Two reasons: a test
cannot reproduce a run, and hidden randomness in an identity path is the kind of thing
that works until it has to be audited. ``DeterministicDocumentIdAuthority`` makes a test
byte-reproducible; ``UuidDocumentIdAuthority`` is the normal implementation.

No timestamp is ever used as identity (ADR-0008 D7). Two documents created in the same
millisecond would collide, and a clock adjustment could make an id repeat.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from master_all_strings.core.score.errors import (
    ScoreContractError,
    require_identifier,
    require_positive_int,
)

DOCUMENT_ID_PREFIX = "score-"


def format_document_id(suffix: str) -> str:
    """Return a prefixed document id, validating the result."""
    require_identifier(suffix, "document id suffix")
    document_id = DOCUMENT_ID_PREFIX + suffix
    require_identifier(document_id, "document_id")
    return document_id


#: Characters a lesson content id may contribute to a document id. Authored ids
#: are slugs, so anything outside this set means the caller passed something that
#: was never a lesson identity -- a path, a title, a digest.
_LESSON_ID_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789_-")


@runtime_checkable
class DocumentIdAuthority(Protocol):
    """Issues document identities. Injected, never global."""

    def next_document_id(self) -> str:
        """Return a fresh document id."""
        ...


class UuidDocumentIdAuthority:
    """Issues UUID4-backed document ids. The normal implementation."""

    def next_document_id(self) -> str:
        """Return ``score-<uuid4 hex>``."""
        return format_document_id(uuid.uuid4().hex)


class DeterministicDocumentIdAuthority:
    """Issues predictable, sequential document ids for tests and fixtures.

    Reproducible by construction: the same authority replays the same sequence, so a
    test asserting on a document id does not have to match a pattern.
    """

    def __init__(self, *, prefix: str = "test", start: int = 1, width: int = 4) -> None:
        require_identifier(prefix, "prefix")
        require_positive_int(start, "start")
        require_positive_int(width, "width")
        self._prefix = prefix
        self._next = start
        self._width = width
        self.issued: list[str] = []

    def next_document_id(self) -> str:
        """Return the next id in the sequence."""
        document_id = format_document_id(f"{self._prefix}-{self._next:0{self._width}d}")
        self._next += 1
        self.issued.append(document_id)
        return document_id


class FixedDocumentIdAuthority:
    """Issues one preset id, then refuses.

    For tests that need an exact id and must fail loudly if a second document is
    created unexpectedly -- an accidental second document is a real ingestion defect,
    and a silent second id would hide it.
    """

    def __init__(self, document_id: str) -> None:
        require_identifier(document_id, "document_id")
        self._document_id = document_id
        self._used = False

    def next_document_id(self) -> str:
        """Return the preset id once."""
        if self._used:
            raise ScoreContractError(
                f"FixedDocumentIdAuthority was asked for a second id after issuing "
                f"{self._document_id!r}"
            )
        self._used = True
        return self._document_id


class LessonDocumentIdAuthority:
    """Maps a stable authored-lesson identity to a stable document identity.

    A lesson that keeps its name is the same musical *work* across exports, so it
    must keep its document id; editing its notes then produces a new revision of
    that work rather than a new work. A UUID authority would mint a different
    document -- and therefore a different revision id -- on every export, which
    would make the exported artifacts churn for no musical reason.

    The mapping is over the lesson's identity, never its content. Deriving the
    document id from serialized musical bytes would collapse the two questions
    this design keeps apart: *which work is this* and *which state of it*.
    """

    def __init__(self, content_id: str) -> None:
        require_identifier(content_id, "content_id")
        normalized = content_id.strip().lower()
        illegal = sorted(set(normalized) - _LESSON_ID_ALLOWED)
        if illegal:
            raise ScoreContractError(
                f"lesson content_id contains characters that cannot form a document id: "
                f"{illegal}"
            )
        self._content_id = normalized
        self._document_id = format_document_id(normalized)
        self.issued: list[str] = []

    @property
    def content_id(self) -> str:
        return self._content_id

    @property
    def document_id(self) -> str:
        """The identity this authority will issue, without consuming anything."""
        return self._document_id

    def next_document_id(self) -> str:
        """Return this lesson's document id.

        Unlike the fixed test authority this does not refuse a second call: one
        lesson exported twice is the same work both times, and refusing would make
        re-export an error.
        """
        self.issued.append(self._document_id)
        return self._document_id
