# Lesson Assignment Boundary

## Role

`LessonAssignmentV1` is the mandatory application-level entry point for MVP-1 lesson
content. It owns instructional intent and portability. It does **not** own canonical
musical truth.

```text
Local MIDI / future transport
        ↓
LessonAssignmentV1
        ↓
validate / resolve
        ↓
canonical MusicalEvent
        ↓
MSME → selector → temporal projection → renderer
```

## Engine ownership

| Concern | Owner |
| --- | --- |
| Assignment identity, instructional intent, practice instructions, teacher overrides, assessment intent, provenance, routing metadata | Educational Engine (`LessonAssignmentV1`) |
| Canonical musical events, instrument/tuning profiles | Musical Core |
| Possible spatial mappings | MSME (Musical Core) |
| Automatic fingering when no valid override | Deterministic selector (Musical Core; MVP uses enumeration-order scaffold pending DO-004) |
| Playback clock | Transport / runtime |
| Display-ready semantic payloads | Projection |
| Pixels / animation | Renderer (zero authority) |
| Transmission, addressing, auth | Future networking (deferred) |

## Identity model

- `content_id` identifies underlying musical/lesson content.
- `assignment_id` identifies one instructional assignment instance.
- The same content may later carry different tempos, repetitions, fret regions,
  teacher overrides, or assessment settings under distinct assignment IDs.

## Content resolution

Embedded normalized events are **input to canonical resolution**. Once resolved:

```text
LessonAssignmentV1 → canonical MusicalEvent
```

all MSME and projection behavior consumes Musical Core contracts only.

Timing uses integer ticks (`start_tick`, `duration_ticks`) plus
`ticks_per_quarter`. Beat floats are derived views, never a second timing authority.

## Playback policy

Assignment playback may request tempo, start/end ticks, loop, and count-in.
Transport remains authoritative for current playback position.

Tempo precedence:

```text
explicit assignment tempo override
        ↓
source tempo map
```

Tempo changes affect transport timing only; they must not alter MSME candidates or
selected fingering.

## Spatial guidance

Expresses instructional intent, not screen coordinates:

- `instrument_profile_id`
- `fingering_policy_id`
- preferred fret region (soft guidance unless a policy promotes it)
- open-string preference

Forbidden: pixel positions, CSS layout, renderer offsets.

## Teacher overrides

Priority after physical validity:

```text
physical / instrument validity
        ↓
valid teacher override
        ↓
lesson spatial constraints
        ↓
deterministic selector
```

An override does not assert physical validity. MSME/Musical Core verifies the
requested location; invalid overrides fail validation and never silently fall back.

## Provenance

Captures source type, source name (basename only), created-at, and creator
classification. Absolute local file paths must not be required for portable
operation.

## Routing neutrality

`LessonRoutingV1` (`sender_device_id`, `recipient_device_id`, `classroom_id`) may be
absent, null, or populated. Changing only routing metadata must not change:

- resolved canonical events
- MSME candidates
- selected positions
- timing / projection digests defined over musical behavior
- scrolling-fretboard semantic payload

Routing terminates at the lesson/orchestration boundary and must not enter Musical
Core, MSME, selector, transport timing, or projection.

## Downstream authority

The existing authority chain is unchanged after resolution:

```text
MusicalEvent → MSME → candidates → selector → SelectedSpatialEvent
→ temporal projection → renderer
```

The renderer remains a zero-authority consumer of projection data.

## Future transport seam

Networking is deferred. Network readiness is proven by serialize → reload →
identical behavior, and by routing-metadata invariance tests — not by sockets,
discovery, or remote services.
