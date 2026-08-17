# DO-011 Tranche Plan — MVP 2A Lesson Media & Guided Practice Foundation

**Dev Order:** DO-011  
**Milestone:** MVP 2 (tranche A only)  
**Branch:** `cursor/mvp2a-lesson-media-90b8`  
**PR target:** `main`

## Immutable predecessor

```text
mvp1_release_sha = ac38819b23ed9d85b651755e7612f42d7d528ddc
```

## Development baseline

```text
do011_base_sha = 042b5d5b38ca83c72429f7bd865cf87249079200
```

Recorded before any DO-011 modifications.

## Objective

Add a replaceable **Lesson Media / Teaching Aid** presentation seam beside the
frozen MVP 1 learning loop. Media explains; it never owns curriculum, musical
events, Zone semantics, transport, or evaluation.

## Authority boundary

```text
LessonAssignmentV1 (unchanged)  → musical / instructional assignment authority
Media sidecar catalog           → presentation references only
Musical Core / MSME / Zone      → unchanged
Performance / Education         → unchanged
```

## Design rulings (locked)

1. Sidecar media catalog keyed by lesson/content identity — **no** `LessonAssignmentV1` mutation.
2. Cues canonicalize by `(time_seconds, cue_id)`.
3. Unresolved `optional=false` fails catalog validation; runtime/browser soft-fails.
4. Tiny original in-repo demo assets only.
5. Modest Teaching Media panel in `web/mvp1` (no shell rewrite).
6. Evidence freeze + PR only — no MVP 2 tag/release.
7. Docs-only subsystem — no new engine registry row.

## Stages

1. Baseline + architecture docs  
2. Contracts + schemas  
3. Catalog + resolver + validation  
4. Sidecar lesson integration  
5. Localhost media API  
6. Browser media component  
7. Product-shell panel  
8. Golden “Half Steps on One String” teaching aid  
9. Non-interference proof  
10. Browser verification  
11. Full regression  
12. Evidence freeze + PR  

## Non-goals

Recovered corpus migration, avatars, cloud streaming, frame-accurate A/V sync,
DRM, teacher uploads, MVP 2 release declaration.
