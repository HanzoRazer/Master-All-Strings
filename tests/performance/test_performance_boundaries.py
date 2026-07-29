"""Engine-boundary invariants (DO-006 §8.5).

These are the tests that make ADR-0007 enforceable rather than aspirational. They
check the constitutional registry agrees with the code, and — most importantly — that
no runtime-specific vocabulary has leaked across ``PerformanceRuntimePort``.

The leakage test is the one that earns its keep. Coupling to a third-party runtime
does not arrive as a decision; it arrives as one convenient field name.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path
from typing import Any

import pytest
from helpers import REPO_ROOT

from master_all_strings.governance import engine_boundaries as eb
from master_all_strings.performance.contracts import capture as capture_mod
from master_all_strings.performance.contracts import commands as commands_mod
from master_all_strings.performance.contracts import ingestion as ingestion_mod
from master_all_strings.performance.contracts import results as results_mod
from master_all_strings.performance.contracts import runtime as runtime_mod
from master_all_strings.performance.contracts import session as session_mod
from master_all_strings.performance.contracts.capture import PerformanceObservationV1
from master_all_strings.performance.ports import runtime as port_mod

PERFORMANCE_ROOT = REPO_ROOT / "src" / "master_all_strings" / "performance"
ADAPTER_ROOT = PERFORMANCE_ROOT / "adapters"

# Vocabulary that must never appear outside an implementation's own adapter package.
RUNTIME_SPECIFIC_TERMS = ("ardour", "lv2", "osc", "jack", "pipewire", "alsa")

NEUTRAL_MODULES = (
    runtime_mod,
    session_mod,
    capture_mod,
    commands_mod,
    results_mod,
    ingestion_mod,
    port_mod,
)


@pytest.fixture
def registry() -> dict[str, Any]:
    return eb.load_registry()


def _capability(registry: dict[str, Any], capability_id: str) -> dict[str, Any]:
    for capability in registry["capabilities"]:
        if capability["id"] == capability_id:
            return dict(capability)
    raise AssertionError(f"capability {capability_id!r} is not registered")


def _contract(registry: dict[str, Any], name: str) -> dict[str, Any]:
    for contract in registry["contracts"]:
        if contract["name"] == name:
            return dict(contract)
    raise AssertionError(f"contract {name!r} is not registered")


class TestRegistryStaysClean:
    def test_registry_has_no_violations(self, registry: dict[str, Any]) -> None:
        assert eb.validate_registry(registry) == []

    def test_committed_views_match_the_registry(self, registry: dict[str, Any]) -> None:
        assert eb.check_views(registry) == []


class TestPerformanceOwnsTheRuntime:
    @pytest.mark.parametrize(
        "capability_id",
        [
            "embedded-performance-runtime",
            "runtime-orchestration",
            "midi-device-ingestion",
            "synth-routing",
            "transport-control",
            "raw-performance-capture",
            "runtime-diagnostics",
            "performance-studio",
        ],
    )
    def test_runtime_capabilities_belong_to_performance(
        self, registry: dict[str, Any], capability_id: str
    ) -> None:
        assert _capability(registry, capability_id)["owning_engine"] == "PERFORMANCE_ENGINE"

    def test_ardour_is_not_an_engine(self, registry: dict[str, Any]) -> None:
        engine_ids = {e["id"] for e in registry["engines"]}
        assert len(engine_ids) == 4
        assert not any("ARDOUR" in engine_id for engine_id in engine_ids)

    def test_no_capability_or_contract_names_a_runtime(self, registry: dict[str, Any]) -> None:
        for capability in registry["capabilities"]:
            assert "ardour" not in capability["id"].lower()
        for contract in registry["contracts"]:
            assert "ardour" not in contract["name"].lower()


class TestDependencyDirection:
    def test_performance_depends_on_musical_core(self, registry: dict[str, Any]) -> None:
        rules = {(r["from"], r["to"]): r["relation"] for r in registry["dependency_rules"]}
        assert rules[("PERFORMANCE_ENGINE", "MUSICAL_CORE")] == "depends"

    def test_educational_consumes_performance_evidence_only(
        self, registry: dict[str, Any]
    ) -> None:
        rules = {(r["from"], r["to"]): r["relation"] for r in registry["dependency_rules"]}
        assert rules[("EDUCATIONAL_ENGINE", "PERFORMANCE_ENGINE")] == "consumes_evidence"

    def test_creative_does_not_depend_on_performance(self, registry: dict[str, Any]) -> None:
        rules = {(r["from"], r["to"]): r["relation"] for r in registry["dependency_rules"]}
        assert rules[("CREATIVE_ENGINE", "PERFORMANCE_ENGINE")] == "prohibited"

    def test_performance_code_imports_no_other_engine(self) -> None:
        # Performance may depend on Musical Core and nothing else.
        forbidden = ("educational", "creative", "practice", "sequencer")
        for path in PERFORMANCE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not any(term in node.module for term in forbidden), (
                        f"{path.name} imports {node.module}"
                    )


class TestMusicalCoreRemainsCanonical:
    def test_ingestion_request_is_owned_by_musical_core(self, registry: dict[str, Any]) -> None:
        # Core owns the vocabulary for changing the canonical model, exactly as it
        # owns ScoreEditCommandSet that Creative produces.
        contract = _contract(registry, "CanonicalIngestionRequestV1")
        assert contract["owning_engine"] == "MUSICAL_CORE"
        assert contract["producer"] == "PERFORMANCE_ENGINE"
        assert contract["versioning_authority"] == "MUSICAL_CORE"

    @pytest.mark.parametrize(
        "capability_id",
        ["piano-roll-projection", "notation-projection", "tab-projection", "midi-projection"],
    )
    def test_projections_belong_to_musical_core(
        self, registry: dict[str, Any], capability_id: str
    ) -> None:
        assert _capability(registry, capability_id)["owning_engine"] == "MUSICAL_CORE"

    def test_piano_roll_is_not_owned_by_performance(self, registry: dict[str, Any]) -> None:
        # A Performance-owned editable note collection is one refactor away from a
        # second authoritative score (ADR-0007 D8).
        capability = _capability(registry, "piano-roll-projection")
        assert capability["owning_engine"] == "MUSICAL_CORE"
        assert "PERFORMANCE_ENGINE" not in capability["permitted_consumers"]

    def test_performance_reaches_projections_through_projection_result(
        self, registry: dict[str, Any]
    ) -> None:
        # Displaying a projection during review is legitimate; owning a note model
        # is not. ProjectionResult is the sanctioned route.
        assert "PERFORMANCE_ENGINE" in _contract(registry, "ProjectionResult")["consumers"]

    def test_no_performance_module_defines_a_score_revision(self) -> None:
        for path in PERFORMANCE_ROOT.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for line in source.splitlines():
                if line.startswith("class ") and "Revision" in line:
                    raise AssertionError(
                        f"{path.name} defines a revision type; "
                        "canonical revisions belong to Musical Core"
                    )


class TestPerformanceEmitsEvidenceNotCoaching:
    def test_performance_owns_no_interpretation_capability(
        self, registry: dict[str, Any]
    ) -> None:
        for capability in registry["capabilities"]:
            if capability["owning_engine"] == "PERFORMANCE_ENGINE":
                assert capability["classification"] != "interpretation", capability["id"]

    def test_educational_consumes_the_observation(self, registry: dict[str, Any]) -> None:
        assert "EDUCATIONAL_ENGINE" in _contract(registry, "PerformanceObservationV1")["consumers"]

    def test_coaching_recommendation_is_educational(self, registry: dict[str, Any]) -> None:
        contract = _contract(registry, "CoachingRecommendationV1")
        assert contract["owning_engine"] == "EDUCATIONAL_ENGINE"
        assert contract["cites"] == "PerformanceObservationV1"

    def test_performance_defines_no_coaching_contract(self) -> None:
        for module in NEUTRAL_MODULES:
            for name in dir(module):
                assert "Coaching" not in name, f"{module.__name__}.{name}"
                assert "Curriculum" not in name, f"{module.__name__}.{name}"

    def test_observation_carries_no_pedagogical_field(self) -> None:
        # An allowlist, because the boundary erodes one plausible field at a time.
        banned = (
            "mastery",
            "mastered",
            "difficulty",
            "difficult",
            "beginner",
            "advanced",
            "skill",
            "grade",
            "score",
            "quality",
            "technique",
            "recommend",
            "curriculum",
            "lesson",
            "level",
            "rating",
            "proficiency",
        )
        for field in dataclasses.fields(PerformanceObservationV1):
            for term in banned:
                assert term not in field.name.lower(), f"{field.name} contains {term!r}"


class TestNoRuntimeVocabularyCrossesThePort:
    def test_port_source_names_no_runtime(self) -> None:
        source = inspect.getsource(port_mod).lower()
        for term in RUNTIME_SPECIFIC_TERMS:
            # Mentioning a runtime in prose is fine; a symbol is not.
            for line in source.splitlines():
                stripped = line.strip()
                if stripped.startswith(("def ", "class ", "from ", "import ")):
                    assert term not in stripped, f"port declares {term!r}: {line}"

    @pytest.mark.parametrize("module", NEUTRAL_MODULES, ids=lambda m: m.__name__.split(".")[-1])
    def test_neutral_modules_declare_no_runtime_specific_symbol(self, module: Any) -> None:
        for name in dir(module):
            if name.startswith("_"):
                continue
            lowered = name.lower()
            assert "ardour" not in lowered, f"{module.__name__}.{name}"

    @pytest.mark.parametrize("module", NEUTRAL_MODULES, ids=lambda m: m.__name__.split(".")[-1])
    def test_no_contract_field_names_a_runtime(self, module: Any) -> None:
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and dataclasses.is_dataclass(obj):
                for field in dataclasses.fields(obj):
                    assert "ardour" not in field.name.lower(), f"{name}.{field.name}"

    def test_contract_modules_do_not_import_an_adapter(self) -> None:
        contract_dir = PERFORMANCE_ROOT / "contracts"
        for path in list(contract_dir.glob("*.py")) + [PERFORMANCE_ROOT / "ports" / "runtime.py"]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "adapters" not in node.module, f"{path.name} imports {node.module}"

    def test_ardour_vocabulary_is_confined_to_its_adapter(self) -> None:
        ardour_dir = ADAPTER_ROOT / "ardour"
        for path in PERFORMANCE_ROOT.rglob("*.py"):
            if ardour_dir in path.parents:
                continue
            source = path.read_text(encoding="utf-8")
            for line in source.splitlines():
                stripped = line.strip()
                if stripped.startswith(("class ", "def ")):
                    assert "ardour" not in stripped.lower(), f"{path.name}: {line}"

    def test_the_ardour_adapter_exports_nothing_publicly(self) -> None:
        from master_all_strings.performance.adapters import ardour

        assert ardour.__all__ == []


class TestAdaptersDoNotMutateCanonicalState:
    def test_no_adapter_imports_musical_core_mutation_paths(self) -> None:
        for path in ADAPTER_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "core.musical_events" not in node.module, path.name
                    assert "core.spatial_mapping" not in node.module, path.name

    def test_performance_never_mints_a_revision_identifier(self) -> None:
        from master_all_strings.performance import ingestion

        source = inspect.getsource(ingestion)
        assert "canonical_revision_id=None" in source
        # There must be no function here capable of producing a revision.
        for name in dir(ingestion):
            assert "revision" not in name.lower() or name.startswith("_"), name


class TestPackageDeclaresItsEngine:
    def test_performance_package_declares_its_owning_engine(self) -> None:
        import master_all_strings.performance as performance

        assert "Performance Engine" in (performance.__doc__ or "")

    def test_system_model_lists_the_performance_package(self) -> None:
        path: Path = REPO_ROOT / "docs" / "architecture" / "FOUR_ENGINE_SYSTEM_MODEL.md"
        text = path.read_text(encoding="utf-8")
        assert "`performance/`" in text
