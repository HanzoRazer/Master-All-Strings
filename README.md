# Master All Strings

Master All Strings is the modern product home for reconstructing, modernizing, and expanding the musical sequencing and String Master concepts developed in the original Master Producer.

> Master All Strings is not software for drawing instruments or estimating CNC jobs. It is a musical-performance and learning platform that translates musical information into playable, instrument-specific guidance.

> Music is canonical. Instrument representation is an adapter.

## Current scope

This repository implements the foundation contracts and the first executable capability of the **Musical Spatial Mapping Engine (MSME)**:

- repository structure and architecture documents;
- immutable core contracts for musical events, instruments, and spatial positions;
- validation helpers;
- pitch-formatting utilities;
- equal-temperament geometry utilities;
- MSME candidate generation.

### Implementation status

| Capability | Status |
| --- | --- |
| Candidate generation | implemented |
| Deterministic selection | deferred |
| Pedagogical interpretation | deferred |
| Phrase and chord planning | deferred |

`generate_candidates(event, instrument, constraints)` returns every valid playable position for a canonical musical event on a configured instrument, preserving ambiguity. Its ordering is stable enumeration and **not** a ranking — index zero is not a recommendation. See [ADR-0004](docs/decisions/ADR-0004-CANDIDATE-GENERATION.md) for the settled decisions.

## What this repository is not

This repository is not:

- a luthier CAD/CAM application;
- a CNC estimating or manufacturing-planning tool;
- a generic fretboard calculator;
- a continuation of the frozen Visual C++ 6 / MFC archive;
- a place to copy unrelated code from neighboring repositories.

## Repository layout

```text
Master-All-Strings/
├── pyproject.toml
├── src/master_all_strings/
├── resources/instruments/
├── tests/
└── docs/
```

## Architecture

The platform is organized into four cooperating engines — **Musical Core**, **Educational**, **Creative**, and **Performance** — each a constitutional ownership and dependency boundary. Only Musical Core has shipped code so far; the others are governance boundaries with planned capabilities. See [ADR-0006](docs/decisions/ADR-0006-FOUR-ENGINE-ARCHITECTURE.md) and the [four-engine system model](docs/architecture/FOUR_ENGINE_SYSTEM_MODEL.md). Ownership is held in a machine-readable registry (`governance/engine_architecture_v1.json`) and enforced by `tests/governance/`.

See `docs/architecture/PRODUCT_CHARTER.md` for the product charter and `docs/architecture/MUSICAL_SPATIAL_MAPPING_ENGINE.md` for subsystem details.

## Repository verification

Every pull request and every push to `main` runs the engineering gates in GitHub
Actions (`.github/workflows/verify.yml`): Ruff lint, mypy in strict mode (configured
in `[tool.mypy]`, so the command is just `mypy`), and the pytest suite with a
repository-wide coverage floor of 95%. Reproduce the same checks locally:

```bash
pip install -e ".[dev]"

ruff check src tests
mypy
pytest --cov --cov-report=term-missing
```

See [docs/development/CONTINUOUS_VERIFICATION.md](docs/development/CONTINUOUS_VERIFICATION.md) for the full policy.
