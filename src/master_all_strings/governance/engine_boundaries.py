"""Validate the four-engine architecture registry and its Markdown views.

The constitutional source of truth is ``governance/engine_architecture_v1.json``.
This module loads it, checks the invariants ratified in ADR-0006, and renders the
canonical Markdown views. A committed view that disagrees with the JSON, or a JSON
change not reflected in the views, is a governance violation surfaced by the tests
in ``tests/governance/``.

Run directly for a local check::

    python -m master_all_strings.governance.engine_boundaries
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, NamedTuple, cast

ENGINE_IDS = ("MUSICAL_CORE", "EDUCATIONAL_ENGINE", "CREATIVE_ENGINE", "PERFORMANCE_ENGINE")
_NON_PROHIBITED = frozenset({"depends", "consumes_evidence", "consumes_contracts"})

_REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = _REPO_ROOT / "governance" / "engine_architecture_v1.json"
SCHEMA_PATH = _REPO_ROOT / "schemas" / "engine_architecture_v1.schema.json"
VIEW_DIR = _REPO_ROOT / "docs" / "architecture"

# Contract names fixed by the DO-005 seam rulings, with their required owner.
_FIXED_CONTRACT_OWNERS = {
    "SpatialEvidenceV1": "MUSICAL_CORE",
    "EducationalInterpretationV1": "EDUCATIONAL_ENGINE",
    "PerformanceObservationV1": "PERFORMANCE_ENGINE",
    "CoachingRecommendationV1": "EDUCATIONAL_ENGINE",
}


class Violation(NamedTuple):
    """A single governance-boundary violation."""

    code: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.detail}"


def load_registry(path: Path | None = None) -> dict[str, Any]:
    """Load and return the machine-readable architecture registry.

    ``REGISTRY_PATH`` is resolved at call time (not captured as a default) so the
    path stays a single overridable source.
    """

    text = (path or REGISTRY_PATH).read_text(encoding="utf-8")
    return cast("dict[str, Any]", json.loads(text))


def _relation(reg: Mapping[str, Any], frm: str, to: str) -> str | None:
    for rule in reg["dependency_rules"]:
        if rule["from"] == frm and rule["to"] == to:
            return str(rule["relation"])
    return None


def validate_registry(reg: Mapping[str, Any]) -> list[Violation]:
    """Return every constitutional-boundary violation in ``reg`` (empty if clean)."""

    v: list[Violation] = []
    v.extend(_check_engines(reg))
    v.extend(_check_dependency_matrix(reg))
    v.extend(_check_capabilities(reg))
    v.extend(_check_contracts(reg))
    v.extend(_check_seams(reg))
    v.extend(_check_adrs(reg))
    return v


def _check_engines(reg: Mapping[str, Any]) -> list[Violation]:
    v: list[Violation] = []
    engine_ids = [e["id"] for e in reg["engines"]]
    if set(engine_ids) != set(ENGINE_IDS):
        v.append(Violation("ENGINES", f"engine set must be {sorted(ENGINE_IDS)}"))
    if len(engine_ids) != len(set(engine_ids)):
        v.append(Violation("ENGINES", "duplicate engine id"))
    free = [e["id"] for e in reg["engines"] if e.get("depends_on_none")]
    if free != ["MUSICAL_CORE"]:
        v.append(
            Violation("CORE_INDEPENDENT", f"only MUSICAL_CORE may be dependency-free, got {free}")
        )
    return v


def _check_dependency_matrix(reg: Mapping[str, Any]) -> list[Violation]:
    v: list[Violation] = []
    pairs = [(r["from"], r["to"]) for r in reg["dependency_rules"]]
    expected = {(a, b) for a in ENGINE_IDS for b in ENGINE_IDS if a != b}
    if set(pairs) != expected:
        missing = sorted(expected - set(pairs))
        extra = sorted(set(pairs) - expected)
        v.append(Violation("MATRIX", f"matrix incomplete; missing={missing} extra={extra}"))
    if len(pairs) != len(set(pairs)):
        v.append(Violation("MATRIX", "duplicate dependency rule"))
    for rule in reg["dependency_rules"]:
        if rule["from"] == "MUSICAL_CORE" and rule["relation"] != "prohibited":
            v.append(Violation("CORE_DEPENDS", f"Musical Core must not depend on {rule['to']}"))
    return v


def _check_capabilities(reg: Mapping[str, Any]) -> list[Violation]:
    v: list[Violation] = []
    seen: set[str] = set()
    for cap in reg["capabilities"]:
        cid = cap["id"]
        if cid in seen:
            v.append(Violation("CAP_DUP", f"duplicate capability id {cid!r}"))
        seen.add(cid)
        owner = cap["owning_engine"]
        for consumer in cap["permitted_consumers"]:
            if consumer == owner:
                v.append(
                    Violation("CAP_SELF", f"capability {cid!r} lists its own owner as consumer")
                )
                continue
            if _relation(reg, consumer, owner) not in _NON_PROHIBITED:
                v.append(
                    Violation("CAP_DEP", f"capability {cid!r}: {consumer} cannot depend on {owner}")
                )
        v.extend(_check_classification(f"capability {cid!r}", owner, cap["classification"]))
        if owner == "PERFORMANCE_ENGINE" and cap["classification"] == "interpretation":
            v.append(
                Violation("PERF_POLICY", f"{cid!r}: Performance may not own interpretation")
            )
    return v


def _check_contracts(reg: Mapping[str, Any]) -> list[Violation]:
    v: list[Violation] = []
    seen: set[str] = set()
    by_name = {c["name"]: c for c in reg["contracts"]}
    for con in reg["contracts"]:
        name = con["name"]
        if name in seen:
            v.append(Violation("CON_DUP", f"duplicate contract {name!r}"))
        seen.add(name)
        owner = con["owning_engine"]
        if con["versioning_authority"] != owner:
            v.append(
                Violation("CON_VERSION", f"{name!r}: versioning authority must be owner")
            )
        producer = con["producer"]
        if producer != owner and _relation(reg, producer, owner) not in _NON_PROHIBITED:
            v.append(
                Violation("CON_DEP", f"{name!r}: producer {producer} cannot depend on {owner}")
            )
        for consumer in con["consumers"]:
            if consumer == owner:
                continue
            if _relation(reg, consumer, owner) not in _NON_PROHIBITED:
                v.append(
                    Violation("CON_DEP", f"{name!r}: consumer {consumer} cannot depend on {owner}")
                )
        v.extend(_check_classification(f"contract {name!r}", owner, con["classification"]))
        v.extend(_check_citation(name, con, by_name))
    return v


def _check_citation(
    name: str, con: Mapping[str, Any], by_name: Mapping[str, Any]
) -> list[Violation]:
    cited = con.get("cites")
    if cited is None:
        return []
    v: list[Violation] = []
    if cited not in by_name:
        v.append(Violation("CON_CITE", f"contract {name!r} cites unknown contract {cited!r}"))
        return v
    if con["classification"] != "interpretation":
        v.append(Violation("CON_CITE", f"only interpretation contracts cite; {name!r} does not"))
    if by_name[cited]["classification"] != "evidence":
        v.append(Violation("CON_CITE", f"contract {name!r} must cite an evidence contract"))
    return v


def _check_seams(reg: Mapping[str, Any]) -> list[Violation]:
    v: list[Violation] = []
    by_name = {c["name"]: c for c in reg["contracts"]}
    for cname, req_owner in _FIXED_CONTRACT_OWNERS.items():
        if cname not in by_name:
            v.append(Violation("SEAM", f"required contract {cname!r} is missing"))
        elif by_name[cname]["owning_engine"] != req_owner:
            v.append(Violation("SEAM", f"contract {cname!r} must be owned by {req_owner}"))
    return v


def _check_adrs(reg: Mapping[str, Any]) -> list[Violation]:
    v: list[Violation] = []
    adrs: dict[str, dict[str, Any]] = {}
    for a in reg["adr_assignments"]:
        if a["adr"] in adrs:
            v.append(Violation("ADR_DUP", f"ADR number {a['adr']} assigned twice"))
        adrs[a["adr"]] = a
    a5 = adrs.get("ADR-0005", {})
    if a5.get("status") != "reserved" or a5.get("owner") != "DO-004":
        v.append(Violation("ADR_0005", "ADR-0005 must remain reserved for DO-004"))
    if adrs.get("ADR-0006", {}).get("status") != "accepted":
        v.append(Violation("ADR_0006", "ADR-0006 (four-engine architecture) must be accepted"))
    return v


def _check_classification(label: str, owner: str, classification: str) -> list[Violation]:
    """Evidence is owned by Core or Performance; interpretation only by Education."""

    if classification == "interpretation" and owner != "EDUCATIONAL_ENGINE":
        return [Violation("CLASS", f"{label}: interpretation must be owned by Educational")]
    if classification == "evidence" and owner not in ("MUSICAL_CORE", "PERFORMANCE_ENGINE"):
        return [Violation("CLASS", f"{label}: evidence must be owned by Core or Performance")]
    return []


# --- Markdown view rendering (deterministic; the committed views must match) ---

_GENERATED_HEADER = (
    "<!-- GENERATED from governance/engine_architecture_v1.json — do not edit by hand. -->\n"
    "<!-- Regenerate: python -m master_all_strings.governance.engine_boundaries --write-views -->\n"
)
_ENGINE_NAME = {
    "MUSICAL_CORE": "Musical Core",
    "EDUCATIONAL_ENGINE": "Educational",
    "CREATIVE_ENGINE": "Creative",
    "PERFORMANCE_ENGINE": "Performance",
}
_RELATION_CELL = {
    "depends": "depends",
    "consumes_evidence": "evidence only",
    "consumes_contracts": "contracts only",
    "prohibited": "no",
}


def render_dependency_matrix(reg: Mapping[str, Any]) -> str:
    lines = [
        _GENERATED_HEADER,
        "# Engine Dependency Matrix\n",
        'Read a row as "may the row engine depend on the column engine?" '
        "Generated from the constitutional registry.\n",
    ]
    cols = " | ".join(_ENGINE_NAME[e] for e in ENGINE_IDS)
    lines.append(f"| Depends on ↓ / Engine → | {cols} |")
    lines.append("| --- | " + " | ".join("---" for _ in ENGINE_IDS) + " |")
    for frm in ENGINE_IDS:
        cells = []
        for to in ENGINE_IDS:
            if frm == to:
                cells.append("—")
            else:
                cells.append(_RELATION_CELL[_relation(reg, frm, to) or "prohibited"])
        lines.append(f"| **{_ENGINE_NAME[frm]}** | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def render_ownership_registry(reg: Mapping[str, Any]) -> str:
    lines = [
        _GENERATED_HEADER,
        "# Engine Ownership Registry\n",
        "Every capability has exactly one authoritative owning engine. "
        "Generated from the constitutional registry.\n",
        "| Capability ID | Capability | Owning engine | Permitted consumers "
        "| Classification | Status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for cap in reg["capabilities"]:
        consumers = ", ".join(_ENGINE_NAME[c] for c in cap["permitted_consumers"]) or "—"
        lines.append(
            f"| `{cap['id']}` | {cap['name']} | {_ENGINE_NAME[cap['owning_engine']]} "
            f"| {consumers} | {cap['classification']} | {cap['implementation_status']} |"
        )
    return "\n".join(lines) + "\n"


def render_contract_ownership(reg: Mapping[str, Any]) -> str:
    lines = [
        _GENERATED_HEADER,
        "# Engine Contract Ownership\n",
        "Every cross-engine contract has exactly one owning engine and one versioning "
        "authority. Generated from the constitutional registry.\n",
        "| Contract | Owning engine | Producer | Consumers | Mutability "
        "| Classification | Cites | Versioning authority |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for con in reg["contracts"]:
        consumers = ", ".join(_ENGINE_NAME[c] for c in con["consumers"]) or "—"
        cites = con.get("cites") or "—"
        lines.append(
            f"| `{con['name']}` | {_ENGINE_NAME[con['owning_engine']]} "
            f"| {_ENGINE_NAME[con['producer']]} | {consumers} | {con['mutability']} "
            f"| {con['classification']} | {cites} | {_ENGINE_NAME[con['versioning_authority']]} |"
        )
    return "\n".join(lines) + "\n"


VIEWS: dict[str, Any] = {
    "ENGINE_DEPENDENCY_MATRIX.md": render_dependency_matrix,
    "ENGINE_OWNERSHIP_REGISTRY.md": render_ownership_registry,
    "ENGINE_CONTRACT_OWNERSHIP.md": render_contract_ownership,
}


def check_views(reg: Mapping[str, Any], view_dir: Path = VIEW_DIR) -> list[Violation]:
    """Return a violation for every committed view that differs from the rendered one."""

    v: list[Violation] = []
    for filename, render in VIEWS.items():
        path = view_dir / filename
        expected = render(reg)
        if not path.exists():
            v.append(
                Violation("VIEW_MISSING", f"{filename} missing; regenerate with --write-views")
            )
            continue
        if path.read_text(encoding="utf-8") != expected:
            v.append(Violation("VIEW_STALE", f"{filename} disagrees with the registry"))
    return v


def write_views(reg: Mapping[str, Any], view_dir: Path = VIEW_DIR) -> None:
    """Write the canonical Markdown views from the registry."""

    for filename, render in VIEWS.items():
        (view_dir / filename).write_text(render(reg), encoding="utf-8")


def _format(violations: Iterable[Violation]) -> str:
    items = list(violations)
    if not items:
        return "engine boundaries: OK"
    return "engine boundary violations:\n" + "\n".join(f"  {x}" for x in items)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 when clean, 1 on any violation."""

    args = sys.argv[1:] if argv is None else argv
    reg = load_registry()
    if "--write-views" in args:
        write_views(reg)
        print("wrote engine architecture views")
        return 0
    violations = validate_registry(reg) + check_views(reg)
    print(_format(violations))
    return 1 if violations else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
