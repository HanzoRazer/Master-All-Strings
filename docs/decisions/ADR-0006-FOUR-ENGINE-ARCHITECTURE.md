# ADR-0006: Four-Engine Architecture

## Status
Accepted

## Context

The product has grown a set of large capability areas — a canonical musical model and the Musical Spatial Mapping Engine; curriculum, coaching, and assessment; AI score entry and composition; Smart Guitar and live performance. A planning handoff captured all of these, but grouped them under a single "educational platform," which was already straining: score authoring and notation had been filed under education because there was nowhere else to put them.

Treating everything downstream of the musical core as one subsystem produces an oversized catch-all with no internal dependency discipline. The alternative is to name the major capability areas explicitly and give each a constitutional boundary before significant implementation begins, so ownership and dependency direction are decided deliberately rather than by whichever Dev Order lands first.

This decision does not reopen, delay, or alter DO-004. Deterministic candidate selection remains Musical Core work under both the previous and the current architectural descriptions.

## Decision

The system is composed of **four engines**. Each is a constitutional boundary: it owns a set of contracts, a dependency direction, a roadmap, and a Dev Order namespace.

- **Musical Core** — canonical musical truth and everything mechanically derivable from it.
- **Educational Engine** — pedagogical meaning, curriculum, and the learner.
- **Creative Engine** — authoring, composition, and AI-assisted score entry.
- **Performance Engine** — live capture, playback, and device integration.

### An engine is a governance boundary, not a package boundary

An engine defines authority, dependency direction, roadmap ownership, contracts, and Dev Order namespaces. **It does not require a matching top-level Python package until implementation pressure justifies one.**

The existing packages stay where they are. `core/`, `instruments/`, and `spatial_mapping/` are **not** moved under a `musical_core/` directory. Doing so would break imports and mix an architectural clarification with a repository-wide refactor that delivers no functional value.

Each package should declare which engine owns it (a one-line statement in its `__init__` docstring is sufficient). Applying those declarations to the existing packages is a small, separate follow-up and is deliberately not bundled with this decision, so the ratification stays reviewable on its own and does not touch Musical Core source while DO-004 is in flight.

A future package reorganization may occur **only** when all of the following hold:

1. at least two engines have substantial production implementations;
2. import ownership is becoming genuinely unclear;
3. the migration has its own Dev Order;
4. compatibility aliases and rollout are specified;
5. the refactor produces a measurable architectural benefit.

The engine taxonomy must not be used as an excuse to reorganize healthy code.

### Engine ownership

**Musical Core** owns: the canonical musical model; instrument and tuning profiles; the MSME; candidate generation; deterministic selection; mechanical phrase and chord planning; spatial evidence; projection contracts; notation/TAB/MIDI *semantic* projection; and deterministic musical transformations that require no pedagogical judgment. It depends on no other engine.

**Educational Engine** owns: Learning Objects; curriculum; etudes; references; learning paths; educational interpretation; difficulty; coaching; assessment; practice metrics; progress; teacher authority; pedagogical phrase-plan selection; curriculum compatibility; and tuning-specific instructional meaning.

**Creative Engine** owns: Smart Score Entry; intent capture; composition; arrangement; semantic transformation proposals; "vibe the score"; AI proposal planning; score-authoring UX; direct precision editing; and the preview / compare / accept / reject / regenerate / undo workflows. It consumes Musical Core contracts and may request Educational constraints.

**Performance Engine** owns: live capture; playback; performance sessions; Smart Guitar integration; teacher/student synchronization; performance telemetry; timing and note-observation evidence; device adapters; and offline / fail-safe behavior. It emits observed performance evidence; it does not determine curriculum meaning or canonical musical truth.

### Dependency rule

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

- Musical Core depends on none of the other engines.
- Educational depends on Musical Core.
- Creative depends on Musical Core and may consume Educational contracts.
- Performance depends on Musical Core.
- Educational may consume Performance evidence.
- Creative must not depend directly on Performance device implementations.
- Performance must not embed curriculum or coaching policy.
- No engine may mutate another engine's authoritative records directly.

## The three seams

Most engine assignments are obvious. Three are not, because a single capability spans a boundary. These are the load-bearing decisions.

### Seam 1 — Authoring versus projection

Splitting these keeps a notation renderer from quietly becoming a music editor.

**Creative owns changing the music:** musical intent entry, Smart Score Entry, composition, arrangement, transformation requests, semantic edit proposals, executable score-edit command planning, user-facing authoring workflows, direct manipulation as an editing interaction, and "vibe the score."

**Musical Core owns faithfully projecting the resulting music:** the canonical representation, deterministic projection contracts, semantic-to-representation conversion, notation/TAB/MIDI projection requests and results, projection determinism, source-revision binding, and renderer-independent projection semantics.

Concrete renderer integrations live behind a Core-owned projection interface and may be implemented in adapter packages:

```text
Creative Engine  --produces semantic edits-->  Canonical Music (Musical Core)
                                                        |
                                                        v
                                          Projection Contract (Musical Core)
                                                        |
                                                        v
                                              Notation Renderer Adapter
```

A notation renderer is not inherently creative. It must not decide the music, simplify a phrase, choose a teaching strategy, or reinterpret intent. It **may** make deterministic engraving choices — spacing, stems, beams, system breaks, collision resolution.

### Seam 2 — Spatial evidence versus educational interpretation

This is the strongest seam in the model. Musical Core must **not** own a contract named `EducationalAnalysis`; that would fuse instrument facts with pedagogical conclusions. Two contracts, one dependency direction.

**Musical Core owns `SpatialEvidenceV1`** — factual or mechanically derived: candidate positions; selected positions (once selection exists); string usage; fret and position ranges; shifts; repeated-position patterns; open-string use; crossings; alternate playable mappings; instrument and tuning profile; source event and phrase references; algorithm identity and version; unsupported or ambiguous cases. It says **what occurred spatially**.

The Core contract must avoid pedagogical terms — *easy*, *difficult*, *beginner*, *advanced*, *recommended for study*, *poor fingering*. It may report *three shifts*, *maximum fret 12*, *four-string span*, *two alternate mappings*, *open-string participation*, *a large positional displacement*.

**Educational Engine owns `EducationalInterpretationV1`** — estimated difficulty; beginner suitability; lesson concepts; fingering recommendations; technique labels; simplification opportunities; curriculum compatibility; coaching observations; assessment criteria. It must **cite** `SpatialEvidenceV1` records and may not redefine or overwrite Core evidence.

```text
Musical Core  --SpatialEvidenceV1-->  Educational Engine  --EducationalInterpretationV1-->
```

Education decides what the facts mean for a learner.

### Seam 3 — Mechanical phrase planning versus pedagogical sequencing

**Musical Core owns mechanical phrase planning.** Given canonical music, an instrument, a tuning, and explicit non-pedagogical constraints, what valid path(s) through playable positions exist? Core handles continuity across events, candidate-path generation, deterministic path selection under declared non-pedagogical policies, bounded/minimized shifts *when explicitly requested*, voice continuity, chord-position compatibility, physical reach constraints, string/fret constraints, ambiguity preservation, and explanation of why paths were admitted or rejected.

Core may support explicit objective functions — `minimize total position movement`, `minimize string changes`, `stay below fret 7`, `avoid open strings`, `remain within positions 1–5`. These are mechanical constraints when supplied explicitly. Core must not decide that one objective is educationally superior.

**Educational Engine owns pedagogical sequencing.** Which mechanically valid plan best serves this learner, lesson, or objective? Introducing one new technique at a time; choosing a harder fingering for instructional value; reinforcing curriculum; sequencing exercises; controlling cognitive load; deciding whether to preserve or remove shifts; beginner/intermediate/advanced adaptation; mastery progression; assessment-driven variation; teacher-selected policy.

```text
Educational objective
        -> explicit planning constraints/preferences
        -> Musical Core phrase planner
        -> valid, evidence-bearing phrase plans
        -> Educational selection and explanation
```

Core owns the path search. Education owns why a learner should use one path rather than another.

## Consequences

Every future Dev Order names the engine it belongs to, and its dependencies must respect the direction above. A Dev Order that would make Musical Core depend on Educational, Creative, or Performance is malformed by construction.

The existing placeholders foreshadow two of the engines: `practice/` (repetitions, tempo progression, ear-training, student guidance) is Educational; `sequencer/` (transport, playback, track handling) is Performance. Neither is built here; naming their engines now prevents them from accreting Musical Core responsibilities later.

The `SpatialEvidenceV1` / `EducationalInterpretationV1` split means DO-004's selected positions become Core evidence that the Educational Engine later cites — the selection Dev Order does not need to anticipate pedagogy, and the pedagogy Dev Order does not get to relitigate selection.

The captured planning handoff (`HANDOFF-2026-07-21-EDUCATIONAL-PLATFORM-SMART-NOTATION.md`) remains valid as a preservation and queue document. It should later be narrowed to a Learning-Object-and-curriculum foundation handoff, with its score-authoring material moved into a separate Creative Engine handoff, each with traceability links back to the original. It is not discarded or silently replaced.

The operational detail of this decision — the engine map, the seam contracts, and how a Dev Order declares its engine — lives in [`FOUR_ENGINE_SYSTEM_MODEL.md`](../architecture/FOUR_ENGINE_SYSTEM_MODEL.md).

## Rejected alternatives

**One educational subsystem.** The status quo of the planning handoff. Produces a catch-all with no internal dependency discipline; score authoring and notation had already been misfiled under it.

**Immediate top-level packages per engine.** Would move healthy, just-merged code for no functional gain, break imports, and couple a naming decision to a repository-wide refactor. Deferred behind five explicit conditions instead.

**A single `EducationalAnalysis` contract owned by Core.** Fuses instrument facts with pedagogical judgment, which is exactly the seam this decision most wants to keep clean. Split into `SpatialEvidenceV1` and `EducationalInterpretationV1`.

**Notation under Creative.** A renderer that can reinterpret or simplify music is a music editor wearing an engraver's coat. Projection is deterministic and belongs to Musical Core; only authoring is Creative.
