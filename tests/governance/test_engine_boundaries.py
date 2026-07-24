"""Tests for the engine-boundary validator.

The committed registry must be clean; deliberately corrupted copies must each raise
the specific violation they model, so a real future regression cannot pass.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from master_all_strings.governance import engine_boundaries as eb


@pytest.fixture
def registry() -> dict[str, Any]:
    return eb.load_registry()


def _codes(reg: dict[str, Any]) -> set[str]:
    return {v.code for v in eb.validate_registry(reg)}


class TestCommittedRegistryIsClean:
    def test_committed_registry_has_no_violations(self, registry: dict[str, Any]) -> None:
        assert eb.validate_registry(registry) == []

    def test_cli_reports_ok(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert eb.main([]) == 0
        assert "OK" in capsys.readouterr().out


class TestEngineInvariants:
    def test_missing_engine_fails(self, registry: dict[str, Any]) -> None:
        registry["engines"] = registry["engines"][:3]
        assert "ENGINES" in _codes(registry)

    def test_wrong_engine_id_fails(self, registry: dict[str, Any]) -> None:
        registry["engines"][1]["id"] = "PEDAGOGY_ENGINE"
        assert "ENGINES" in _codes(registry)

    def test_core_not_marked_independent_fails(self, registry: dict[str, Any]) -> None:
        for e in registry["engines"]:
            if e["id"] == "MUSICAL_CORE":
                e["depends_on_none"] = False
        assert "CORE_INDEPENDENT" in _codes(registry)

    def test_two_independent_engines_fails(self, registry: dict[str, Any]) -> None:
        for e in registry["engines"]:
            if e["id"] == "EDUCATIONAL_ENGINE":
                e["depends_on_none"] = True
        assert "CORE_INDEPENDENT" in _codes(registry)


class TestDependencyDirection:
    def test_core_depending_on_educational_fails(self, registry: dict[str, Any]) -> None:
        for r in registry["dependency_rules"]:
            if r["from"] == "MUSICAL_CORE" and r["to"] == "EDUCATIONAL_ENGINE":
                r["relation"] = "depends"
        assert "CORE_DEPENDS" in _codes(registry)

    def test_incomplete_matrix_fails(self, registry: dict[str, Any]) -> None:
        registry["dependency_rules"] = registry["dependency_rules"][:-1]
        assert "MATRIX" in _codes(registry)

    def test_duplicate_rule_fails(self, registry: dict[str, Any]) -> None:
        registry["dependency_rules"].append(copy.deepcopy(registry["dependency_rules"][0]))
        assert "MATRIX" in _codes(registry)


class TestCapabilityOwnership:
    def test_duplicate_capability_id_fails(self, registry: dict[str, Any]) -> None:
        registry["capabilities"].append(copy.deepcopy(registry["capabilities"][0]))
        assert "CAP_DUP" in _codes(registry)

    def test_consumer_that_cannot_depend_on_owner_fails(self, registry: dict[str, Any]) -> None:
        # curriculum is Educational-owned; Performance cannot depend on Educational.
        for cap in registry["capabilities"]:
            if cap["id"] == "curriculum":
                cap["permitted_consumers"] = ["PERFORMANCE_ENGINE"]
        assert "CAP_DEP" in _codes(registry)

    def test_owner_listed_as_own_consumer_fails(self, registry: dict[str, Any]) -> None:
        for cap in registry["capabilities"]:
            if cap["id"] == "curriculum":
                cap["permitted_consumers"] = ["EDUCATIONAL_ENGINE"]
        assert "CAP_SELF" in _codes(registry)


class TestClassificationAndSeams:
    def test_interpretation_owned_by_core_fails(self, registry: dict[str, Any]) -> None:
        for cap in registry["capabilities"]:
            if cap["id"] == "candidate-generation":
                cap["classification"] = "interpretation"
        assert "CLASS" in _codes(registry)

    def test_evidence_owned_by_creative_fails(self, registry: dict[str, Any]) -> None:
        for cap in registry["capabilities"]:
            if cap["id"] == "composition":
                cap["classification"] = "evidence"
        assert "CLASS" in _codes(registry)

    def test_performance_owning_interpretation_fails(self, registry: dict[str, Any]) -> None:
        for cap in registry["capabilities"]:
            if cap["id"] == "telemetry":
                cap["classification"] = "interpretation"
        # PERF_POLICY (performance may not own interpretation) fires; CLASS also fires.
        assert "PERF_POLICY" in _codes(registry)

    def test_spatial_evidence_reassigned_off_core_fails(self, registry: dict[str, Any]) -> None:
        for con in registry["contracts"]:
            if con["name"] == "SpatialEvidenceV1":
                con["owning_engine"] = "EDUCATIONAL_ENGINE"
                con["versioning_authority"] = "EDUCATIONAL_ENGINE"
                con["classification"] = "interpretation"
        assert "SEAM" in _codes(registry)

    def test_missing_required_seam_contract_fails(self, registry: dict[str, Any]) -> None:
        registry["contracts"] = [
            c for c in registry["contracts"] if c["name"] != "CoachingRecommendationV1"
        ]
        assert "SEAM" in _codes(registry)


class TestContractInvariants:
    def test_versioning_authority_not_owner_fails(self, registry: dict[str, Any]) -> None:
        for con in registry["contracts"]:
            if con["name"] == "LearningObject":
                con["versioning_authority"] = "MUSICAL_CORE"
        assert "CON_VERSION" in _codes(registry)

    def test_contract_consumer_wrong_direction_fails(self, registry: dict[str, Any]) -> None:
        # EducationalInterpretationV1 is Educational-owned; Performance cannot consume it.
        for con in registry["contracts"]:
            if con["name"] == "EducationalInterpretationV1":
                con["consumers"] = ["PERFORMANCE_ENGINE"]
        assert "CON_DEP" in _codes(registry)

    def test_interpretation_must_cite_evidence(self, registry: dict[str, Any]) -> None:
        for con in registry["contracts"]:
            if con["name"] == "EducationalInterpretationV1":
                con["cites"] = "LearningObject"  # not an evidence contract
        assert "CON_CITE" in _codes(registry)

    def test_owner_consuming_own_contract_is_allowed(self, registry: dict[str, Any]) -> None:
        # ProjectionRequest is Core-owned and Core-consumed; this must NOT be flagged.
        names = {v.detail for v in eb.validate_registry(registry) if v.code == "CON_DEP"}
        assert not any("ProjectionRequest" in d for d in names)


class TestAdrAssignments:
    def test_adr_0005_reassigned_fails(self, registry: dict[str, Any]) -> None:
        for a in registry["adr_assignments"]:
            if a["adr"] == "ADR-0005":
                a["status"] = "accepted"
                a["owner"] = "DO-005"
        assert "ADR_0005" in _codes(registry)

    def test_adr_number_reuse_fails(self, registry: dict[str, Any]) -> None:
        registry["adr_assignments"].append(
            {"adr": "ADR-0006", "title": "dup", "status": "accepted"}
        )
        assert "ADR_DUP" in _codes(registry)

    def test_adr_0006_not_accepted_fails(self, registry: dict[str, Any]) -> None:
        for a in registry["adr_assignments"]:
            if a["adr"] == "ADR-0006":
                a["status"] = "proposed"
        assert "ADR_0006" in _codes(registry)


class TestRemainingBranches:
    """Direct coverage for the defensive and CLI branches."""

    def test_duplicate_engine_id(self, registry: dict[str, Any]) -> None:
        registry["engines"].append(copy.deepcopy(registry["engines"][0]))
        assert "ENGINES" in _codes(registry)

    def test_duplicate_contract_name(self, registry: dict[str, Any]) -> None:
        registry["contracts"].append(copy.deepcopy(registry["contracts"][0]))
        assert "CON_DUP" in _codes(registry)

    def test_cite_unknown_contract(self, registry: dict[str, Any]) -> None:
        for con in registry["contracts"]:
            if con["name"] == "EducationalInterpretationV1":
                con["cites"] = "NoSuchContract"
        assert "CON_CITE" in _codes(registry)

    def test_non_interpretation_that_cites_is_flagged(self, registry: dict[str, Any]) -> None:
        for con in registry["contracts"]:
            if con["name"] == "SelectedSpatialPath":  # classification 'evidence'
                con["cites"] = "SpatialEvidenceV1"
        assert "CON_CITE" in _codes(registry)

    def test_relation_returns_none_for_self_pair(self, registry: dict[str, Any]) -> None:
        assert eb._relation(registry, "MUSICAL_CORE", "MUSICAL_CORE") is None

    def test_violation_str_is_readable(self) -> None:
        assert str(eb.Violation("CODE", "detail")) == "[CODE] detail"

    def test_format_with_violations(self) -> None:
        out = eb._format([eb.Violation("A", "x")])
        assert "violations" in out and "[A] x" in out

    def test_cli_write_views_returns_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        # Idempotent: rewrites the already-generated views with identical content.
        assert eb.main(["--write-views"]) == 0
        assert "wrote" in capsys.readouterr().out

    def test_cli_nonzero_on_violation(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        broken = eb.load_registry()
        broken["engines"] = broken["engines"][:3]
        (tmp_path / "reg.json").write_text(__import__("json").dumps(broken), encoding="utf-8")
        monkeypatch.setattr(eb, "REGISTRY_PATH", tmp_path / "reg.json")
        assert eb.main([]) == 1
        assert "violations" in capsys.readouterr().out
