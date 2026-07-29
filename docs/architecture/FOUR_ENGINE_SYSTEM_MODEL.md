# Four-Engine System Model

This document is the operational companion to [ADR-0006](../decisions/ADR-0006-FOUR-ENGINE-ARCHITECTURE.md). The ADR ratifies the decision; this explains how to work within it — how the engines fit together, where the seam contracts sit, and how a Dev Order declares which engine it belongs to.

An **engine** is a constitutional boundary: an ownership scope, a dependency direction, a roadmap, and a Dev Order namespace. It is **not** (yet) a top-level Python package. See ADR-0006 for why, and for the five conditions under which that changes.

> **Machine-readable source of truth.** The engine set, dependency rules, capability ownership, contract ownership, seams, and ADR assignments are held in `governance/engine_architecture_v1.json` (schema: `schemas/engine_architecture_v1.schema.json`). The generated views — [ENGINE_OWNERSHIP_REGISTRY.md](ENGINE_OWNERSHIP_REGISTRY.md), [ENGINE_DEPENDENCY_MATRIX.md](ENGINE_DEPENDENCY_MATRIX.md), [ENGINE_CONTRACT_OWNERSHIP.md](ENGINE_CONTRACT_OWNERSHIP.md) — are rendered from it and verified against it by `tests/governance/`. A view that disagrees with the JSON, or a JSON change not reflected in the views, fails the suite. The prose in *this* document is the human explanation; the JSON is the authority the validator enforces.

## The four engines at a glance

| Engine | Answers | Owns, in one line |
| --- | --- | --- |
| **Musical Core** | *What is the music, and where can it be played?* | Canonical music, MSME, selection, mechanical planning, spatial evidence, deterministic projection. |
| **Educational Engine** | *What does this mean for a learner?* | Learning Objects, curriculum, interpretation, coaching, assessment, pedagogical sequencing. |
| **Creative Engine** | *How does a human change the music?* | Smart Score Entry, composition, arrangement, AI proposals, authoring UX. |
| **Performance Engine** | *What actually happened when it was played?* | Live capture, playback, Smart Guitar, telemetry, device adapters. |

## Dependency direction

```text
                 Creative Engine
                    |       |
                    v       v
Educational Engine ---> Musical Core
        ^                 ^
        |                 |
        +--- Performance --+
             Engine
```

Read the arrows as "depends on / consumes contracts from." The single rule that makes the system tractable:

> **Musical Core depends on nothing.** Everything else depends on Core; Core answers to no one.

The rest follows:

- **Educational** → Musical Core. May also consume **Performance** evidence (what a student actually played).
- **Creative** → Musical Core. May *request* Educational constraints (e.g. "keep this beginner-appropriate") but does not depend on Educational internals.
- **Performance** → Musical Core. Emits evidence upward; embeds no curriculum or coaching policy.
- No engine mutates another engine's authoritative records directly. Cross-engine influence happens through contracts, not reach-in.

If a proposed Dev Order needs Musical Core to import from any other engine, the Dev Order is malformed. Re-scope it.

### Allowed-dependency matrix

The diagram is prose-adjacent; this table is the exact rule. "Depends on" means compile/import-time dependency on the other engine's contracts. Read a row as "may X depend on the column engine?"

| Depends on ↓ / Engine → | Musical Core | Educational | Creative | Performance |
| --- | --- | --- | --- | --- |
| **Musical Core** | — | no | no | no |
| **Educational** | yes | — | no | consumes evidence only |
| **Creative** | yes | consumes contracts only | — | no |
| **Performance** | yes | no | no | — |

Two rows need their qualifier read precisely, because the review flagged them as ambiguous:

- **Educational → Performance is "consumes evidence only".** Educational may read Performance-emitted evidence contracts (what a student actually played). It may **not** import Performance device implementations or depend on Performance internals. Data flows up; code does not depend down into the device layer.
- **Creative → Educational is "consumes contracts only".** When Creative "requests Educational constraints" (e.g. "keep this beginner-appropriate"), that is a contract Creative passes and Educational fulfils — **not** a compile-time dependency on Educational internals. Creative depends only on Musical Core at import time.

Every other off-diagonal cell that is not "yes" is a hard "no": Creative must not depend on Performance device code, Performance must not embed Educational or Creative policy, and nothing depends on Musical Core in reverse. No engine mutates another engine's authoritative records; cross-engine influence is by contract, never reach-in.

## The three seams

A seam is where one human-visible capability spans two engines. Getting these right is the whole point of the taxonomy; getting them wrong reintroduces the catch-all. Each seam is a **contract boundary**, not a handoff of vague responsibility.

### Seam 1 — Authoring | Projection

```text
Creative: change the music        Musical Core: project the music faithfully
--------------------------        ----------------------------------------
intent entry, Smart Entry         canonical representation
composition, arrangement          deterministic projection contracts
transformation *requests*         semantic -> representation conversion
semantic edit proposals           notation / TAB / MIDI projection results
score-authoring UX                source-revision binding
"vibe the score"                  renderer-independent projection semantics
```

A renderer lives behind a Core-owned projection interface (adapter packages are fine). It may choose spacing, stems, beams, system breaks, and collision resolution. It may **not** decide the music, simplify a phrase, pick a teaching strategy, or reinterpret intent. **Creative changes the music; Core projects the result.**

### Seam 2 — Spatial evidence | Educational interpretation

The strongest seam. Two contracts, never one.

```text
Musical Core: SpatialEvidenceV1          Educational: EducationalInterpretationV1
-----------------------------            ---------------------------------------
what occurred spatially                  what it means for a learner
- candidate / selected positions         - estimated difficulty
- string usage, fret/position ranges     - beginner suitability
- shifts, repeated positions             - lesson concepts, technique labels
- open-string use, string crossings      - fingering recommendations
- alternate playable mappings            - simplification opportunities
- instrument + tuning profile            - curriculum compatibility
- source event/phrase references         - coaching observations
- algorithm identity + version           - assessment criteria
- unsupported / ambiguous cases          (each cites SpatialEvidenceV1 records)
```

**Litmus test for the Core side:** if a field uses *easy*, *hard*, *beginner*, *advanced*, *recommended*, or *poor*, it is in the wrong contract. Core reports *three shifts*, *max fret 12*, *four-string span*, *two alternate mappings*. Education decides whether that is hard for this learner.

Educational interpretation **cites** evidence and never overwrites it. Evidence is a fact of the instrument; interpretation is an opinion about a learner, and opinions carry their sources.

### Seam 3 — Mechanical planning | Pedagogical sequencing

```text
Musical Core: mechanical phrase planner   Educational: pedagogical sequencing
---------------------------------------   ----------------------------------
"what valid paths exist, under            "which valid plan best serves this
 explicit non-pedagogical constraints?"    learner / lesson / objective?"
- continuity across events                - one new technique at a time
- candidate-path generation               - a harder fingering for teaching value
- deterministic path selection under      - reinforcing curriculum
  declared non-pedagogical policies       - sequencing, cognitive load
- bounded shifts *when asked*             - preserve vs remove shifts
- reach / string / fret constraints       - level adaptation, mastery progression
- ambiguity preservation                  - assessment-driven variation
- admit/reject explanations               - teacher-selected policy
```

Core accepts explicit objective functions — `minimize position movement`, `stay below fret 7`, `avoid open strings` — as **mechanical** constraints. It must never decide one objective is *educationally* superior. Education supplies the objective and picks among the valid plans Core returns.

Flow:

```text
Educational objective
  -> explicit planning constraints / preferences
  -> Musical Core phrase planner
  -> valid, evidence-bearing phrase plans
  -> Educational selection + explanation
```

### Seam 4 — Performance evidence | Coaching

The same evidence-versus-interpretation split as Seam 2, on the other side of the system: Performance records what was played; Education decides what it means for the learner. Performance embeds no coaching policy, and Education does not rewrite the observed record.

```text
Performance Engine
    PerformanceObservationV1        (what was played: timing, notes, errors — facts)
              |
              v
Educational Engine
    learner / session interpretation
              |
              v
    CoachingRecommendationV1        (what to do about it — cites the observation)
```

This is the one cross-engine path where Educational depends *downward on Performance* — as an evidence consumer only. Educational imports Performance's observation contract; it does not depend on Performance device code, and Performance never depends up into curriculum or coaching. `CoachingRecommendationV1` cites `PerformanceObservationV1`, exactly as `EducationalInterpretationV1` cites `SpatialEvidenceV1`.

## Borderline cases

The seam language is clear in principle but disputable at the margin. These are the recurring hard calls, decided once here so they are not relitigated per Dev Order. The test in each case is the same: **does the operation require a judgment about a human (a learner, an author's intent), or only a deterministic fact about the music?**

| Borderline capability | Engine | Why |
| --- | --- | --- |
| A deterministic transformation (transpose, capo-shift, enharmonic respell, quantize to a grid) | Musical Core | Fully determined by the input music; no intent or pedagogy. A function of the notes, not of a person. |
| A "semantic edit proposal" (make this jazzier, simplify for a beginner, re-voice) | Creative | Encodes an author's *intent*; the result is one of many valid outputs chosen to match a goal. |
| Engraving choices (spacing, stems, beams, system breaks, collision resolution) | Musical Core (projection) | Deterministic rendering of fixed music; changes appearance, not content. |
| Choosing *which* notation to show a student, or hiding complexity | Educational | A pedagogical decision about a learner, layered on top of a faithful projection. |
| A mechanical constraint (`stay below fret 7`, `minimize shifts`) supplied explicitly | Musical Core | An objective function over playability; Core optimizes it without judging it. |
| Deciding that fret-7 or fewer shifts is *better for this learner* | Educational | A judgment about pedagogy, not mechanics. Education supplies the objective; Core executes it. |
| Difficulty, "beginner-appropriate", "good fingering" | Educational | Any claim using a pedagogical adjective is interpretation, never Core evidence (Seam 2 litmus test). |

When a genuinely new borderline appears, apply the litmus test above and record the ruling by extending this table, not by re-deciding in a Dev Order.

## Contract naming and location

This is a governance document; it names contracts (`SpatialEvidenceV1`, `EducationalInterpretationV1`) and their owning engine, but deliberately does **not** fix their module paths, class names, or versioning mechanics. Those are decided by the implementing Dev Order for the owning engine, so that the physical home follows the code that builds it. What is fixed here is *which engine owns each contract* and *which engine may cite it* — the constitutional facts, not the file layout.

## How a Dev Order declares its engine

Every Dev Order names its engine and respects the dependency direction. Concretely:

1. **State the engine** in the Dev Order's architectural-context section (e.g. "Engine: Musical Core").
2. **List cross-engine contracts consumed**, and confirm each dependency points down the arrows above. A Musical Core Dev Order consumes nothing from another engine.
3. **Own contracts under the right authority.** A new evidence/interpretation contract goes to Core or Educational per Seam 2; a projection contract is Core; an authoring command is Creative.
4. **Declare the owning engine on any new package** — a one-line note in the package `__init__` docstring, and add a row to the package-to-engine table below in the same change.

**Authority precedence.** For a package that exists in the table, the table is authoritative. For a newly added package whose table row has not yet landed, its `__init__` docstring declaration is authoritative in the interim; the same Dev Order must add the table row, so the two never disagree for longer than one change. If a docstring and the table ever conflict for an existing package, that is a defect to fix, not a choice to make.

A reviewer can then check a single question: *does this Dev Order's dependency direction respect the arrows?* If not, it is re-scoped before implementation, not after.

## Package-to-engine mapping (current)

Packages are physically arranged by current repository convention; the engine column is governance, not directory structure.

| Package (today) | Engine | Notes |
| --- | --- | --- |
| `core/` (foundation, musical_events, spatial_mapping) | Musical Core | Canonical model + MSME. |
| `instruments/` | Musical Core | Instrument and tuning profiles. |
| `adapters/` | boundary (Core today) | Hosts boundary adapters behind the interface of whichever engine owns it. Today that is Musical Core (projection/renderer, I/O); a future Performance device adapter would live here under Performance ownership, with its own table row. |
| `practice/` (placeholder) | Educational | Foreshadows the Educational Engine. |
| `sequencer/` (placeholder) | Performance | Transport/playback foreshadows the Performance Engine. |

This table lists every top-level package present today; there is no current package it omits. `core/` groups the `foundation`, `musical_events`, and `spatial_mapping` subpackages — `spatial_mapping` is *inside* `core/`, not a sibling. No package moves as a result of ADR-0006. For the packages listed, this table is authoritative on engine ownership until a future, separately-authorized reorganization changes the physical layout; for a package not yet listed, see the authority-precedence rule above.

## Relationship to existing documents

- [ADR-0001](../decisions/ADR-0001-REPOSITORY-OWNERSHIP.md) — repository ownership; unchanged. This repository still owns the musical core and the layers above it, and still is not luthiers-toolbox or CNC-Production-Shop.
- [ADR-0003](../decisions/ADR-0003-MUSIC-CANONICAL.md) — music is canonical; the four engines sit *around* that principle, they do not weaken it. Musical Core is where "canonical" lives.
- [ADR-0004](../decisions/ADR-0004-CANDIDATE-GENERATION.md) — candidate generation; Musical Core.
- [SYSTEM_BOUNDARIES.md](SYSTEM_BOUNDARIES.md) — the earlier per-subsystem boundary sketch; the four engines are the coarser constitutional grouping above those subsystems.
- The captured planning handoff is retained as preservation and queue authority by the ratifying decision (ADR-0006), which directs that it later split into a Learning-Object/curriculum foundation (Educational) and a separate Creative Engine handoff rather than be rewritten now. Its validity is a consequence of that decision, not an independent claim of this file.

DO-004 (deterministic selection) is Musical Core and proceeds unaffected; ADR-0005 is reserved for it.

## Enforcement posture

Per ADR-0006, engine boundaries are governance, not import-enforced, in this tranche — deliberately, to avoid churning healthy code. That means the dependency direction is enforced by review against this document, not yet by tooling. A mechanical check (an import-linter contract mirroring the allowed-dependency matrix, or CI on the per-package declarations) is a candidate follow-up once a second engine ships production code; it is out of scope here and named so it is not mistaken for already-present enforcement.
