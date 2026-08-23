# DO-012 Release Report — MVP 2B Synchronized Teaching Timeline

**Status:** IMPLEMENTED — EVIDENCE FROZEN
**Branch:** `cursor/mvp2b-teaching-timeline-90b8`
**PR:** [#20](https://github.com/HanzoRazer/Master-All-Strings/pull/20) → `main` · **Merge:** not authorized · **Tag:** not authorized

```text
mvp1_release_sha   = ac38819b23ed9d85b651755e7612f42d7d528ddc
mvp2a_baseline_sha = 2695993a601f6cc7b526294bdaac50ec5650cc23
do012_base_sha     = 2695993a601f6cc7b526294bdaac50ec5650cc23
do012_product_sha  = bc43db8e608a2217befeb5075c39b1966c1e4fa3
```

`origin/main` was re-verified as `2695993a…` immediately before the branch was
cut, and the branch was created from that SHA directly rather than from a local
ref.

## What was built

One authoritative musical transport now drives every teaching surface through a
reusable, score-agnostic seam:

```text
Python / Musical Core timing
      │  ticks_to_seconds()
      ├── tick↔seconds anchor table ──────────┐
Existing Transport (browser)                  │
      │  subscribe() / snapshot()             │
      ▼                                       │
Teaching Timeline Coordinator ◄───────────────┘
      ├── TeachingTimelineStateV1
      ├── TeachingPlayheadStateV1
      ├── Fretboard active state
      ├── Zone active state
      └── Media follower ── binding · drift · health

Educational ISOLATE_PASSAGE → presentation adapter → Transport.setLoop()
```

`Transport` was not modified. It already exposed `subscribe()` and `snapshot()`,
so the coordinator observes it without any authority moving.

## Two things the handoff assumed that were not true

Both were confirmed by reading the MVP 2A baseline, and both are closed here.

**ISOLATE_PASSAGE never set a loop.** The Dev Order describes the chain
`Educational result → ISOLATE_PASSAGE → practice loop` as existing. It did not.
`practice_actions.js` emitted a status string and `app.js` set a visual focus
range; only the manual loop UI ever called `Transport.setLoop`. DO-012 adds the
presentation adapter that converts the engine's already-authoritative focus
ticks into transport seconds. No Educational code changed, and the golden
three-attempt demo digests are pinned unchanged.

**The browser had no tick authority.** `position_tick` is required by D2 and D3
and produced live, in the browser — but Musical Core owns `ticks_to_seconds`
and the browser only ever consumed precomputed `onset_seconds`. Rather than
write a second canonical tick converter in JavaScript, the mapping is exported
as a table of `(tick, seconds)` anchors at every tempo boundary. Between two
anchors the tempo is constant by construction, so interpolating within the table
*reproduces* the Core mapping instead of approximating it.

To keep the two implementations from drifting apart, both languages read one
generated vector file: Python asserts the vectors still match
`ticks_to_seconds`, and Node asserts the browser reproduces the vectors.

A third, smaller correction: the patch plan assumed static exports only, but
DO-011 had already added `/api/v1/lessons/{key}/media`. Bindings therefore ride
that existing payload, while anchors ride the static projection export — two
sources, joined in presentation, with no new endpoint.

## Anchors do not touch musical identity

`timeline_anchors` is written at the **export wrapper** level, never inside
`FretboardScrollProjectionV1`. Adding a field to the projection dataclass would
have moved `behavior_digest` and broken frozen DO-008 and DO-009 evidence for a
presentation concern carrying no musical content. Tests assert the projection
digest still verifies and that `timeline_anchors` does not appear inside the
projection object.

For all eleven bundled demos, interpolating the exported table at every note
onset equals `ticks_to_seconds`, and every `onset_seconds` round-trips back to
its `onset_tick`.

## Gate results

| Gate | Result |
|---|---|
| Ruff | PASS |
| mypy --strict | PASS (147 source files) |
| pytest (Windows) | 1930 passed, 2 skipped, 2 documented environment exceptions |
| Coverage | 95.43% (floor 95%) |
| Node | 136 passed, 0 failed |
| Governance | PASS (no new engine authority; presentation is not an engine) |
| DO-008 digest gate (Linux) | PASS |
| MVP 1 lineage / no-squash topology (Linux) | PASS |
| Browser smoke | PASS — 0 console errors, 0 failed requests |
| **GitHub Actions (ubuntu-latest)** | **PASS** — run [32610886932](https://github.com/HanzoRazer/Master-All-Strings/actions/runs/32610886932), 36s |

### The two Windows exceptions, characterised and verified on Linux

Neither is a repository defect, and per D18 neither was touched.

1. `test_do008_end_to_end.py::test_checked_in_bundle_correlates_all_authoritative_semantic_events`
   — `core.autocrlf=true` with no `.gitattributes` rewrites the trailing byte of
   `resources/mvp2/do008_bundle/zone_semantics.json`. The worktree file hashes to
   `743977fe…`; the manifest declares `c59e5c83…`. **On a clean WSL Ubuntu clone
   the file contains zero CR bytes and hashes to exactly `c59e5c83…`, and the
   bundle digest gate passes.**

2. `test_mvp1_publication_utils.py::test_mvp1_lineage_script_passes`
   — msys2 Python's cp1252 stdout cannot encode `→`. **On Linux both
   `verify_mvp1_release_lineage.py` and `verify_no_squash_release_topology.py`
   run clean and report PASS.**

### Linux certification: what was and was not run

The DO asked for a clean WSL/Linux full Python gate. The content-addressed
checks — the ones the Windows exceptions are actually about — were run there and
pass. The **full pytest suite was not run in WSL**: that distribution's `python3`
ships without `pip` and without `ensurepip` (Debian moves them into
`python3-venv`/`python3-pip`), and Docker Desktop was not running. Installing
system packages or starting Docker would have modified the developer host, which
was not authorised, so it was not done. The full Linux suite is delegated to
GitHub Actions, which the Dev Order names as authoritative for these gates; its
run is recorded below.

**GitHub Actions run [32610886932](https://github.com/HanzoRazer/Master-All-Strings/actions/runs/32610886932) is green** on `ubuntu-latest` at `8dfc167`: Ruff, strict mypy, and the full `pytest --cov` suite all pass. That independently confirms both Windows failures are environment artifacts rather than repository defects — the same two tests pass there.

### Known CI coverage gap (recorded, not closed)

`.github/workflows/verify.yml` runs Ruff, strict mypy, and `pytest --cov` only.
Node tests and browser smoke are **not** in CI and were certified locally with
the platform recorded. `verify.yml` was not modified: expanding CI is
release-infrastructure scope for a later Dev Order.

## Browser evidence

The golden workflow was driven **entirely through the user interface** in a
headless browser — no page internals were poked. Page globals are not reachable
from the driver's isolated world, so synchronization state is mirrored onto
`document.body` as `data-` attributes, which turned out to be the stronger test:
every action is a real click, select, or slider change.

The full capture is in
[`do012_artifacts/golden_workflow_capture.json`](do012_artifacts/golden_workflow_capture.json),
with 19 screenshots beside it.

| Step | Observed |
|---|---|
| Sync ON | `synced`, drift 0 ms |
| Play | playhead advances, event IDs track, media follows |
| 0.75× | rate applied, followers stay aligned |
| Seek past 3.0 s | media `out_of_binding_range`, **music continues** |
| Manual loop | ticks 640–1280, 2 repetitions |
| Practice attempt | armed, 6 observed notes, action `isolate_passage` |
| Apply action | loop ticks **0–1440** (0.00 s–2.25 s) — the loop the engine implied |
| Loop repeats | 2 repetitions, media `synced` at **−8 ms** |
| Detach | media-only rates restored, including 1.25× |

Zone was captured separately on the DO-008 lesson, because Zone semantics reach
the browser through that stack rather than through the bundled demos. The active
Zone tracks the playhead (`ZONE_1 ZONE_2` → `ZONE_2 ZONE_1` as it advances),
reports the **set** when simultaneous notes occupy different Zones rather than
inventing a dominant one, and honestly reports none during silence. The playhead
carries canonical DO-008 event IDs (`comp:000012`…), not browser-local ones.

## Two defects the browser run found

Neither was reachable from unit tests, and both are worth recording because they
are the reason for running the real thing.

**Media that cannot be seeked was being seeked forever.** The bundled DO-011
demonstration clip reports `seekable=[0,0]` while reporting `buffered=[0,3]` and
`readyState=4`: fully loaded, completely unseekable. The follower measured drift,
issued a hard seek, the element ignored it, and the next frame reached the same
verdict. The settle window bounded that to roughly four attempts per second
rather than sixty — which is why it presented as slow bleed rather than a spin —
but 36 hard seeks accumulated over one run. Checking the element's seekable
ranges before correcting turns this into a single honest `DEGRADED` report: the
same run now issues **one** hard seek, and the media tracks the Educational loop
at −8 ms instead of sitting at zero. Forward playback was never affected, which
is exactly why a cooperative test stub could not have caught it.

**The sync toggle's label was invisible.** The Teaching Media panel is built on
system colors (`Canvas`/`CanvasText`) while the surrounding app sets its own
near-white text, so the new control inherited light-on-light. It now uses the
same basis as the panel it sits in. The wider panel/theme mismatch is
pre-existing DO-011 styling and was left alone.

## The golden asset exercises partial-range synchronization on purpose

`half_steps_one_string` is a 4.5 s lesson; its bundled demonstration clip is
3.0 s. The binding says so honestly:

```text
lesson_anchor_seconds = 0    media_anchor_seconds = 0
lesson_end_seconds    = 3.0  media_end_seconds    = 3.0
```

After 3.0 s the media follower reports `OUT_OF_BINDING_RANGE` while music,
fretboard, Zone, and playhead continue. This is a feature of the evidence, not a
defect: it proves media cannot hold the lesson hostage. A full-range binding
fixture exercises the non-degraded path so the implementation is not tested only
through partial range.

## Non-interference

Musical Core, MSME, Zone semantics, Performance evidence, and Educational output
are all unchanged, with digests pinned in the test suite. DO-011 detached media
behaviour is intact, including the media-only 1.25× step, which is preserved in
`DETACHED` and simply unavailable in `SYNCHRONIZED` — the shared transport's set
is offered instead, so no rate is ever silently approximated.

The suite also walks the import graph of Core, Educational, Performance, and
instruments to prove none of them depends on `presentation`. `media` does depend
on it — it carries the bindings — and that direction is one-way, so there is no
cycle.

`canonical_revision_id` is deliberately absent from every presentation contract,
and a test asserts it stays absent. DO-013 owns revision provenance; a
placeholder here would let presentation state imply an authority it does not
have.

## Reviewer question

> Does one existing musical transport now coordinate the current teaching
> surfaces through a reusable, score-agnostic timeline/playhead seam, without
> introducing a second clock or changing any musical, spatial, performance, or
> educational authority?

Yes.

```text
DO-012 / MVP 2B
STATUS: IMPLEMENTED — EVIDENCE FROZEN

MVP 2
STATUS: IN DEVELOPMENT
```

DO-013 can now branch from a real MVP 2B baseline and add canonical revision
wiring plus synchronized TAB and notation as further followers of
`TeachingPlayheadStateV1`, without inventing temporary infrastructure.
