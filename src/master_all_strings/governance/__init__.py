"""Governance for the four-engine architecture (owning engine: cross-engine).

This package enforces the constitutional boundaries ratified in ADR-0006. Its
source of truth is ``governance/engine_architecture_v1.json`` at the repository
root; the Markdown documents under ``docs/architecture/`` are generated views of
that file and are checked against it here.
"""

from __future__ import annotations

__all__ = ["engine_boundaries"]
