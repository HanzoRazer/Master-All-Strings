# Performance Engine package

Navigation for the Embedded Performance Runtime
([ADR-0007](../../../docs/decisions/ADR-0007-EMBEDDED-PERFORMANCE-RUNTIME.md)).
Read this before the modules; it is a map, not a spec.

## The one rule

```text
             contracts/  +  ports/          <- runtime-neutral. No Ardour. Ever.
                    |
        ------------+------------
        |                       |
   adapters/fake_runtime   adapters/ardour/  <- implementation-specific vocabulary
   (ships, tested)         (scaffold, raises)   lives here and nowhere else
```

`tests/performance/test_performance_boundaries.py` parses this package with `ast` and
fails the build if that rule is broken.

## Where things live

| Path | What it is | State |
| --- | --- | --- |
| `contracts/runtime.py` | Identity, capabilities, config, health, readiness, faults | stable |
| `contracts/session.py` | Session, track, transport, loop, metronome | stable |
| `contracts/capture.py` | Captured events, raw capture, observation — **the evidence model** | stable |
| `contracts/commands.py` | Every operation a caller may request | stable |
| `contracts/results.py` | What a runtime returns | stable |
| `contracts/ingestion.py` | The Musical Core handoff | stable |
| `contracts/errors.py` | `PerformanceContractError` + shared validators | stable |
| `ports/runtime.py` | `PerformanceRuntimePort` — **the boundary** | stable |
| `adapters/fake_runtime.py` | Deterministic in-memory runtime | ships |
| `adapters/clock.py` | Deterministic timestamps | ships |
| `adapters/ardour/` | Ardour adapter | **scaffold; raises** |
| `configuration.py` | Config + synth registry loading, cross-file validation | ships |
| `session_builder.py` | Builders for the one-track first target | ships |
| `capture_normalization.py` | Event normalization, capture open/append/close | ships |
| `observations.py` | Factual observations from a capture | ships |
| `runtime_diagnostics.py` | Readiness aggregation, diagnostic rendering | ships |
| `export.py` | Deterministic serialization + digest | ships |
| `ingestion.py` | Builds the ingestion request | ships |
| `cli.py` | Read-only validate / inspect commands | ships |

## Reading order for a newcomer

1. `ports/runtime.py` — the whole interface, in one file.
2. `contracts/capture.py` — the evidence model everything else cites.
3. `adapters/fake_runtime.py` — the interface actually driven end to end.
4. `contracts/ingestion.py` — where Performance stops and Musical Core begins.

## Invariants enforced in code, not prose

- Raw capture is immutable once closed; closure is explicit and one-way.
- Sequence numbers strictly increase; timestamps never decrease.
- `source_string` is observed or `None`. Never inferred.
- One MIDI track. Audio tracks are rejected outright.
- Performance may reference a canonical revision id; it may never mint one.
- Observations carry counts, bounds, and states — never a judgment about a player.
- Readiness is two questions: `ready` (accepts commands) and `capture_ready`
  (a session exists). See Diagram 7 in the architecture doc.

## Duplicated authorities, and what keeps them honest

The same rules appear in Python contracts, JSON Schema, fixtures, and the governance
registry. That duplication is deliberate and each pair has a test:

| Pair | Test |
| --- | --- |
| contract ↔ schema — event, capture, health, config | `test_schemas.py::TestEnumsMatchBetweenPythonAndSchema`, `::TestRequiredFieldsAndBoundsMatch` |
| contract ↔ schema — session, track, transport, meter, loop, metronome, synth entry, capability registry | `test_schemas.py::TestSessionAndRegistrySchemasMatchTheirContracts` |
| schema ↔ fixtures (valid and invalid, by named validator) | `test_schemas.py::TestValidFixturesPass`, `::TestInvalidFixturesFailForANamedReason` |
| contract ↔ serialized form (lossless round-trip) | `test_schemas.py::TestRoundTrip` |
| embedded ↔ standalone event schema | `test_schemas.py::TestEmbeddedEventDefinitionDoesNotDrift` |
| registry ↔ generated views | `tests/governance/test_engine_markdown_views.py` |
| registry ↔ code ownership | `test_performance_boundaries.py` |

A schema added without a matching drift test is itself asserted against, in
`TestSessionAndRegistrySchemasMatchTheirContracts::test_every_schema_with_a_contract_is_covered_by_a_drift_test`.
