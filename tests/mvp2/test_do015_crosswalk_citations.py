"""The Stage 8 coverage crosswalk must cite tests that exist, where it says.

A crosswalk is an evidence claim: each cell asserts that some test already
locks that authority cell. Cited by name alone, the claim rots silently -- a
rename leaves the row reading as verified while pointing at nothing. Four cells
were already citing paraphrases rather than real test names when the citations
were first resolved.

So each cell names ``path:line``, and this reads them back.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN = REPO_ROOT / "docs" / "mvp2" / "DO015_TRANCHE_PLAN.md"

#: ``path:line`` followed by `` :: `` and the test's name. The name runs to the
#: next `;`, the cell's end, or a sentence break -- a cell may add a note after
#: its citations, and no test here is named with one.
_CITATION = re.compile(r"`([\w./-]+):(\d+)`\s*::\s*([^;|\n]+?)(?=\s*(?:;|\||\.\s|$))")


def _crosswalk() -> str:
    text = PLAN.read_text(encoding="utf-8")
    start = text.index("### Coverage crosswalk")
    return text[start : text.index("\n## ", start)]


def _citations() -> list[tuple[str, int, str]]:
    return [
        (match.group(1), int(match.group(2)), match.group(3).strip())
        for match in _CITATION.finditer(_crosswalk())
    ]


def test_the_crosswalk_cites_every_cell() -> None:
    table = [
        line
        for line in _crosswalk().splitlines()
        if line.startswith("| ") and not line.startswith(("| ---", "| Cell"))
    ]
    assert len(table) >= 40, "the crosswalk lost rows"
    uncited = [line for line in table if not _CITATION.search(line)]
    assert uncited == [], f"cells with no path:line citation: {uncited}"
    # "same test" was how a cell used to point at its neighbour. A citation
    # that cannot be followed on its own is the thing this file prevents.
    assert "same test" not in _crosswalk()


@pytest.mark.parametrize(("path", "line", "name"), _citations(), ids=lambda value: str(value))
def test_each_citation_names_a_test_that_is_there(path: str, line: int, name: str) -> None:
    target = REPO_ROOT / path
    assert target.exists(), f"{path} does not exist"
    lines = target.read_text(encoding="utf-8").splitlines()
    assert 1 <= line <= len(lines), f"{path}:{line} is past the end of the file"
    cited = lines[line - 1]
    if path.endswith(".py"):
        assert cited.strip().startswith(f"def {name}("), f"{path}:{line} is not def {name}"
    else:
        assert cited.strip().startswith(f'test("{name}"'), f'{path}:{line} is not test("{name}")'


def test_citations_point_at_distinct_evidence() -> None:
    # Two cells may legitimately share a test, but a citation repeated across
    # most of the table would mean the crosswalk is thinner than it reads.
    seen = [f"{path}:{line}" for path, line, _ in _citations()]
    assert len(set(seen)) >= len(seen) * 0.7, "the crosswalk leans on too few tests"
