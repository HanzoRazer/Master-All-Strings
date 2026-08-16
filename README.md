# Master All Strings

Master All Strings is an offline musical-performance and learning platform. Music
is canonical; instrument representation is an adapter.

> Master All Strings is not software for drawing instruments or estimating CNC jobs.

## Master All Strings MVP 1

Commercial milestone **MVP 1** is complete as software. It closes the offline
practice loop:

```text
Lesson → See / Hear → Practice → Perform → Evaluate → Feedback → Next Action → Continue
```

Current MVP 1 capability includes:

- Musical Core contracts and MSME candidate generation;
- lesson assignment / projection for bundled demos;
- fretboard visualization with Zone Harmony overlay and one-string teaching aids;
- shared practice transport (Play / Pause / Seek / rates / loop);
- offline Reference Synth;
- live or fake Web MIDI performance capture and deterministic alignment;
- Educational Practice*V1 evaluation, feedback, and next-action selection.

Historical engineering names (MVP-1F, MVP-2A, DO-008, DO-009, DO-010) remain valid
history. They do **not** mean commercial MVP 2 has shipped.

### Launch (localhost)

```bash
pip install -e ".[dev]"
PYTHONPATH=src python3 scripts/run_mvp1.py --lesson ascending_scale --open
```

Headless export only:

```bash
PYTHONPATH=src python3 scripts/run_mvp1.py --lesson ascending_scale
```

### Hardware verification status

| Channel | Status |
| --- | --- |
| Physical MIDI input | `UNVERIFIED_PHYSICAL_MIDI_INPUT` |
| Audio output | `UNVERIFIED_AUDIO_OUTPUT` |

Software MVP 1 publication does not certify physical hardware.

### MVP 1 documents

- [Product spec](docs/mvp/MASTER_ALL_STRINGS_MVP_PRODUCT_SPEC.md)
- [Release report](docs/mvp/MASTER_ALL_STRINGS_MVP_RELEASE_REPORT.md)
- [Release baseline (SHAs)](docs/mvp/MVP1_RELEASE_BASELINE.md)
- [Publication report](docs/mvp/MVP1_PUBLICATION_REPORT.md)

## Architecture

The platform is organized into four cooperating engines — **Musical Core**,
**Educational**, **Creative**, and **Performance** — each a constitutional
ownership and dependency boundary. See [ADR-0006](docs/decisions/ADR-0006-FOUR-ENGINE-ARCHITECTURE.md)
and the [four-engine system model](docs/architecture/FOUR_ENGINE_SYSTEM_MODEL.md).
Ownership is held in `governance/engine_architecture_v1.json` and enforced by
`tests/governance/`.

Performance measures. Education interprets. Creative authoring remains largely
planned. Musical Core remains the dependency-free foundation.

## What this repository is not

- a luthier CAD/CAM application;
- a CNC estimating or manufacturing-planning tool;
- a generic fretboard calculator;
- a continuation of the frozen Visual C++ 6 / MFC archive;
- commercial MVP 2 (advanced sequencer, synchronized media, video, avatar).

## Repository layout

```text
Master-All-Strings/
├── pyproject.toml
├── src/master_all_strings/
├── resources/
├── web/mvp1/
├── tests/
└── docs/
```

## Repository verification

Every pull request and every push to `main` runs the engineering gates in GitHub
Actions (`.github/workflows/verify.yml`): Ruff lint, mypy in strict mode, and the
pytest suite with a repository-wide coverage floor of 95%. Reproduce locally:

```bash
pip install -e ".[dev]"

ruff check src tests
mypy
pytest --cov --cov-report=term-missing
```

Browser unit tests:

```bash
cd web/mvp1 && npm test
```

See [docs/development/CONTINUOUS_VERIFICATION.md](docs/development/CONTINUOUS_VERIFICATION.md).
