# DO-013 / MVP 2C — Release Report

**Canonical revision wiring + synchronized TAB and standard notation**

| | |
|---|---|
| Branch | `cursor/mvp2c-score-projections-90b8` |
| Draft PR | [#23](https://github.com/HanzoRazer/Master-All-Strings/pull/23) → `main` |
| Status | IMPLEMENTED · BROWSER-PROVEN · CI-CERTIFIED · EVIDENCE-FROZEN |
| Merged | **No** — not authorized |
| MVP 2 tag | **No** — not authorized |

---

## 1. What this tranche establishes

One Core-authored canonical score now drives fretboard, TAB, and standard
notation simultaneously, synchronized through the existing Teaching Timeline and
Transport, without introducing a competing musical, spatial, educational,
revision, or timing authority.

```
             CanonicalScoreRevisionV1
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
       TabProjectionV1     NotationProjectionV1
             │                   │
             └─────────┬─────────┘
                       │
                canonical event ids
                       │
             TeachingPlayheadStateV1
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
      Fretboard       TAB       Notation
```

The load-bearing claim is that the authored lesson produces a **real** canonical
revision — minted by Core's own `CanonicalRevisionService` under
`MANUAL_CONSTRUCTION` provenance — and that both projections cite it. No capture
provenance is fabricated: an authored lesson has no capture behind it, so
`event_provenance` is empty rather than invented.

---

## 2. Identity

| Field | Value |
|---|---|
| `mvp1_release_sha` | `ac38819b23ed9d85b651755e7612f42d7d528ddc` (tag `mvp-1`, unchanged) |
| `mvp2b_baseline_sha` | `8bb4e5938d64802a02117b5de49c294909c09d7e` |
| `do013_base_sha` | `10b706271ddf9ad1cf4d8d4d90cfb9e24927cb6e` (descends from the MVP 2B baseline) |
| `do013_product_sha` | **`59e4ea4f08343faa537c6d9ec612ea9c979f9eb7`** |
| Browser evidence SHA | `511054856bab33485fbf50f43f233ba254f08611` |
| Supplementary evidence SHA | `0bfca41bd85b1057f3d33dce2ca4d20976cfbb00` |

The product SHA is the last commit that changes executable product code.
Evidence-only commits after it do not redefine product identity.

---

## 3. Commit ledger

| SHA | Stage |
|---|---|
| `8acaaf2` | Baseline + score projection boundary |
| `97baa9f` | Meter through lesson resolution |
| `ebf87f7` | Document identity + canonical revision seam |
| `3ea0fe1` | Projection contracts + TAB/notation builders |
| `bb6277b` | Generic dispatcher + deterministic digests |
| `b9f71e6` | Authored provenance + lesson-stamped `created_at` |
| `f40f3b8` | Deterministic static score export |
| `60e2e06` | Synthetic projection edge fixtures |
| `b0c13a5` | Projection schema freeze |
| `201f398` | Schema rejection hardening |
| `cfbe2ca` | Browser TAB renderer |
| `9da844f` | Browser notation renderer |
| `c4d3462` | Score coordinator |
| `28563fb` | Cross-view navigation |
| `ebb84c5` | Selection/activity conflation lock |
| `21ae5c2` | Shell wiring, diagnostics, coexistence |
| `59e4ea4` | Browser-discovered defect corrections — **product candidate** |
| `5110548` | First golden browser evidence capture |
| `0bfca41` | Supplementary DO-013E-normalized evidence |

History was not rewritten, squashed, or repartitioned.

---

## 4. Browser certification

**Platform:** Windows 11 · Chromium 149.0.7827.55 headless · external CDP driver
(not committed, nothing installed).

**Result: 26 / 26 checks passed** — DO-013E's B01–B24 plus two beyond the order's
list (coexistence identity invariance, and lesson-change reload).

| Observation | Result |
|---|---|
| Score status | `ready` |
| Canonical revision | `rev-cc28c4e1b3a1e2ae9d130332` |
| Revision agreement | canonical revision, TAB and notation all cite the same revision |
| TAB digest | `sha256:7c1cf893…` |
| Notation digest | `sha256:935cd730…` |
| Cross-view identity | active id present in `activeEventIds`, `tabActiveEventIds`, `notationActiveEventIds` |
| TAB click-to-seek | PASS |
| Notation click-to-seek | PASS |
| Seek/activity authority | PASS |
| Selection ≠ activity | PASS |
| Rate coexistence (0.75×) | PASS |
| Rate invariance | PASS |
| Loop repetitions | **3** |
| Loop invariance | PASS |
| Zone / one-string / media | PASS |
| Console errors | **0** |
| Failed score-artifact requests | **0** |

Two results deserve emphasis.

**The browser's digests match the Python suite's frozen values exactly.** The
artifact the page loads is demonstrably the artifact Core produced — a
cross-check neither side could make alone.

**Seek does not manufacture activity.** After a seek, the score layer's
`activeEventIds` *equals* the Teaching Playhead's published set, and each
renderer's drawn set is a subset of it. A seek to an event's onset may correctly
cause the playhead to publish that event as active; what would be a violation is
divergence — the score reporting activity nobody published. It does not occur.

### Defects this proof found

The browser stage was not ceremonial. It exposed two real defects, fixed in
`59e4ea4` before evidence was frozen:

1. **Switching lessons left the score panel dead.** `loadSession` took an
   optional demo id and the lesson-change handler did not pass one, so the score
   never reloaded while every other surface did. The id now comes from the
   exported payload, so no call site can omit it.
2. **The score panels rendered light-themed on a dark shell.** `score-view.css`
   was written theme-adaptive; the shell is unconditionally dark. Every user on a
   light-preference OS would have seen the score views pasted on rather than
   integrated.

Neither was reachable by the 328 Node tests: both lived in shell wiring.

---

## 5. Platform evidence — read these separately

Certification is **not** unified on one platform, and this report does not claim
it is.

| Proof | Platform |
|---|---|
| Interactive / browser | Windows 11 + real Chromium via external CDP |
| JavaScript unit | Windows 11 / Node v24.11 — **328 passed, 0 failed** |
| Linux / Python | GitHub Actions `ubuntu-latest` / `verify.yml` |

**Linux Node CI does not exist in this repository.** Recorded as:

> `DEFERRED_CI_GAP` — The current Linux CI workflow does not execute the Node
> suite. DO-013 uses the established Windows Node runtime for JavaScript-unit
> certification.

This is a pre-existing CI limitation, not something DO-013 introduced, and
`verify.yml` was deliberately left unmodified.

**Local WSL is `NOT_CERTIFICATION_CAPABLE`** on this workstation: no network, no
passwordless sudo, an incomplete Python dependency set (`referencing` absent),
and no Node. That is an environment limitation, not a product failure.

---

## 6. Authoritative Linux certification

**GitHub Actions run [`33343196695`](https://github.com/HanzoRazer/Master-All-Strings/actions/runs/33343196695)** on head `0bfca41` — conclusion **success**.

| Gate | Result |
|---|---|
| Ruff | PASS |
| mypy strict | PASS |
| pytest | **2534 passed, 3 skipped, 0 failed** |
| Coverage | **95.34%** (threshold 95.00%) |

Projection schemas, the 29-case rejection matrix, the five synthetic fixtures,
governance, and the DO-008 → DO-012A regression chain are all pytest tests and
are included in that run.

---

## 7. The Windows DO-008 discrepancy — a confirmed platform checkout artifact

Throughout this tranche the Windows checkout reported one failure:
`test_do008_end_to_end.py::test_checked_in_bundle_correlates_all_authoritative_semantic_events`.

**Nothing on Windows was changed, and the Windows condition itself is not
resolved.** What authoritative Linux execution established is narrower and more
useful: DO-008 is healthy, and the Windows discrepancy is isolated to CRLF
transformation at checkout.

The mechanism is confirmed rather than assumed. The Windows working tree's
`resources/mvp2/do008_bundle/zone_semantics.json` carries one CRLF pair where the
committed blob has LF, so its sha256 reads `743977fe…` against the manifest's
pinned `c59e5c83…`. The bytes in git are correct; the bytes on that disk are not
the bytes git stores.

**On Linux CI the same test passes.** The Linux run reports 2534 passed against
Windows' 2533 — the difference is exactly this test. No DO-008 file was modified,
and `.gitattributes` was not touched.

An auditor asking later why the Windows suite still reports 2533 rather than 2534
should read that as the expected, documented state of a Windows checkout under
the current `.gitattributes` configuration — not as an unresolved DO-008 defect,
and not as something DO-013 fixed.

DO-009's frozen digest remains
`sha256:c1249457f3d9c9a26b19fc3f8338c1844bec9c6af08809b059d31b89949175d4`.

---

## 8. Known limitations

These are deliberate MVP 2C boundaries, recorded rather than concealed. The
golden evidence shows them rather than avoiding material that would expose them.

- **`MVP2C_NOTATION_REGISTER_LIMITATION`** — Concert-pitch guitar notes are
  rendered faithfully on a single treble staff. Low-register material therefore
  requires extensive ledger lines; F♯1, the corpus floor, sits ten below the
  staff. Guitar octave-transposing notation and alternate clefs are deferred.
  Captured in `golden_notation_register_limitation.png` using the `open_strings`
  lesson — chosen *because* it exposes the limitation.
- **`MVP2C_NOTATION_ACCIDENTAL_LIMITATION`** — An accidental is drawn for every
  note whose `display_pitch` carries one. Measure-level accidental persistence is
  deferred: carrying an accidental through the bar makes the printed glyph depend
  on neighbouring notes rather than on this note's Core-authored spelling.
- **`MVP2C_UNSUPPORTED_DURATION_PLACEHOLDER`** — A note or derived rest the V1
  grammar cannot spell keeps its exact tick span and gets a neutral marker. No
  nearest-glyph approximation.
- **`MVP2C_NO_TIE_INFERENCE`** — Ties are never inferred. The notation contract
  has no tie representation at all.
- **`MVP2C_VOICE_SPECIFIC_REST_UNAVAILABLE`** — Rests derive only from true
  global silence; per-voice inference needs voice evidence the corpus lacks.
- **`DEFERRED_CI_GAP`** — Linux CI does not run the Node suite.

Physical MIDI and audio verification status is unchanged by this tranche.

---

## 9. Workspace state

The **tracked tree is clean**. The working directory as a whole is not, and this
report does not claim otherwise. Three pre-existing untracked paths unrelated to
DO-013 remain untouched, unstaged, and unmodified:

```
Master-All-Strings.code-workspace
sg-agentd-master (8)/
string_master_v.4.0-master (14)/
```

---

## 10. Reviewer's question

> Is DO-013 / MVP 2C browser-proven, regression-safe, Linux-certified within the
> repository's actual CI capabilities, evidence-frozen, and ready for review
> without creating a competing musical, spatial, educational, revision, or timing
> authority?

**Yes**, with the platform distinctions in §5 read as stated — Linux certifies
Python; Windows certifies JavaScript units and the browser proof.

Merge: **no**. MVP 2 tag: **no**. `mvp-1`: unchanged.

---

## 11. Publication report: not applicable at this lifecycle state

DO-011 and DO-012 each carry a `_PUBLICATION_REPORT.md` alongside their release
report. DO-013 deliberately does not, and the asymmetry is the point.

Those tranches reached a publication lifecycle: they were merged, and their
publication reports record an event that actually happened. DO-013 has not been
authorized to merge. PR #23 remains draft, nothing has reached `main`, and no
MVP 2 tag exists.

Creating a publication report now for visual symmetry would weaken the evidence
model by implying a publication event that has not occurred.

If DO-013 is later authorized and merged, that subsequent tranche should create
`DO013_PUBLICATION_REPORT.md` against the actual merge SHA and the post-merge CI
evidence — the only point at which such a document can say anything true.
