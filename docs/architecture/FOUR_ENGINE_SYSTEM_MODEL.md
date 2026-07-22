# Four-Engine System Model

This document is the operational companion to [ADR-0006](../decisions/ADR-0006-FOUR-ENGINE-ARCHITECTURE.md). The ADR ratifies the decision; this explains how to work within it — how the engines fit together, where the seam contracts sit, and how a Dev Order declares which engine it belongs to.

An **engine** is a constitutional boundary: an ownership scope, a dependency direction, a roadmap, and a Dev Order namespace. It is **not** (yet) a top-level Python package. See ADR-0006 for why, and for the five conditions under which that changes.

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

## How a Dev Order declares its engine

Every Dev Order names its engine and respects the dependency direction. Concretely:

1. **State the engine** in the Dev Order's architectural-context section (e.g. "Engine: Musical Core").
2. **List cross-engine contracts consumed**, and confirm each dependency points down the arrows above. A Musical Core Dev Order consumes nothing from another engine.
3. **Own contracts under the right authority.** A new evidence/interpretation contract goes to Core or Educational per Seam 2; a projection contract is Core; an authoring command is Creative.
4. **Declare the owning engine on any new package** — a one-line note in the package `__init__` docstring.

A reviewer can then check a single question: *does this Dev Order's dependency direction respect the arrows?* If not, it is re-scoped before implementation, not after.

## Package-to-engine mapping (current)

Packages are physically arranged by current repository convention; the engine column is governance, not directory structure.

| Package (today) | Engine | Notes |
| --- | --- | --- |
| `core/` (foundation, musical_events, spatial_mapping) | Musical Core | Canonical model + MSME. |
| `instruments/` | Musical Core | Instrument and tuning profiles. |
| `adapters/` | Musical Core (boundary) | Projection/renderer and I/O adapters sit behind Core-owned interfaces. |
| `practice/` (placeholder) | Educational | Foreshadows the Educational Engine. |
| `sequencer/` (placeholder) | Performance | Transport/playback foreshadows the Performance Engine. |

No package moves as a result of ADR-0006. This table is the authority for which engine owns which code until a future, separately-authorized reorganization changes the physical layout.

## Relationship to existing documents

- [ADR-0001](../decisions/ADR-0001-REPOSITORY-OWNERSHIP.md) — repository ownership; unchanged. This repository still owns the musical core and the layers above it, and still is not luthiers-toolbox or CNC-Production-Shop.
- [ADR-0003](../decisions/ADR-0003-MUSIC-CANONICAL.md) — music is canonical; the four engines sit *around* that principle, they do not weaken it. Musical Core is where "canonical" lives.
- [ADR-0004](../decisions/ADR-0004-CANDIDATE-GENERATION.md) — candidate generation; Musical Core.
- [SYSTEM_BOUNDARIES.md](SYSTEM_BOUNDARIES.md) — the earlier per-subsystem boundary sketch; the four engines are the coarser constitutional grouping above those subsystems.
- The captured planning handoff remains valid as preservation and queue authority; it will later split into a Learning-Object/curriculum foundation (Educational) and a separate Creative Engine handoff.

DO-004 (deterministic selection) is Musical Core and proceeds unaffected; ADR-0005 is reserved for it.
