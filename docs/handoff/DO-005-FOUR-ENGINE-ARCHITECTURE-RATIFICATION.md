# Dev-Ready Engineering Handoff

**Dev Order:** DO-005  
**Title:** Four-Engine Architecture Ratification  
**Repository:** `HanzoRazer/Master-All-Strings`  
**Branch:** `agent/curriculum-smart-notation-roadmap`  
**Status:** Dev-ready  
**Execution posture:** documentation and governance only; no production package reorganization or runtime behavior change

---

## 1. Objective

Ratify a four-engine constitutional architecture for Master All Strings that assigns clear ownership, dependency direction, and cross-engine contract boundaries to the Musical Core, Educational, Creative, and Performance engines.

This Dev Order establishes the system-wide architectural spine required to decompose future development without turning the Educational Platform handoff into a catch-all and without disturbing current Musical Core implementation work.

---

## 2. Architectural Context

### Subsystem

Cross-system architecture and governance.

This Dev Order does not belong to any one product engine. It establishes the constitutional boundary within which all four engines operate.

### Dependencies

- Existing Product Charter.
- Existing canonical-music decisions.
- Existing MSME candidate-generation architecture.
- DO-004 deterministic selection work, which continues independently.
- `HANDOFF-2026-07-21-EDUCATIONAL-PLATFORM-SMART-NOTATION.md`, which preserves the complete capability inventory that later engine-specific handoffs must decompose.

### Upstream components

- canonical musical model;
- instrument and tuning profiles;
- MSME candidate generation;
- existing repository governance and ADR conventions.

### Downstream consumers

- future Musical Core Dev Orders;
- Learning Object and curriculum Dev Orders;
- AI Smart Score Entry and score-authoring Dev Orders;
- notation, TAB, and MIDI projection work;
- practice, coaching, and assessment work;
- Smart Guitar and performance-capture integrations;
- documentation, schemas, package ownership, and future repository restructuring decisions.

### Constitutional boundary

The four engines are governance and authority boundaries in this Dev Order. They are not immediate top-level Python package boundaries.

The Dev Order must preserve these constitutional rules:

1. Musical Core owns canonical musical truth and mechanically derived evidence.
2. Educational owns pedagogical interpretation, curriculum, assessment, and coaching policy.
3. Creative owns intent capture, score authoring, composition, arrangement, and controlled musical-change workflows.
4. Performance owns live capture, playback, telemetry, device integration, and session evidence.
5. No engine may directly mutate another engine's authoritative records.
6. Smart Guitar remains a consumer and integration surface, not the canonical source of truth.
7. DO-004 remains unblocked and retains its existing ADR reservation.

This work belongs at the cross-system architecture layer because the disputed seams—notation projection, spatial evidence, educational interpretation, phrase planning, and device evidence—span multiple engines and cannot be settled safely inside a single feature handoff.

---

## 3. Scope

### Authorized work

This Dev Order authorizes:

- creation of the four-engine architecture ADR;
- creation of a concise four-engine system-model architecture document;
- definition of ownership for the Musical Core, Educational, Creative, and Performance engines;
- definition of allowed dependency directions;
- definition of cross-engine contract seams;
- explicit rulings for notation and score projection;
- explicit rulings for MSME spatial evidence and educational interpretation;
- explicit rulings for mechanical phrase planning and pedagogical sequencing;
- documentation of engine-to-package mapping without moving production packages;
- update of architecture indexes and the Product Charter so the new system model is discoverable;
- a traceability note connecting the existing educational-platform handoff to the new engine model;
- tests or validation utilities required to prevent contradictory ownership declarations in architecture records.

### Required engine assignments

#### Musical Core

Must own:

- canonical musical model;
- instrument and tuning profiles;
- MSME candidate generation;
- deterministic candidate selection;
- mechanical phrase and chord planning;
- spatial evidence;
- renderer-independent score-projection contracts;
- notation, TAB, and MIDI semantic projection;
- deterministic musical transformations that require no pedagogical judgment.

#### Educational Engine

Must own:

- Learning Objects;
- curriculum;
- etudes and references;
- learning paths;
- pedagogical interpretation;
- difficulty assessment;
- coaching;
- formal assessment;
- practice metrics and progress;
- teacher authority;
- pedagogical selection among valid phrase plans;
- instructional meaning of alternate tunings.

#### Creative Engine

Must own:

- AI Smart Score Entry;
- intent capture;
- composition;
- arrangement;
- semantic transformation proposals;
- score-authoring interaction;
- direct precision editing;
- preview, compare, accept, reject, regenerate, and undo workflows;
- "vibe the score" as an interaction concept.

#### Performance Engine

Must own:

- live capture;
- playback;
- performance sessions;
- Smart Guitar integration;
- teacher/student synchronization;
- timing and note-observation evidence;
- device adapters;
- performance telemetry;
- offline and fail-safe device behavior.

### Explicit seam rulings

#### Notation and score projection

- Creative owns changing the music.
- Musical Core owns faithfully projecting canonical music into notation, TAB, and MIDI semantics.
- Concrete renderer adapters operate behind a Musical Core-owned projection contract.
- Engraving may resolve spacing, beams, stems, collisions, systems, and pages, but may not change musical meaning.

#### Spatial evidence and educational interpretation

- Musical Core owns `SpatialEvidenceV1` or the equivalent versioned evidence contract.
- Educational owns `EducationalInterpretationV1` or the equivalent versioned interpretation contract.
- Educational interpretation must cite Core evidence.
- Core evidence must not include pedagogical labels such as beginner, difficult, recommended, or poor fingering.

#### Phrase planning

- Musical Core owns mechanically valid multi-event path generation and selection under explicit constraints.
- Educational owns choosing or sequencing a valid plan for a learner or lesson objective.
- Mechanical optimization policies must be explicit inputs, not hidden pedagogical assumptions.

### Out-of-scope unless separately authorized

Everything not listed above is out of scope, including production code moves, new runtime features, schema implementation for later engines, and redesign of current MSME algorithms.

---

## 4. Design Decisions

### D1 — Deliverable form

The four-engine model will be ratified through:

1. `ADR-0006-FOUR-ENGINE-ARCHITECTURE.md`;
2. `FOUR_ENGINE_SYSTEM_MODEL.md`.

The ADR records the constitutional decision. The architecture document records the operational ownership map, dependency rules, and seams.

### D2 — DO-004 is not blocked

DO-004 proceeds independently as Musical Core work.

ADR-0005 remains reserved for DO-004. This Dev Order uses ADR-0006.

### D3 — Engine means governance boundary now

An engine defines:

- authority;
- dependency direction;
- contract ownership;
- roadmap ownership;
- Dev Order scope;
- evidence and interpretation boundaries.

An engine does not yet require a matching top-level package.

### D4 — No immediate package reorganization

Existing packages such as:

```text
src/master_all_strings/core/
src/master_all_strings/instruments/
src/master_all_strings/core/spatial_mapping/
```

remain in place.

No code is moved under `musical_core/`, `education/`, `creative/`, or `performance/` solely to match the taxonomy.

### D5 — Future package reorganization requires its own Dev Order

A future physical package reorganization is allowed only when:

- at least two engines have substantial production implementations;
- existing package ownership is demonstrably unclear;
- compatibility and migration are planned;
- the reorganization has measurable architectural benefit;
- import churn is isolated from feature work.

### D6 — Musical Core has zero inward engine dependencies

Musical Core may depend on general-purpose infrastructure, but not on Educational, Creative, or Performance domain policy.

### D7 — Educational depends on Musical Core evidence

Educational may consume canonical music, instrument/tuning context, phrase plans, and spatial evidence. It may not overwrite those records or redefine mechanical facts.

### D8 — Creative depends on Musical Core and may consume Educational constraints

Creative may request instructional constraints or use educational objectives, but its authoring operations must resolve into validated changes against canonical music.

### D9 — Performance depends on Musical Core and emits observation evidence

Performance may consume canonical music and timing expectations. It emits observed performance evidence for downstream Educational interpretation. It must not embed curriculum or coaching policy.

### D10 — Notation authoring and notation projection are separate

Creative owns authoring intent and editing interaction.

Musical Core owns deterministic, renderer-independent projection semantics.

### D11 — Spatial evidence and pedagogy use separate contracts

A Core-owned evidence contract and an Educational-owned interpretation contract are required. A single conflated `EducationalAnalysis` contract is rejected.

### D12 — Mechanical planning and pedagogical sequencing are separate

Core owns valid path search and explicit mechanical optimization. Educational owns why and when a learner should use a given path.

### D13 — Engine ownership is declared, not inferred from directory names

Architecture records must include an explicit package-to-engine ownership table. Directory names alone do not establish authority.

### D14 — Existing preservation handoff remains source evidence

`HANDOFF-2026-07-21-EDUCATIONAL-PLATFORM-SMART-NOTATION.md` is not deleted or silently rewritten in this Dev Order.

It remains a preservation artifact. A later decomposition Dev Order may supersede portions of it while preserving traceability.

### D15 — No production behavior changes

This Dev Order is documentation and governance only. No runtime API, schema, serialization, or behavior changes are authorized.

---

## 5. File-by-File Patch Plan

### Create

#### `docs/decisions/ADR-0006-FOUR-ENGINE-ARCHITECTURE.md`

Create the constitutional decision record.

It must include:

- context and motivation;
- four engine definitions;
- dependency direction;
- notation/projection seam;
- spatial-evidence/educational-interpretation seam;
- phrase-planning/pedagogical-sequencing seam;
- governance-boundary-now ruling;
- non-blocking relationship to DO-004;
- consequences;
- rejected alternatives.

#### `docs/architecture/FOUR_ENGINE_SYSTEM_MODEL.md`

Create the operational architecture document.

It must include:

- engine responsibilities;
- authority tables;
- dependency matrix;
- allowed and forbidden cross-engine flows;
- package-to-engine ownership map;
- contract ownership map;
- current-state versus future-state distinction;
- examples of valid and invalid interactions;
- later package-reorganization trigger conditions.

#### `docs/planning/ENGINE_OWNERSHIP_REGISTER.md`

Create a compact authoritative register with one row per current or planned package, schema family, major contract, architecture document, and queue family.

Required columns:

- artifact or capability;
- owning engine;
- consuming engines;
- authority type;
- current package or location;
- status;
- governing ADR;
- notes.

This register must distinguish current ownership from future planned implementation.

#### `tests/architecture/test_engine_architecture_docs.py`

Create architecture-document integrity tests if repository conventions permit tests over documentation.

The test must verify:

- all four engines appear in the ADR, architecture document, and ownership register;
- ADR-0006 states DO-004 is unblocked;
- Musical Core has no inward engine dependency;
- notation authoring and projection are assigned separately;
- spatial evidence and educational interpretation are assigned separately;
- phrase planning and pedagogical sequencing are assigned separately;
- the ownership register contains no artifact with multiple authoritative engines.

If documentation tests are inconsistent with repository conventions, replace this file with the utility described in Section 7 and test that utility instead.

### Modify

#### `docs/architecture/PRODUCT_CHARTER.md`

Add a concise four-engine system statement and the rule that the engine taxonomy is a governance boundary, not an immediate package mandate.

Do not turn the Product Charter into the detailed engine specification.

#### `README.md`

Add a short architecture link section pointing to the four-engine system model and ADR-0006.

Do not claim that Educational, Creative, or Performance runtime implementations already exist.

#### `docs/handoff/HANDOFF-2026-07-21-EDUCATIONAL-PLATFORM-SMART-NOTATION.md`

Add only a non-destructive supersession note near the top stating:

- the handoff remains the preservation source;
- cross-engine ownership is governed by ADR-0006;
- implementation must be decomposed by engine;
- no capability is removed by the taxonomy.

Do not rewrite or delete the detailed capability inventory in this Dev Order.

#### Existing documentation index, if present

Add links to:

- ADR-0006;
- `FOUR_ENGINE_SYSTEM_MODEL.md`;
- `ENGINE_OWNERSHIP_REGISTER.md`.

### Remove

No files are authorized for removal.

---

## 6. Interfaces

### Documentation contracts

This Dev Order introduces three governance interfaces:

1. **Engine taxonomy** — the authoritative four-engine ownership model.
2. **Dependency matrix** — allowed engine-to-engine dependency directions.
3. **Ownership register** — artifact-level declaration of authority and consumption.

### Contract names reserved by this Dev Order

The architecture documents reserve, but do not implement:

- `SpatialEvidenceV1` — Musical Core-owned;
- `EducationalInterpretationV1` — Educational-owned;
- score-projection request/result contract family — Musical Core-owned;
- score-edit proposal/command contract family — Creative-owned;
- observed-performance evidence contract family — Performance-owned.

Exact dataclass and schema shapes are deferred to later Dev Orders.

### Package interfaces

No Python package paths, imports, exports, or public runtime interfaces change.

### Schema interfaces

No schema files change.

### CLI and API interfaces

No CLI or runtime API changes.

### Compatibility

All changes are additive documentation and governance changes.

No breaking interface change is authorized.

---

## 7. Utilities

### Required utility

Create one validator unless existing documentation tests cover the same checks cleanly.

#### `scripts/check_engine_architecture.py`

Responsibilities:

- parse the ownership register;
- verify each artifact has exactly one authoritative engine;
- verify engine names are limited to Musical Core, Educational, Creative, and Performance;
- verify Musical Core declares no dependency on another product engine;
- verify all cross-engine seams named in ADR-0006 appear in the architecture document;
- verify reserved contract ownership is unique;
- verify DO-004 non-blocking language is present;
- verify the preservation handoff references ADR-0006 without deleting its capability inventory.

The utility must be deterministic, offline, and read-only.

### Optional helper

A small parser for the ownership register may be introduced under `scripts/lib/` only if needed for clean testing.

No runtime utilities are authorized.

---

## 8. Test Plan

### Unit tests

Test the architecture validator or documentation-integrity functions for:

- valid four-engine register;
- unknown engine name;
- duplicate authoritative owners;
- missing owner;
- forbidden Musical Core dependency;
- missing seam declaration;
- missing DO-004 non-blocking statement;
- missing preservation-handoff traceability note.

### Regression tests

- Existing test suite remains green.
- Existing MSME candidate-generation behavior remains unchanged.
- DO-004 files and ADR reservation remain untouched.
- No imports or package paths change.

### Serialization tests

Not applicable. No runtime serialization contract is introduced.

### Schema tests

Not applicable. No schema is added or changed.

### Boundary tests

Required assertions:

1. Musical Core does not depend on Educational, Creative, or Performance.
2. Educational interpretation consumes but does not own spatial facts.
3. Creative authoring does not own deterministic projection truth.
4. Performance evidence does not contain curriculum or coaching policy.
5. No artifact in the ownership register has more than one authoritative engine.

### Negative cases

- A renderer assigned to Creative as authoritative for projection must fail validation.
- `EducationalAnalysis` assigned jointly to Musical Core and Educational must fail validation.
- phrase planning assigned wholly to Educational with no Core mechanical layer must fail validation.
- Smart Guitar assigned as the canonical source of truth must fail validation.
- package relocation instructions inside this Dev Order must fail review.

### Invariants

- one authoritative engine per artifact or contract;
- Musical Core has no inward product-engine dependency;
- evidence and interpretation remain separate;
- authoring and projection remain separate;
- mechanical planning and pedagogical sequencing remain separate;
- taxonomy does not erase preserved capabilities;
- production behavior is unchanged.

### Expected coverage

- 100% line coverage for `scripts/check_engine_architecture.py` and any helper module introduced by this Dev Order;
- full branch coverage for validation failure paths where repository tooling supports it;
- no reduction in overall repository coverage.

---

## 9. Acceptance Criteria

This Dev Order is complete only when all of the following are true:

1. ADR-0006 exists and is marked Accepted or the repository's equivalent ratified state.
2. `FOUR_ENGINE_SYSTEM_MODEL.md` exists and defines all four engines.
3. `ENGINE_OWNERSHIP_REGISTER.md` exists and assigns one authoritative engine per listed artifact.
4. DO-004 is explicitly documented as unblocked and unchanged.
5. ADR-0005 remains reserved for DO-004.
6. Existing production packages have not been moved.
7. The notation-authoring/projection seam is explicit.
8. The spatial-evidence/educational-interpretation seam is explicit.
9. The mechanical-planning/pedagogical-sequencing seam is explicit.
10. The preservation handoff remains intact and references ADR-0006.
11. Product Charter and README links are updated without overstating implementation.
12. Architecture validation passes.
13. Full repository test suite passes.
14. Linting and formatting checks pass for any new script or test code.
15. No runtime behavior, public API, or schema changes are present.

---

## 10. Rollout Order

### Commit 1 — Constitutional decision

Create:

- `docs/decisions/ADR-0006-FOUR-ENGINE-ARCHITECTURE.md`.

Purpose:

Ratify the four-engine taxonomy and the three seam rulings before dependent documentation is written.

### Commit 2 — Operational architecture map

Create:

- `docs/architecture/FOUR_ENGINE_SYSTEM_MODEL.md`;
- `docs/planning/ENGINE_OWNERSHIP_REGISTER.md`.

Purpose:

Translate the ADR into explicit responsibilities, dependencies, package ownership, and contract ownership.

### Commit 3 — Validation and tests

Create:

- `scripts/check_engine_architecture.py`;
- helper module if required;
- architecture validation tests.

Purpose:

Make the constitutional boundary machine-checkable rather than advisory prose only.

### Commit 4 — Repository integration

Modify:

- `docs/architecture/PRODUCT_CHARTER.md`;
- `README.md`;
- documentation index;
- preservation handoff traceability note.

Purpose:

Make the architecture discoverable and connect the existing preserved capability inventory to its new ownership model.

### Commit 5 — Verification report

Add or update the repository's implementation report mechanism with:

- files changed;
- validation results;
- full-suite result;
- confirmation of zero runtime changes;
- confirmation that DO-004 remained unblocked;
- exact next authorized decomposition item.

Do not combine all work into one large commit unless repository policy explicitly requires squashing before review.

---

## 11. Risks

### Architectural risk

**Risk:** The engine taxonomy becomes another naming layer without constraining real ownership.

**Mitigation:** The ownership register and validator require one authoritative engine per artifact and encode dependency rules.

### Compatibility risk

**Risk:** Treating engines as packages immediately would break imports and churn recently merged code.

**Mitigation:** This Dev Order explicitly makes engines governance boundaries only and prohibits package moves.

### Performance risk

None. No runtime code path changes.

### Migration risk

**Risk:** Later package reorganization could be assumed to be automatically authorized by this taxonomy.

**Mitigation:** Any physical package reorganization requires a separate Dev Order with migration and compatibility planning.

### Scope risk

**Risk:** The existing educational-platform handoff is rewritten prematurely and loses preserved capabilities.

**Mitigation:** This Dev Order permits only a traceability note and prohibits deletion or compression of the capability inventory.

### Dependency risk

**Risk:** DO-004 is delayed by the architecture discussion.

**Mitigation:** ADR-0006 must state explicitly that DO-004 proceeds independently and retains ADR-0005.

---

## 12. Constitutional Impact

**Subsystem:**  
Cross-system architecture and governance

**Public API:**  
Unchanged

**Package layout:**  
Unchanged

**Schema:**  
Unchanged

**Serialization:**  
Unchanged

**Measurement:**  
Unchanged

**Mechanical evidence:**  
Ownership clarified; behavior unchanged

**Interpretation:**  
Ownership clarified; behavior unchanged

**Creative authoring:**  
Ownership clarified; not implemented

**Performance integration:**  
Ownership clarified; not implemented

**Governance:**  
Extended with four-engine authority and dependency rules

**Scientific validity:**  
Preserved by separating mechanically derived evidence from pedagogical interpretation

**Production behavior:**  
Unchanged

**DO-004:**  
Unblocked and unchanged

---

## 13. Non-Goals

This Dev Order does not authorize:

- moving existing Python packages;
- renaming `core/`, `instruments/`, or spatial-mapping modules;
- changing imports;
- implementing Learning Objects;
- implementing curriculum registries;
- implementing `SpatialEvidenceV1`;
- implementing `EducationalInterpretationV1`;
- implementing score-edit commands;
- implementing notation, TAB, or MIDI rendering;
- selecting a notation-rendering library;
- integrating an AI provider;
- implementing AI Smart Score Entry;
- implementing coaching or assessment;
- implementing performance capture;
- implementing Smart Guitar hardware or runtime integration;
- changing candidate generation;
- changing deterministic selection under DO-004;
- rewriting the full educational-platform preservation handoff;
- creating empty engine packages merely to mirror the taxonomy;
- adding placeholder UI or mock endpoints.

---

## 14. Definition of Done

The sprint is complete only when:

- ADR-0006 ratifies the four-engine architecture;
- the operational system-model document defines responsibilities, dependencies, and seams;
- the ownership register assigns one authoritative engine per artifact;
- architecture validation is automated and green;
- DO-004 remains unblocked and retains ADR-0005;
- the existing preservation handoff remains intact and traceable;
- no production packages are moved;
- no runtime, schema, serialization, or public API behavior changes;
- all new tests pass with required coverage;
- the full repository test suite passes;
- formatting, linting, and governance checks pass;
- README, Product Charter, and documentation indexes are updated accurately;
- the implementation matches the approved architecture;
- no constitutional boundary is violated;
- the completion report identifies the next engine-specific Dev Order without beginning it.

A reviewer must be able to answer **yes** to this question:

> Is the four-engine constitutional architecture ratified, discoverable, machine-checked, non-breaking, and ready to govern subsequent Master All Strings development?