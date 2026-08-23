# DO-012 Tranche Plan — MVP 2B Synchronized Teaching Timeline

**Dev Order:** DO-012
**Milestone:** MVP 2 (tranche B)
**Branch:** `cursor/mvp2b-teaching-timeline-90b8`
**PR target:** `main`
**Delivery:** implementation + evidence freeze + feature PR. Merge/tag not authorized.

## Lineage

```text
mvp1_release_sha  = ac38819b23ed9d85b651755e7612f42d7d528ddc
mvp2a_baseline_sha = 2695993a601f6cc7b526294bdaac50ec5650cc23
do012_base_sha     = 2695993a601f6cc7b526294bdaac50ec5650cc23
```

`origin/main` was re-verified as `2695993a…` immediately before branch creation.
The branch was cut from that SHA directly, not from a local ref.

## Objective

One authoritative musical transport driving synchronized presentation state for
teaching media, fretboard activity, Zone highlighting, playhead position,
playback rate, seeking, and practice loops — without a second musical clock and
without changing any musical, spatial, performance, or educational authority.

## Two gaps the survey exposed

The handoff assumed two things the MVP 2A baseline did not actually contain.
Both were confirmed by reading the code at `2695993a…` and both are closed here.

**1. `ISOLATE_PASSAGE` never set a loop.** `web/mvp1/practice_actions.js`
handled `isolate_passage` by emitting a status string; `app.js` set a visual
focus range. Nothing called `Transport.setLoop()` from an Educational action —
only the manual loop UI did. The "Educational result → practice loop" chain the
handoff describes as existing did not exist. DO-012 adds the presentation
adapter that closes it. Educational engine code is unchanged.

**2. The browser had no tick authority.** Python owns `ticks_to_seconds`; the
browser only ever consumed precomputed `onset_seconds` values. `position_tick`
could not be produced live. DO-012 exports a Python-authored tick↔seconds anchor
table and interpolates within it, rather than implementing a second canonical
tick converter in JavaScript.

## Design rulings (locked)

1. `Transport` remains the sole musical transport authority. No new clock.
2. Teaching Timeline state is derived, never owned.
3. `TeachingPlayheadStateV1` is created here, score-agnostic, for DO-013 reuse.
4. Media has two explicit modes: `DETACHED` (MVP 2A behavior) and `SYNCHRONIZED`.
5. Synchronization requires an explicit `MediaTimelineBindingV1`. No inference.
6. V1 mapping is affine 1:1. No time warping.
7. Shared rates are the transport's `{0.5, 0.75, 1, 1.5}`. Media's detached-only
   `1.25` is preserved in `DETACHED` and unavailable in `SYNCHRONIZED`.
8. The existing practice loop stays authoritative; everything follows it.
9. `ISOLATE_PASSAGE` gains a presentation adapter, not an Educational change.
10. Drift is explicit evidence via `SynchronizationHealthV1`.
11. Drift thresholds are declared constants: 40 ms / 150 ms.
12. No `currentTime` thrashing. Bounded correction only.
13. Media failure never stops musical playback.
14. Fretboard and Zone get no independent clocks.
15. Cues seek the shared transport only when explicitly bound.
16. **No canonical revision integration.** `canonical_revision_id` is absent by
    design; that wiring belongs to DO-013.
17. No widget monolith. Components stay separate.
18. Windows EOL/console defects are out of scope.

## Anchor table placement

Two distinct sources, joined in presentation:

```text
musical projection / static export  →  timeline anchors
lesson media sidecar / media API    →  media timeline binding
```

Anchors are derived from canonical musical timing, so they ship with the
projection export. Bindings are media metadata, so they extend the existing
DO-011 `/api/v1/lessons/{key}/media` payload additively. No new endpoint and no
second static synchronization export.

Anchors are added at the **export wrapper** level, not inside
`FretboardScrollProjectionV1`. The projection dataclass and its digest are
untouched, so `behavior_digest`, the DO-008 stack, and the DO-009 alignment
digest are unaffected.

## Cue binding

`MediaCueV1.lesson_time_seconds` is added as an optional presentation binding.
It does not reinterpret the existing field:

```text
time_seconds          = position inside the media asset
lesson_time_seconds?  = explicit shared-transport binding
```

## Golden asset: deliberate partial-range synchronization

`half_steps_one_string` is a 4.5 s lesson. Its bundled demonstration clip
`half-steps-demo-video` is 3.0 s. The binding is honest:

```text
lesson_anchor_seconds = 0
media_anchor_seconds  = 0
lesson_end_seconds    = 3.0
media_end_seconds     = 3.0
```

After 3.0 s the media follower reports `OUT_OF_BINDING_RANGE` while music,
fretboard, Zone, and playhead continue. This is a feature of the evidence, not a
defect: it proves media cannot hold the lesson hostage. A full-range binding
fixture exercises the non-degraded path so the implementation is not tested only
through partial range.

## Stages

1. Baseline + architecture docs
2. Contracts + schemas
3. Timeline mapping utilities
4. Synchronization policy
5. Browser Teaching Timeline coordinator
6. Media follower
7. Shared loop propagation
8. Fretboard / Zone / playhead followers
9. Explicit cue bindings
10. Sync controls + diagnostics
11. Educational isolate integration proof
12. Golden browser proof
13. Full non-interference regression
14. Evidence freeze
15. Publication to PR

## Verification platforms

Windows is the development host; it is **not** certification authority for
content-addressed gates.

| Platform | Role |
|---|---|
| Windows (local) | development; two known environment artifacts, documented below |
| WSL Ubuntu (clean clone) | pre-push Linux certification: full pytest, Ruff, mypy, DO-008 digest |
| GitHub Actions (`verify.yml`, ubuntu-latest) | authoritative Linux certification, recorded by run ID |

### Known Windows environment artifacts (not defects, not fixed here)

Both are characterized, reproduced, and deliberately left untouched per D18.

1. `tests/integrations/test_do008_end_to_end.py::test_checked_in_bundle_correlates_all_authoritative_semantic_events`
   — `core.autocrlf=true` with no `.gitattributes` rewrites the trailing byte of
   `resources/mvp2/do008_bundle/zone_semantics.json` to CRLF. The worktree file
   hashes to `743977fe…`; stripping the single CR yields `c59e5c83…`, exactly
   what `clip.bundle.json` declares. LF checkouts are unaffected.

2. `tests/mvp/test_mvp1_publication_utils.py::test_mvp1_lineage_script_passes`
   — msys2 Python's cp1252 stdout cannot encode `→` in
   `scripts/verify_mvp1_release_lineage.py`. Passes under `PYTHONIOENCODING=utf-8`.

Cross-platform determinism (`.gitattributes`, console encoding) is separate
hygiene work for a later Dev Order.

### Known CI coverage gap (recorded, not closed here)

`.github/workflows/verify.yml` runs Ruff, strict mypy, and `pytest --cov` only.
Node tests and browser smoke are not in CI and are certified locally with the
platform recorded. Expanding CI is release-infrastructure scope; DO-012 does not
modify `verify.yml` (D22).

### Out-of-scope work deliberately kept out

Three hygiene changes were prepared during this tranche and removed from it,
because D21, D22, and the non-goals forbid each: a `.gitattributes` pinning LF
for digest-pinned artifacts, a Node step in `verify.yml`, and an ASCII-arrow fix
in `verify_mvp1_release_lineage.py`. All three are recorded in
`DO012_INTEGRATION_EVIDENCE.json` under `deferred_out_of_scope_work` so a later
hygiene Dev Order can pick them up.

## Non-goals

Canonical revision wiring, TAB, notation, score projection contracts, score
editing, Smart Entry, media authoring, nonlinear time warping, new audio DSP,
`.gitattributes` changes, Windows digest repair, console encoding repair, CI
expansion, MVP 2 release/tag.
