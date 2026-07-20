# ADR-0002: Core Dataclasses

## Status
Accepted

## Decision
Core computational models use frozen standard-library dataclasses. Framework-specific validation belongs at application boundaries.

## Consequences

The core engine remains portable, dependency-light, and explicit about invariants without taking a runtime dependency on framework validation systems.
