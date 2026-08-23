# DO-012A Publication Report — MVP 2B Closeout

**Status:** PUBLISHED TO MAIN — BASELINE FROZEN
**Tag:** none created, and none authorized.

```text
mvp1_release_sha     = ac38819b23ed9d85b651755e7612f42d7d528ddc
do012_base_sha       = 2695993a601f6cc7b526294bdaac50ec5650cc23
do012_merge_sha      = a4206873210031ba9947cacf9f9f6e1be9f1eb26   (PR #20, squash)
alignment_head_sha   = 8f9ecbaf8324c5ba5cd5b9fc4e2331024025f204   (PR #21 final head)
alignment_merge_sha  = 8402058ceeefec2ddd60faa682b2bd8ce5531731   (PR #21, merge commit)
hardening_merge_sha  = 7e03f20d97283495459d6912d303559b000f079f   (PR #22, merge commit)
post_merge_main_sha  = 7e03f20d97283495459d6912d303559b000f079f
```

## How MVP 2B arrived

Two pull requests, deliberately kept distinguishable.

**PR #20** landed the DO-012 behaviour: the Teaching Timeline coordinator over
the existing `Transport`, Python-authored tick anchors, synchronized and
detached Lesson Media, the fretboard and Zone followers, the generic playhead,
and the `ISOLATE_PASSAGE` presentation adapter. It was squash-merged by the
repository owner as `a420687`.

**PR #21** is the alignment tranche. It did not add teaching capability. It
reconciled what was delivered with what DO-012 actually names, filled the
evidence the order requires, corrected the Zone readout, proved the
≥3-repetition requirement on a lesson whose policy permits it, and removed three
hygiene changes that had shipped in spirit but are explicitly forbidden. It was
merged as a **two-parent merge commit**, `8402058`, so both lineages remain
separately inspectable.

PR #20's squash is historical topology. D13 applies from PR #21 forward and was
not applied retroactively.

## Review result

Line-by-line across all changed files.

```text
blockers                        0
security findings unresolved    0
authority violations unresolved 0
```

| Classification | Finding | Resolution |
|---|---|---|
| DOC_ONLY | `timeline.py` documented `seconds_to_tick_from_anchors` as "the inverse of `seconds_at_tick`" — a name the same PR removed | fixed |
| DOC_ONLY | `teaching-timeline.js` carried the seven-line `sequence` explanation duplicated verbatim in the constructor and `clearLesson` | fixed |
| EFFICIENCY | `renderer.activeZones()` is evaluated twice per publish, by the Zone follower and the diagnostics mirror | recorded, deferred |

The efficiency observation is on a per-frame path, which is why it was looked at
twice. It iterates at most a few dozen notes and both callers read the same
authoritative source; changing a hot path inside an alignment tranche is a worse
trade than leaving it.

## What alignment actually changed

**Named surface.** The order names its contract surface, so equivalent-but-
different names were not good enough:

```text
seconds_at_tick        -> tick_to_seconds_from_anchors
tick_at_seconds        -> seconds_to_tick_from_anchors
_require_anchor_table  -> validate_timeline_anchors   (now public)
health_*.json          -> sync_health_*.json
```

**Evidence.** `sync_health_samples` and `do009_digest` were absent entirely. The
first now carries states captured from the golden run covering `synced`,
`drifting`, `degraded`, `out_of_binding_range`, and `detached`. The second is
verified by showing none of its inputs moved: `resources/performance`, the
performance package, and `DO009_INTEGRATION_EVIDENCE.json` are byte-identical to
the DO-012 base.

**Zone readout.** Now `Zone: ZONE_2, ZONE_1 · Anchor: 5-11, 0-6`. The axis is
copied from the Zone artifact, never derived; no theory is computed in the
browser. Simultaneous notes in different Zones produce a deterministic set, not
an invented dominant Zone.

**Repetitions.** `half_steps_one_string` declares `target_repetitions = 2` in its
own practice policy and correctly stops there. The ≥3 proof therefore runs on
`ascending_scale`, whose policy declares no target: 1 → 2 → 3 → 4 observed with
the loop bounds fixed at ticks 800–1600 throughout. The golden lesson's policy
was not touched — that is lesson-content authority, not presentation.

**A mislabelled timing vector.** Promoting the vector generator into
`scripts/build_interpolation_vectors.py` exposed a defect that had passed every
test: the `half_steps_one_string` case was a relabelled copy of
`constant_120bpm` at 960 PPQ / 8640 ticks, while the lesson it named exports 480
PPQ / 2880 ticks. Internally consistent, and describing a tick domain the browser
never sees. The generator now derives that case from the demo library, and a
negative regression builds the mislabelled shape and asserts the generator
rejects it.

## Mechanical guards added

`scripts/verify_do012a_publication.py` turns the closeout from a set of claims
into something re-runnable:

```text
mvp-1 unchanged
DO-012 base ancestry
deferred hygiene absent from the alignment delta
no presentation contract declares canonical_revision_id
named timeline utilities importable
evidence pack fields present
baseline identities internally consistent
```

It is deliberately narrow — identity, scope, and evidence completeness. The
musical, spatial, performance, and educational authorities have their own suites,
and a second opinion about domain truth would be worse than none.

Its classification logic takes the change set as an argument rather than
computing it, so the tests feed it synthetic deltas: each deferred path alone,
several together, and near-miss names like `docs/.gitattributes.md` that must
*not* trip it. A guard that can only run against one ephemeral branch is a guard
nobody can prove works.

## Deferred, not forgotten

Three changes remain out of scope and out of the tree:

| Change | Would fix | Deferred by |
|---|---|---|
| `.gitattributes` pinning LF for digest-pinned artifacts | the Windows CRLF content-digest exception | D21, non-goals |
| A Node step in `verify.yml` | the browser half of the cross-language vector contract going unenforced in CI | D22, non-goals |
| ASCII arrows in `verify_mvp1_release_lineage.py` | the cp1252 console-encoding exception | D21, non-goals |

Each is defensible engineering. None belongs in a tranche whose risk section
warns specifically against unrelated hygiene riding along with timing work. They
are recorded in `DO012_INTEGRATION_EVIDENCE.json` under
`deferred_out_of_scope_work`, and the forbidden-file guard now fails if any of
them returns.

## Certification

| Gate | Result |
|---|---|
| Linux (clean WSL clone) | **1980 passed, 0 failed**, coverage 95.44% |
| Windows | 1978 passed, 2 documented environment exceptions |
| Ruff | PASS |
| mypy --strict | PASS (147 source files) |
| Node | 146 passed, 0 failed |
| Browser smoke (pre-merge) | 0 console errors, 0 failed requests |
| GitHub CI | [32653809950](https://github.com/HanzoRazer/Master-All-Strings/actions/runs/32653809950) green on `8f9ecba` |
| Publication verifier | PASS |

The two Windows exceptions are the documented `core.autocrlf` content-digest
smudge and the cp1252 console-encoding failure. Both pass on Linux; neither was
repaired here.

### Post-merge verification on `main`

```text
merge commit 8402058 has 2 parents
  a420687  DO-012 behaviour (PR #20)
  8f9ecba  DO-012A alignment (PR #21)
mvp-1 ac38819 reachable
publication verifier PASS
pytest 1978 passed / 2 documented exceptions
node 146 passed
browser smoke 0 console errors, 0 failed requests
```

The post-merge browser run exercised the full learner workflow on `main`: load,
Sync ON, play, 0.75×, seek, past-clip range, loop, one-string view, Zone readout,
practice attempt, `ISOLATE_PASSAGE` producing loop ticks 0–1440 with the media
following at `synced`, and detach restoring MVP 2A behaviour.

Its screenshots were **not** committed. The post-merge closeout is restricted to
three documentation paths, and widening that exception to carry images would
have defeated the point of restricting it.

## Baseline

```text
DO-012 / MVP 2B
STATUS: PUBLISHED TO MAIN — BASELINE FROZEN

DO-013 / MVP 2C
STATUS: READY TO BEGIN
```

```text
mvp2b_baseline_sha = 2c72307e86d5ab03dfe8888b6be267d2e27540b1
```

That is the closeout commit — the point at which the implementation and the
evidence describing it are both complete. DO-013 branches from it, not from
either feature head.

The field is bound by the commit immediately following, because a commit cannot
contain its own hash. The two differ only by that field, so branching from
either inherits the same implementation and the same evidence.

No `mvp-2`, `mvp-2b`, or `v2.0.0` tag was created.

---

## Conformance hardening (PR #22)

Auditing the published DO-012A against the full Dev Order text found four gaps.
They were closed in a corrective verification PR — verifier and tests only —
merged as a two-parent merge commit `7e03f20`.

| Gap | Closed by |
|---|---|
| Verifier check 7, `sync_health` fixture naming, was never implemented | `verify_fixture_naming()` |
| The `mvp-1` tag check had no negative test | moved-SHA and missing-tag cases |
| `half_steps_one_string.target_repetitions == 2` rested in prose | `test_lesson_policy_invariant_do012a.py` |
| Zone present with no declared tritone axis was untested | `zoneReadoutText()` regression suite |
| The live-delta test passed on an empty comparison | closure invariant over the published range |

The lesson-policy gap is the one that mattered most. Raising the golden lesson's
repetition cap so it could demonstrate three passes would have been **invisible
in the evidence** — the proof would have passed, on the golden lesson, with a
screenshot to match. What it would actually have proved is that presentation may
edit lesson content when the content is inconvenient. That invariant is now
mechanical.

One product file changed, with no behaviour change: `renderActiveZones()` lived
in `app.js`, which is not importable without a DOM, so the D10 rule had no
reachable seam. The formatting moved to `renderer.js` as a pure
`zoneReadoutText()`. Browser smoke produces the same readout before and after —
`Zone: ZONE_2, ZONE_1 · Anchor: 5-11, 0-6`.

The closure test was wrong twice before it was right, which is worth recording.
Comparing `origin/main` to `HEAD` passed on an empty comparison once published —
true for the wrong reason. Asserting that emptiness instead failed on every
feature branch, where a delta is exactly what should exist. The durable property
is about the published *range*: everything between the DO-012 base and the
recorded baseline must be free of deferred hygiene, which holds from wherever it
is evaluated.

### Hardened certification

| Gate | Result |
|---|---|
| Linux (clean WSL clone, on `main`) | **2007 passed, 0 failed**, coverage 95.44% |
| Windows | 2005 passed, 2 documented environment exceptions |
| Node | 154 passed (was 146) |
| Browser smoke | 0 console errors, 0 failed requests |
| GitHub CI | [32671181416](https://github.com/HanzoRazer/Master-All-Strings/actions/runs/32671181416) green |
| Publication verifier | PASS — now 8 of 8 checks |

### Baseline supersession

The pre-hardening baseline `2c72307` is **superseded**. Exactly one baseline is
authoritative going forward, recorded as `mvp2b_baseline_sha`, and DO-013
branches from the published `main` tip — not from `main~1`, and not from either
feature head.
