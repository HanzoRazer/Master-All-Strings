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
