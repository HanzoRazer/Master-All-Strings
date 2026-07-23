> ## Preservation snapshot — read first
>
> This document is preserved **verbatim** as a historical planning and
> capability-preservation artifact. It was authored on 2026-07-21 *before* the
> four-engine architecture ([ADR-0006](../decisions/ADR-0006-FOUR-ENGINE-ARCHITECTURE.md))
> was ratified, and its internal instructions reflect that earlier context. Read
> the body below as a record of what was captured, **not** as current build
> instructions. Specifically:
>
> - **Its planned ADR numbers are superseded — do not create them as written.**
>   `ADR-0005` is **reserved for DO-004** (deterministic candidate selection), not
>   Learning Objects. `ADR-0006` is the **four-engine architecture**, which absorbs
>   "notation as projection" as its Seam 1. The `ADR-0005`–`ADR-0008` file-creation
>   lines in Sections 5 and 6.1 are historical placeholders, not current authority.
> - Its **"Status: authorized …"** line and its file-creation instructions describe
>   the document's original authoring context, not current repository state.
> - The authoritative mapping of this document's capabilities onto the four engines
>   is the DO-005 decomposition plan (`docs/planning/FOUR_ENGINE_HANDOFF_DECOMPOSITION.md`,
>   produced by the DO-005 continuation), governed by ADR-0006 — not this file.
>
> Everything below this banner is the original content, unaltered.

---

# Dev-Ready Engineering Handoff — Educational Platform, Learning Objects, and AI Smart Notation

**Date:** 2026-07-21  
**Repository:** `HanzoRazer/Master-All-Strings`  
**Branch:** `agent/curriculum-smart-notation-roadmap`  
**Status:** authorized for architecture capture and development-queue construction  
**Implementation posture:** contracts and planning first; no production AI, notation engraving, subscription, or Smart Guitar runtime implementation in this tranche

---

## 1. Objective

Create the durable architectural and development foundation that allows Master All Strings to evolve from a MIDI-oriented musical tool into a curriculum-centered musical learning platform.

This tranche must establish, without losing any previously discussed capability:

1. the **Learning Object** as the primary educational entity;
2. MIDI, notation, TAB, audio, PDF, backing tracks, and future formats as optional assets or projections of canonical music;
3. a strict separation between official curriculum, etudes, reference material, public-domain songs, purchased packs, and user-imported material;
4. tuning-aware educational analysis, including alternate tunings as an architectural requirement;
5. MSME-derived educational metadata and playability evidence;
6. AI coaching as an interpretation layer downstream of MSME evidence;
7. AI Smart Score Entry as intent-based musical authoring rather than symbol-coordinate editing;
8. deterministic notation engraving and stable user control;
9. a traceable implementation queue that prevents any accepted or deferred idea from disappearing.

The outcome of this tranche is a set of accepted architecture records, versioned schemas, registries, queue entries, validation utilities, and tests that make later implementation Dev Orders executable.

---

## 2. Architectural Context

### 2.1 Repository role

Master All Strings owns the canonical musical model, the Musical Spatial Mapping Engine, and the educational interpretation layers built on top of them.

The repository already establishes these boundaries:

- music is canonical;
- instrument representation is an adapter;
- candidate generation answers where music can be played without embedding pedagogical preference;
- pedagogical interpretation belongs to a later layer;
- Smart Guitar is a future integration or consumer, not the architectural source of truth.

This handoff extends those boundaries rather than replacing them.

### 2.2 Position in the system

```text
Canonical Musical Model
        |
        v
Instrument + Tuning Profile
        |
        v
MSME Candidate Generation
        |
        v
Selection / Phrase Planning / Educational Analysis
        |
        +--------------------+
        |                    |
        v                    v
Learning Object          Score Projection
        |                    |
        v                    v
Curriculum / Practice    Notation / TAB / MIDI
        |
        v
AI Coaching / Assessment
        |
        v
Web, Desktop, Teacher Studio, Smart Guitar
```

### 2.3 Constitutional boundary

This tranche must not make notation, MIDI, TAB, audio, an AI model, or a Smart Guitar device the canonical source of musical truth.

The canonical musical representation remains authoritative. All external formats and rendered views are imports, assets, evidence, or projections.

---

## 3. Scope

### 3.1 Authorized work

This tranche is authorized to:

- record accepted product and architecture decisions;
- create a complete capability preservation register;
- define the Learning Object v1 contract;
- define educational metadata and curriculum-registry contracts;
- define tuning declaration and compatibility contracts;
- define MSME educational-analysis result contracts;
- define semantic score-edit command contracts;
- define a deterministic score-projection boundary;
- define development queue entries and dependencies;
- create validators and fixture loaders for the new contracts;
- create representative fixtures and contract tests;
- update repository documentation indexes and product architecture documents.

### 3.2 Explicitly preserved capabilities

Every item below must appear in the preservation register and receive a disposition. No item may be silently dropped.

#### Curriculum and library model

- curriculum as intellectual property rather than a pile of files;
- Beginner, Intermediate, Advanced, Theory, Technique, and Ear Training curriculum branches;
- etudes organized by learning purpose, including Picking, Legato, Rhythm, Arpeggios, Chords, Position Shifts, String Crossing, Finger Independence, and alternate-tuning studies;
- reference material including Scales, Modes, Chords, Intervals, and Neck Maps;
- Songs as one branch rather than the center of the product;
- public-domain songs;
- user-imported songs;
- purchased content packs;
- official content and user content kept logically separate;
- learning paths, practice routines, challenges, and assessments;
- teacher-created curriculum and future community curriculum.

#### Learning Object model

- metadata;
- learning objectives;
- MIDI as an optional asset;
- standard notation as an optional projection or asset;
- TAB as an optional projection or asset;
- backing track;
- PDF;
- audio;
- MusicXML import/export capability;
- Guitar Pro import capability;
- ASCII TAB import capability;
- MSME analysis;
- suggested fingering;
- practice metrics;
- assessment;
- coaching rules;
- bookmarks and lesson notes;
- source, composer, tempo, key, tuning, difficulty, concepts, and recommended region.

#### MSME educational analysis

- every playable location;
- alternate positions and alternate fingerings;
- selected fretboard region;
- highest fret;
- string usage;
- position shifts;
- ability to remain in a named or numbered position;
- barre-chord detection;
- string-skipping detection;
- open-string use;
- technical-concept detection;
- estimated difficulty;
- beginner simplification opportunities;
- compatibility with lesson objectives;
- explanatory evidence for every derived educational claim.

#### Tuning architecture

- standard tuning as the initial curriculum default;
- alternate tuning support as a core architectural requirement;
- tuning profile supplied explicitly to MSME operations;
- no silent standard-tuning assumption when a profile is present;
- required tuning and compatible tuning declarations on Learning Objects;
- tuning-independent, tuning-specific, and MSME-adaptable classifications;
- future curriculum such as Drop D, Open G, Open D, DADGAD, half-step-down, modal, and other profiles;
- tuning-aware fingering and coaching;
- future tuning verification and lesson-protection workflows;
- remapping a musical passage for a different tuning without changing canonical pitch intent unless explicitly requested.

#### AI coaching

- MSME determines musical-spatial evidence;
- AI determines how to teach from that evidence;
- coaching receives lesson target, instrument profile, tuning profile, MSME result, and observed performance;
- AI may explain, suggest, compare, simplify, or challenge;
- AI must not invent fretboard facts that contradict MSME;
- assessment and coaching must remain distinguishable;
- coaching changes require traceable scope and user control.

#### AI Smart Score Entry

- typed natural-language musical intent;
- spoken intent;
- humming or singing capture;
- instrument-performance capture;
- MIDI-controller capture;
- imported MIDI transformation;
- requests based on mood, style, technique, difficulty, rhythm, form, fretboard region, harmony, and educational purpose;
- conversational edits such as “make bar 3 easier,” “stay in fifth position,” and “rewrite for Drop D”;
- generation of notation, TAB, MIDI, fingering, MSME mapping, lesson metadata, and practice configuration from one canonical musical result;
- “vibe the score” as a supported interaction concept, not a replacement for deterministic contracts.

#### Score control and engraving

- AI edits semantic music, not page coordinates;
- structured operations such as insert note, delete note, change duration, transpose phrase, replace measure, add articulation, set tempo, assign string/fret, simplify rhythm, and adapt tuning;
- musical layer separated from presentation layer;
- deterministic engraving handles spacing, beams, stems, collisions, measures, systems, and pages;
- user-selected edit scope: note, event, measure, phrase, voice, part, or score;
- preview, compare, accept, reject, undo, and regenerate;
- direct manipulation retained as a precision layer;
- user layout choices preserved where semantically compatible;
- system must report when a musical change invalidates a presentation lock rather than silently moving everything.

#### Smart Guitar integration

- play or hum an idea;
- capture the musical event stream;
- formalize it into canonical music;
- generate notation, TAB, and MIDI;
- produce MSME analysis and a lesson configuration;
- practice the generated material;
- receive coaching from performance evidence;
- preserve the fail-safe principle that the physical guitar remains playable when embedded software is unavailable.

### 3.3 Out of scope for this tranche

- production AI model integration;
- prompt engineering for a specific vendor;
- audio-to-score transcription implementation;
- notation engraving engine implementation;
- browser score editor implementation;
- subscription billing;
- licensing marketplace;
- purchased-pack commerce;
- Smart Guitar hardware implementation;
- runtime assessment engine;
- final difficulty-scoring algorithm;
- full MusicXML, Guitar Pro, or ASCII TAB parsers;
- changes to existing candidate-generation semantics;
- selecting a notation-rendering vendor or library without a separate evaluation record.

These are deferred, not rejected.

---

## 4. Settled Design Decisions

### D1 — Learning Object is the primary educational aggregate

A lesson, exercise, etude, reference item, imported song, or generated practice object is represented as a Learning Object. A `.mid` file is never the aggregate root.

### D2 — Canonical music remains authoritative

MIDI, MusicXML, notation, TAB, audio, and PDF do not become competing canonical models. They are imported sources, attached assets, or generated projections.

### D3 — Libraries are separated by authority and provenance

Official curriculum, etudes, references, public-domain songs, purchased packs, and user-imported material must be distinguishable by type, authority, provenance, mutability, and licensing status.

### D4 — Alternate tuning is architectural, even when UI exposure is deferred

The initial curriculum may support standard guitar tuning only. The model and all MSME-facing educational contracts must still carry explicit tuning profiles and must not hard-code standard tuning.

### D5 — MSME produces evidence; pedagogy interprets it

Candidate generation, future selection, phrase planning, difficulty analysis, and coaching are distinct layers. AI may explain MSME evidence but may not replace it with ungrounded spatial claims.

### D6 — Notation is a projection, not the authoring truth

Standard notation is one view of canonical musical structure. TAB and MIDI are parallel views. A score editor must change musical semantics through commands and then request deterministic re-projection.

### D7 — AI Smart Entry operates through typed semantic commands

An AI model must not write directly into domain objects or page coordinates. It proposes versioned semantic commands that pass deterministic validation before application.

### D8 — Edit scope is mandatory

Every generated or transformed edit declares its target scope. Whole-score mutation is never inferred from a local request.

### D9 — Proposed changes are reviewable and reversible

AI-originated operations must support preview, diff, acceptance, rejection, and undo. Accepted commands must be replayable.

### D10 — Musical and presentation layers are separate

Musical edits may cause deterministic reflow. Presentation preferences and locks are stored separately and preserved when compatible. Invalidated locks produce explicit diagnostics.

### D11 — Derived educational claims require evidence

Statements such as “stays in first position,” “contains string skipping,” or “estimated intermediate” must carry references to the musical events, spatial positions, rules, and tuning profile used to derive them.

### D12 — Imported user material is not automatically official curriculum

MSME analysis can enrich imported material, but analysis does not confer editorial authority, instructional quality, licensing status, or inclusion in official learning paths.

### D13 — The platform supports both intent-first and precision editing

Natural language, speech, humming, playing, and imports are high-level entry modes. Direct note editing and advanced engraving controls remain available as lower-level precision tools.

### D14 — This tranche creates contracts and queue authority, not feature theater

No placeholder UI or mock AI endpoint should be added merely to imply implementation. A capability is implemented only when its contract, evidence, tests, and failure behavior exist.

---

## 5. Proposed Package and File Layout

The implementer must first inspect existing package conventions and may adjust exact module names only to conform to repository style. Ownership boundaries and responsibilities below are fixed.

```text
src/master_all_strings/
├── education/
│   ├── __init__.py
│   ├── models.py
│   ├── enums.py
│   ├── validation.py
│   ├── registry.py
│   └── analysis_models.py
├── score_authoring/
│   ├── __init__.py
│   ├── commands.py
│   ├── scopes.py
│   ├── validation.py
│   └── projection_models.py
└── core/
    └── ... existing canonical music and MSME modules

schemas/
├── learning_object_v1.schema.json
├── curriculum_registry_entry_v1.schema.json
├── educational_analysis_v1.schema.json
├── score_edit_command_v1.schema.json
└── score_projection_request_v1.schema.json

resources/
├── curriculum/
│   └── registry.example.json
├── learning_objects/
│   └── examples/
└── tunings/
    └── ... existing or future tuning profiles

docs/
├── architecture/
│   ├── EDUCATIONAL_PLATFORM.md
│   ├── LEARNING_OBJECT_MODEL.md
│   ├── AI_SMART_NOTATION.md
│   └── TUNING_AWARE_EDUCATION.md
├── decisions/
│   ├── ADR-0005-LEARNING-OBJECT-AS-AGGREGATE.md
│   ├── ADR-0006-NOTATION-AS-PROJECTION.md
│   ├── ADR-0007-SEMANTIC-SCORE-EDIT-COMMANDS.md
│   └── ADR-0008-TUNING-AWARE-EDUCATION.md
├── planning/
│   ├── EDUCATIONAL_PLATFORM_CAPABILITY_REGISTER.md
│   ├── EDUCATIONAL_PLATFORM_TRACEABILITY_MATRIX.md
│   └── EDUCATIONAL_PLATFORM_DEVELOPMENT_QUEUE.md
└── handoff/
    └── HANDOFF-2026-07-21-EDUCATIONAL-PLATFORM-SMART-NOTATION.md

tests/
├── education/
│   ├── test_learning_object.py
│   ├── test_curriculum_registry.py
│   ├── test_educational_analysis.py
│   └── test_tuning_compatibility.py
├── score_authoring/
│   ├── test_score_edit_commands.py
│   ├── test_edit_scope.py
│   └── test_projection_contracts.py
├── schemas/
│   └── test_educational_schemas.py
└── fixtures/
    └── education/
```

---

## 6. File-by-File Patch Plan

### 6.1 Architecture and decision documents

#### `docs/architecture/EDUCATIONAL_PLATFORM.md` — create

Define the subsystem purpose, boundaries, authority layers, library taxonomy, principal workflows, and relationship to MSME, AI coaching, notation, imports, and Smart Guitar.

Must include the complete capability map from Section 3.2.

#### `docs/architecture/LEARNING_OBJECT_MODEL.md` — create

Document the aggregate, child records, identity, asset references, provenance, tuning declarations, analysis attachments, assessment attachments, lifecycle, and versioning.

#### `docs/architecture/AI_SMART_NOTATION.md` — create

Define intent-based entry, supported input modes, semantic command boundary, validation, deterministic application, preview/diff/undo behavior, engraving separation, failure handling, and non-goals.

#### `docs/architecture/TUNING_AWARE_EDUCATION.md` — create

Define required tuning, compatible tuning, tuning-independent content, adaptable content, tuning-specific analysis, coaching constraints, and future tuning-verification hooks.

#### `docs/decisions/ADR-0005-LEARNING-OBJECT-AS-AGGREGATE.md` — create

Record D1–D3 and reject file-centric or MIDI-centric alternatives.

#### `docs/decisions/ADR-0006-NOTATION-AS-PROJECTION.md` — create

Record D2, D6, and D10. Explain why standard notation, TAB, and MIDI are peer projections rather than competing models.

#### `docs/decisions/ADR-0007-SEMANTIC-SCORE-EDIT-COMMANDS.md` — create

Record D7–D9 and D13. Define why AI cannot mutate domain state or coordinates directly.

#### `docs/decisions/ADR-0008-TUNING-AWARE-EDUCATION.md` — create

Record D4, D5, and D11. State that standard tuning may be the first exposed profile but cannot be baked into the architecture.

### 6.2 Preservation and planning records

#### `docs/planning/EDUCATIONAL_PLATFORM_CAPABILITY_REGISTER.md` — create

Create one row per preserved capability with:

- capability ID;
- exact capability statement;
- source discussion theme;
- subsystem owner;
- disposition;
- target phase;
- dependencies;
- verification artifact;
- notes.

Allowed dispositions:

```text
ACCEPTED
DEFERRED
REQUIRES_RESEARCH
REJECTED
DUPLICATE
OUT_OF_SCOPE
```

No capability may be removed; superseded entries remain with a cross-reference.

#### `docs/planning/EDUCATIONAL_PLATFORM_TRACEABILITY_MATRIX.md` — create

Map every capability ID to at least one architecture section, ADR, schema field, test, or explicit deferred queue item.

The matrix validator must fail when an accepted capability has no target artifact.

#### `docs/planning/EDUCATIONAL_PLATFORM_DEVELOPMENT_QUEUE.md` — create

Create an ordered backlog with dependencies and exit gates. Use the rollout sequence in Section 11.

### 6.3 Domain contracts

#### `src/master_all_strings/education/enums.py` — create

Define closed enums for:

- `LearningObjectKind`;
- `LibraryAuthority`;
- `ContentProvenanceKind`;
- `AssetKind`;
- `TuningCompatibilityKind`;
- `AnalysisConfidenceBand` if repository conventions permit;
- lifecycle/status values required by v1.

Do not encode a fixed catalog of techniques as an enum unless the ontology is settled. Use versioned identifiers for extensible concepts.

#### `src/master_all_strings/education/models.py` — create

Define immutable v1 models for:

- `LearningObjectId` or validated identifier convention;
- `LearningObjectMetadata`;
- `LearningObjective`;
- `AssetReference`;
- `TuningRequirement`;
- `LearningObject`;
- `PracticeConfiguration` only if it can remain evidence-free and declarative.

Must not embed raw binary assets.

#### `src/master_all_strings/education/analysis_models.py` — create

Define result-only structures for MSME educational analysis:

- source musical object/version;
- instrument profile identifier;
- tuning profile identifier;
- event or phrase references;
- playable-region summary;
- position-shift evidence;
- string-usage evidence;
- highest-position/fret evidence;
- technique findings;
- alternate-fingering findings;
- difficulty finding with method/version and evidence;
- warnings and unsupported-analysis diagnostics.

Do not implement interpretive algorithms in this file.

#### `src/master_all_strings/education/validation.py` — create

Provide deterministic validation for identifiers, required fields, asset combinations, tuning declarations, provenance constraints, and analysis attachment compatibility.

#### `src/master_all_strings/education/registry.py` — create

Provide pure load/validate/index operations for curriculum registry entries. No database, network, billing, or mutable global registry.

### 6.4 Score-authoring contracts

#### `src/master_all_strings/score_authoring/scopes.py` — create

Define explicit edit target scopes and stable references to note/event, measure, phrase/range, voice, part, and score.

#### `src/master_all_strings/score_authoring/commands.py` — create

Define a versioned discriminated command model for semantic operations. Initial command vocabulary should include only operations that can be represented deterministically against the canonical music model.

Candidate v1 commands:

- insert event;
- delete event;
- replace event;
- change duration;
- transpose selection;
- replace measure/range;
- set tempo;
- add/remove articulation or annotation where supported;
- assign or request string/fret constraints;
- simplify rhythm request as a proposal type, not an immediately executable primitive;
- adapt-to-tuning request as a proposal type, not an immediately executable primitive.

Distinguish executable canonical edits from higher-level AI proposals that require planning.

#### `src/master_all_strings/score_authoring/validation.py` — create

Validate command schema, target existence, scope containment, preconditions, version match, and forbidden whole-score escalation.

#### `src/master_all_strings/score_authoring/projection_models.py` — create

Define requests and result metadata for rendering canonical music into notation, TAB, and MIDI. Do not implement rendering.

Include:

- projection kind;
- source version;
- instrument and tuning context where required;
- presentation preferences;
- locks;
- invalidated-lock diagnostics;
- renderer identity/version;
- deterministic result digest or artifact reference.

### 6.5 JSON Schemas

#### `schemas/learning_object_v1.schema.json` — create

Mirror the v1 Learning Object contract.

#### `schemas/curriculum_registry_entry_v1.schema.json` — create

Define registry placement, authority, learning path membership, prerequisites, ordering, publication status, and referenced Learning Object ID.

#### `schemas/educational_analysis_v1.schema.json` — create

Define evidence-bearing analysis output.

#### `schemas/score_edit_command_v1.schema.json` — create

Define the discriminated command envelope, scope, actor/origin, preconditions, and command payload.

#### `schemas/score_projection_request_v1.schema.json` — create

Define projection target and presentation contract.

### 6.6 Fixtures and examples

#### `resources/curriculum/registry.example.json` — create

Include representative entries for:

- beginner first-position exercise;
- picking etude;
- reference scale object;
- public-domain song;
- user-imported song reference that is not publishable curriculum;
- Drop D lesson marked deferred or future-compatible.

#### `resources/learning_objects/examples/*.json` — create

At minimum:

1. standard-tuning beginner lesson with MIDI asset;
2. tuning-independent rhythm exercise;
3. Drop D-specific etude;
4. user-imported MIDI object with generated analysis attachment;
5. notation/TAB/MIDI multi-projection object;
6. AI-generated draft object with provenance and unreviewed status.

### 6.7 Repository integration

#### `docs/architecture/PRODUCT_CHARTER.md` — modify

Add the educational-platform direction without making unfinished features current capabilities.

Recommended principle:

> Master All Strings is a musical knowledge and learning platform. MIDI, notation, TAB, audio, MSME analysis, curriculum, coaching, and device experiences are assets or projections of canonical musical information.

#### `README.md` — modify

Add a concise “planned educational platform” section and links to the new architecture. Keep current implementation status accurate.

#### Existing documentation index — modify or create as appropriate

Ensure the new records are discoverable.

---

## 7. Interfaces

### 7.1 Learning Object interface

Conceptual v1 shape:

```text
LearningObject
├── schema_version
├── learning_object_id
├── revision
├── kind
├── authority
├── provenance
├── metadata
├── objectives[]
├── concept_ids[]
├── asset_references[]
├── tuning_requirement
├── recommended_region
├── analysis_references[]
├── coaching_rule_references[]
├── assessment_reference?
├── practice_configuration?
└── lifecycle_status
```

### 7.2 Educational analysis interface

```text
EducationalAnalysis
├── analysis_id
├── analysis_version
├── source_music_id
├── source_revision
├── instrument_profile_id
├── tuning_profile_id
├── analyzer_id/version
├── playable_regions[]
├── string_usage[]
├── position_shifts[]
├── alternate_fingerings[]
├── technique_findings[]
├── difficulty_finding?
├── evidence[]
├── warnings[]
└── unsupported_findings[]
```

### 7.3 Score-edit proposal and command interfaces

Use two levels:

1. **Intent proposal** — high-level request such as “make measure 3 easier” or “adapt for Drop D.”
2. **Executable command set** — deterministic semantic edits generated from the proposal and validated before application.

```text
ScoreEditProposal
├── proposal_id
├── origin
├── natural_language_intent?
├── target_scope
├── constraints[]
├── source_revision
└── status

ScoreEditCommandSet
├── command_set_id
├── proposal_id?
├── source_revision
├── target_scope
├── preconditions[]
├── commands[]
├── expected_effect_summary
└── validation_result
```

### 7.4 Projection interface

```text
ScoreProjectionRequest
├── source_music_id/revision
├── projection_kind
├── instrument_profile_id?
├── tuning_profile_id?
├── presentation_preferences
├── presentation_locks[]
└── renderer_requirement?
```

The projection result must report preserved and invalidated locks.

---

## 8. Required Utilities

### 8.1 `scripts/validate_educational_schemas.py`

Validate all schema files and every example/fixture against its declared schema.

Exit nonzero on:

- invalid JSON;
- invalid schema;
- fixture/schema mismatch;
- unknown schema version;
- duplicate IDs.

### 8.2 `scripts/check_educational_traceability.py`

Read the capability register and traceability matrix.

Fail when:

- an `ACCEPTED` capability has no target artifact;
- a `DEFERRED` capability has no queue item or explicit research record;
- an artifact references a nonexistent capability ID;
- duplicate active capability IDs exist;
- a capability silently disappears from the matrix.

### 8.3 `scripts/check_learning_object_assets.py`

Validate asset references and cross-field rules without requiring the actual binary asset to be present unless a local path is declared.

Examples:

- notation projection cannot claim authoritative canonical status;
- user-imported content cannot claim official authority;
- tuning-specific content requires a tuning profile;
- generated AI draft content requires provenance and review status;
- purchased content requires a licensing/provenance reference, though commerce is out of scope.

### 8.4 `scripts/check_score_command_examples.py`

Load score command fixtures and ensure:

- explicit scope;
- source revision;
- stable command ordering;
- valid target references;
- no coordinate mutation commands;
- no silent scope escalation;
- proposal-only operations are not marked directly executable.

### 8.5 Optional `scripts/render_development_queue.py`

Generate a human-readable queue summary from a structured queue file only if the repository already accepts generated documentation. Do not introduce generation infrastructure solely for this handoff.

---

## 9. Test Plan

### 9.1 Learning Object model tests

1. A minimal standard-tuning beginner lesson validates.
2. A Learning Object may omit MIDI and contain generated canonical music or another supported asset.
3. MIDI cannot be treated as the Learning Object ID or aggregate root.
4. User-imported content cannot declare official curriculum authority.
5. Public-domain, purchased, official, and user-imported provenance remain distinguishable.
6. Asset references are immutable and ordered deterministically.
7. Duplicate asset IDs fail validation.
8. Unknown schema versions fail explicitly.

### 9.2 Tuning tests

1. Standard tuning lesson validates with explicit profile ID.
2. Drop D lesson validates with a Drop D requirement.
3. Tuning-independent object rejects a contradictory required profile.
4. Tuning-specific object without a profile fails.
5. Adaptable content can list compatible target tunings without claiming adaptation has occurred.
6. Educational analysis attachment must match the instrument and tuning context it declares.
7. Coaching references cannot attach standard-tuning spatial guidance to a Drop D analysis.
8. No validator supplies standard tuning silently when tuning is required.

### 9.3 Educational analysis tests

1. Findings include evidence references.
2. “First position only” cannot be emitted without event/position evidence.
3. Highest-fret finding records instrument and tuning context.
4. Alternate fingering findings preserve all candidates and do not overwrite generation output.
5. Difficulty output records method/version and cannot masquerade as measured fact.
6. Unsupported analysis produces an explicit diagnostic rather than omission.
7. Findings serialize deterministically.

### 9.4 Curriculum registry tests

1. Beginner, etude, reference, public-domain, purchased, and user-library examples index separately.
2. User-imported content is not automatically included in official learning paths.
3. Prerequisite references resolve.
4. Ordering is deterministic.
5. Circular prerequisites fail.
6. Missing Learning Object references fail.
7. A future alternate-tuning lesson can be registered without being marked currently published.

### 9.5 Score command tests

1. Every command has explicit scope.
2. A note-scoped request cannot mutate another measure.
3. A stale source revision fails precondition validation.
4. Command sets replay deterministically.
5. Undo information or inverse-command support is present according to the settled v1 design.
6. Coordinate-level commands are rejected.
7. “Make bar 3 easier” remains a proposal until converted to executable commands.
8. “Rewrite for Drop D” requires a declared source and target tuning profile.
9. Whole-score scope must be explicit.
10. Invalid target references fail without partial application.

### 9.6 Projection contract tests

1. Notation, TAB, and MIDI projections reference the same canonical source revision.
2. Presentation preferences do not alter canonical musical data.
3. Compatible locks are preserved.
4. Invalidated locks are reported.
5. Renderer identity and version are recorded.
6. Same request and source produce a stable projection-request digest.

### 9.7 Traceability tests

1. Every accepted capability in Section 3.2 appears in the capability register.
2. Every accepted capability maps to an artifact or implementation phase.
3. Deferred formats and workflows remain visible in the queue.
4. Alternate tuning appears in architecture, schema, fixtures, tests, and rollout.
5. AI Smart Entry input modes remain separately listed rather than compressed into “AI input.”
6. Direct manipulation and user layout control remain preserved.
7. Smart Guitar capture-to-practice workflow remains a deferred integration item.

### 9.8 Regression tests

- Existing MSME candidate-generation tests remain unchanged and green.
- Existing schema tests remain green.
- New educational modules must maintain repository coverage requirements.
- No new import cycle from core MSME into education or score-authoring packages.

---

## 10. Acceptance Gates

This tranche is complete only when:

1. all documents and ADRs exist and agree;
2. every capability in Section 3.2 has a capability-register entry;
3. every accepted or deferred capability is traceable;
4. all five schemas validate;
5. all example fixtures validate;
6. tuning is explicit in every context where it affects spatial interpretation;
7. semantic command and projection boundaries are documented and tested;
8. no production AI, renderer, or hardware implementation has leaked into scope;
9. existing tests pass;
10. new tests pass;
11. formatting, linting, typing, and schema checks pass;
12. README and Product Charter describe plans without overstating implementation.

---

## 11. Rollout Order

### Phase 0 — Preservation lock

Create:

- capability register;
- traceability matrix;
- this handoff link/index entry.

Gate: every discussed concept is recorded before abstraction or schema design proceeds.

### Phase 1 — Architecture and ADRs

Create the four architecture documents and four ADRs.

Gate: ownership, authority, canonical-model boundary, tuning policy, score-edit boundary, and notation projection are accepted.

### Phase 2 — Learning Object contracts

Implement education enums, models, validation, Learning Object schema, and fixtures.

Gate: official, public-domain, purchased, generated, and user-imported examples validate without conflation.

### Phase 3 — Curriculum registry

Implement registry contract, loader/index utilities, examples, prerequisite validation, and tests.

Gate: library authority and hierarchy are deterministic and user imports remain separate.

### Phase 4 — Tuning-aware educational-analysis contracts

Implement analysis result models, schema, evidence model, tuning compatibility checks, and representative fixtures.

Gate: no educational spatial claim can exist without instrument/tuning context and evidence.

### Phase 5 — Semantic score-authoring contracts

Implement scopes, proposal envelope, executable command set, validation, schema, fixtures, and tests.

Gate: no AI or user command can mutate coordinates or escalate scope silently.

### Phase 6 — Projection contracts

Implement notation/TAB/MIDI projection request and result metadata contracts, including presentation locks and invalidation diagnostics.

Gate: projections cannot become canonical and presentation state cannot alter musical truth.

### Phase 7 — Queue decomposition

Create subsequent dev-ready handoffs in this dependency order:

1. deterministic candidate selection;
2. phrase/chord planning;
3. educational-analysis rules;
4. curriculum registry runtime;
5. import normalization for MIDI;
6. notation-renderer evaluation;
7. deterministic projection adapter;
8. Smart Score Entry proposal planner;
9. AI provider adapter behind the proposal boundary;
10. teacher authoring workflow;
11. user-library workflow;
12. practice metrics and assessment;
13. AI coaching;
14. Smart Guitar capture and embedded integration;
15. MusicXML, Guitar Pro, ASCII TAB, audio transcription, and additional import adapters.

Each later handoff must cite capability IDs and may not close or omit capabilities without changing their disposition in the register.

---

## 12. Development Queue Seed

Use these queue IDs unless an existing repository convention requires another prefix.

| Queue ID | Capability | Dependency | Initial disposition |
| --- | --- | --- | --- |
| EP-001 | Capability register and traceability | none | ready |
| EP-002 | Educational platform architecture and ADRs | EP-001 | ready |
| EP-003 | Learning Object v1 contracts | EP-002 | queued |
| EP-004 | Curriculum registry v1 | EP-003 | queued |
| EP-005 | Tuning-aware educational analysis contracts | EP-003, MSME | queued |
| EP-006 | Semantic score proposal and command contracts | EP-002 | queued |
| EP-007 | Score projection contracts | EP-003, EP-006 | queued |
| EP-008 | Deterministic selection and phrase planning | MSME current foundation | separate handoff required |
| EP-009 | Educational analysis implementation | EP-005, EP-008 | deferred |
| EP-010 | MIDI import normalization | EP-003 | deferred |
| EP-011 | Notation renderer evaluation | EP-007 | research required |
| EP-012 | Notation/TAB/MIDI projection adapter | EP-007, EP-011 | deferred |
| EP-013 | AI Smart Entry proposal planner | EP-006, EP-008 | deferred |
| EP-014 | AI provider adapter | EP-013 | deferred |
| EP-015 | Teacher Studio | EP-004, EP-012, EP-013 | deferred |
| EP-016 | User Library | EP-003, EP-010 | deferred |
| EP-017 | Practice metrics and assessment | EP-003, EP-009 | deferred |
| EP-018 | AI coaching | EP-005, EP-009, EP-017 | deferred |
| EP-019 | Smart Guitar capture-to-practice integration | EP-010, EP-012, EP-018 | deferred |
| EP-020 | Alternate-tuning curriculum packs | EP-004, EP-005, EP-009 | deferred |
| EP-021 | MusicXML adapter | EP-003, EP-007 | deferred |
| EP-022 | Guitar Pro adapter | EP-003, EP-007 | research required |
| EP-023 | ASCII TAB adapter | EP-003, EP-007 | deferred |
| EP-024 | Humming/audio transcription | EP-006, EP-010 | research required |
| EP-025 | Purchased content and licensing integration | EP-003, EP-004 | out of current scope |

---

## 13. Implementation Rules

- Do not reopen settled MSME candidate-generation decisions.
- Do not select an AI or notation vendor in this tranche.
- Do not encode natural-language prompts as domain contracts.
- Do not let AI-generated prose become musical evidence.
- Do not make a generated difficulty rating authoritative without method and evidence.
- Do not infer standard tuning where tuning affects a result.
- Do not conflate imported songs with official curriculum.
- Do not store binary media in immutable domain objects.
- Do not use page coordinates as musical-edit commands.
- Do not allow whole-score mutation without explicit whole-score scope.
- Do not delete capability-register rows when plans change; update disposition and cross-reference.
- Do not claim a roadmap item is implemented because its schema or UI placeholder exists.

---

## 14. Completion Report Format

The implementer must report:

1. files created and modified;
2. capability-register count by disposition;
3. traceability gaps found and resolved;
4. schemas and fixtures validated;
5. test counts and coverage;
6. lint/type/schema command results;
7. any deviations from the file plan;
8. unresolved decisions requiring owner ruling;
9. the exact next queue item authorized;
10. confirmation that no later-phase implementation was started.

---

## 15. Final Product Principle

> Master All Strings is a musical knowledge and learning platform. The learner studies a Learning Object, not a file. Canonical music supplies the truth; MSME supplies instrument-specific evidence; curriculum supplies purpose; notation, TAB, MIDI, and audio supply views and assets; AI supplies controlled assistance and coaching.

The development process must preserve that principle and the full capability inventory before optimizing, simplifying, or sequencing implementation.