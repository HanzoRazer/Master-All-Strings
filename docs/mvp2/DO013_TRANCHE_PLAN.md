# DO-013 Tranche Plan — MVP 2C Canonical Revision + TAB and Notation

**Dev Order:** DO-013
**Milestone:** MVP 2 (tranche C)
**Branch:** `cursor/mvp2c-score-projections-90b8`
**PR target:** `main`
**Delivery:** implementation + evidence freeze + feature PR. Merge/tag not authorized.

## Lineage

```text
mvp1_release_sha   = ac38819b23ed9d85b651755e7612f42d7d528ddc
mvp2b_baseline_sha = 8bb4e5938d64802a02117b5de49c294909c09d7e
do013_base_sha     = 10b706271ddf9ad1cf4d8d4d90cfb9e24927cb6e
```

The two MVP 2B identities are deliberately distinct. `8bb4e59` is the
authoritative baseline — the closeout commit carrying the complete DO-012A
report and evidence. `10b7062` is the commit immediately after it, which binds
`8bb4e59` as that baseline; a commit cannot name itself.

DO-013 branches from `10b7062` so it inherits both the implementation and the
binding, and `8bb4e59` is verified as its ancestor.

`origin/main` was re-verified as `10b7062…` immediately before branch creation.

## Objective

One authored lesson becomes one resolvable canonical score revision, from which
TAB and standard notation are deterministically projected, exported, and
synchronized with the MVP 2B Teaching Timeline.

## Design rulings (locked)

1. Branch from current `main`; record the MVP 2B baseline separately.
2. Authored lessons never use performance ingestion — no fabricated capture
   provenance.
3. Document identity derives from the lesson's stable `content_id`, not from a
   content digest.
4. No test-only ID authority in production; a real authority does the mapping.
5. The canonical revision is exported durably beside its projections.
6. No general file-backed score repository in this tranche.
7. The exported revision is a serialization of `CanonicalScoreRevisionV1`, not a
   second score model.
8. Core-owned projection contracts live under `core/projections/`, because
   governance assigns `ProjectionRequestV1`/`ProjectionResultV1` to
   `MUSICAL_CORE`.
9. `TabProjectionV1`/`NotationProjectionV1` are typed payloads behind the
   registered envelope; no extra governance rows.
10. Core produces projection semantics; the browser only renders them.
11. `meter_changes` survives `ResolvedLessonV1` (additive).
12. Rests derive from global silence only.
13. Polyphony must not produce false rests.
14. Durations are exact simple values plus a single dot, or unsupported.
15. Single dots are authorized.
16. `display_policy = SHARP_PREFERRED_V1`; display spelling, not canonical.
17. Ties are never inferred.
18. TAB consumes selected spatial evidence only.
19. Notation ignores fingering.
20. The DO-012 playhead is the only timing seam.
21. Static export remains primary delivery.
22. The browser stays dependency-free.
23. Score views are read-only.
24. Rate and loop are presentation state only.
25. Failure degrades softly.
26. Deferred hygiene stays excluded.

## The three identities

The distinction this tranche has to hold:

```text
content_id    what a teacher authored        half_steps_one_string
document_id   the work that lesson denotes   score-half_steps_one_string
revision_id   one state of that work         Core-minted from document + content
```

Editing the notes keeps `document_id` and mints a new `revision_id`. Because
Core's content digest excludes `created_at` and `provenance`, identical musical
content yields an identical `revision_id` on every export, which is what keeps
the exported artifacts byte-stable.

## Baseline facts confirmed before starting

Verified by reading the repository at `10b7062`, not assumed:

* `ResolvedLessonV1` still discards `meter_changes` — ruling 11 is a real gap.
* `ProjectionRequestV1` / `ProjectionResultV1` are registered in
  `governance/engine_architecture_v1.json` with `owning_engine: MUSICAL_CORE`
  but do not exist in code.
* `CanonicalScoreRevisionV1` already carries `events`, `tempo_changes`,
  `meter_changes`, and `ticks_per_quarter`.
* Bundled lessons are **480 PPQ**, not the 960 the vector fixtures use.
* `simultaneous_notes` has genuine simultaneous onsets, and `voice_id` is null
  throughout the corpus — so rest derivation must be interval-based.
* Only `InMemoryCanonicalScoreRepository` exists; there is no persistent adapter,
  which is why ruling 5 exports the artifact instead.

## Stages

1. Baseline + architecture docs
2. Authored lesson document/revision authority
3. Durable canonical revision export
4. Meter preservation through resolution
5. Core generic projection contracts
6. TAB contracts and builder
7. Notation contracts and builder
8. Dispatcher and digests
9. Static score export
10. TAB browser renderer
11. SVG notation renderer
12. Score view and playhead
13. Cross-view navigation
14. Loop/rate/Zone/media coexistence
15. Golden browser proof
16. Non-interference and Linux certification
17. Evidence freeze
18. Feature publication

## Verification platforms

| Platform | Role |
|---|---|
| Windows (local) | development; two known environment artifacts carried forward from MVP 2B |
| WSL Ubuntu (clean clone) | authoritative pre-push Linux certification |
| GitHub Actions (`verify.yml`) | authoritative repository gate |

The two Windows exceptions — the `core.autocrlf` content-digest smudge and the
cp1252 console-encoding failure — remain documented and untouched per ruling 26.

## Non-goals

Persistent score database, file-backed repository, ingestion changes, score
editing, Smart Entry, TAB editing, candidate ranking, voice inference,
per-voice rests, tuplets, double dots, inferred ties, advanced engraving,
MusicXML, frontend packages, CI redesign, Windows EOL fixes, MVP 2 release/tag.
