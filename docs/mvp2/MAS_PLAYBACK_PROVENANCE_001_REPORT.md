# MAS-PLAYBACK-PROVENANCE-001

Received-lesson playback now cites the canonical score revision that the
same preparation already carries. This is a software change on that path
only. It does not repair legacy orchestration provenance, and it does not
certify physical MIDI, speaker output, persistence, remote delivery, or
lesson completion.

## Before and after

A received preparation already contained a Core score revision, and TAB and
notation cited it. The playback plan in that same response had
`canonical_revision_id` null. The browser checked playback identity and
events and did not require the revision to match.

The Stage 9 packet still records that older behavior. Its T1 preparation
has playback citation `null` and digest
`sha256:c0c0ddd11b2d2140462ddecc4e02e6ad33813b80759399fa6f780607d356e4c3`,
while the score revision is `rev-cf73ae5afa337ebe334e924b`. Those bytes are
unchanged. Legacy verification still accepts them. Strict verification
rejects the null citation, which is the expected reading of that packet.

After this order, preparation binds the typed plan before export:

- The original playback digest is verified first. A stale digest is refused
  and is not replaced with a fresh one.
- A null citation becomes the response's score revision, and
  `playback_digest` is recomputed with `compute_playback_plan_digest`.
- A citation that already matches is preserved.
- A different non-null citation is `PreparationFailure`. HTTP returns
  `{"error": "internal server error"}` and no preparation document. Begin
  does not store an attempt.

The fresh T1 preparation cites `rev-cf73ae5afa337ebe334e924b` on both the
score and the playback plan. Its playback digest is
`sha256:dbdb6d0d891bd71e56ce826794c21887cf66a279fbf78048c166337efc6427e5`.
Begin's embedded preparation carries that same citation.

## What changed

```text
branch         agent/mas-playback-provenance-001
base           67e909bd1d21fa9546641f13a807539273b1af11
tested source  76f033a2e7660fb187225136ee3a5d5b1a88c1c6
tested tree    f7e53f1e17911d9ef8c5894077fc64ad6d6c8cb0
```

The tested tree was clean. `76f033a` contains the binding, the browser
check, and strict evidence mode. The fresh packet, this report, the tranche
note, and the assertion that reloads the packet come after that revision.

Production edits are only:

- `src/master_all_strings/mvp/local_practice_preparation.py`
- `web/mvp1/lesson_delivery_validation.js`

`orchestrator.py`, playback models, serializers, schemas, and the legacy
export path are unchanged. The global playback contract remains nullable.
The received preparation imposes the equality.

## Environment and gates

| Runtime | Version |
| --- | --- |
| Python | 3.12.3 locally; CI uses 3.11 |
| Node | v22.23.4 |
| Chrome | 148.0.7778.96 |
| OS | Linux |
| Witness clock | 7:45:24 PM CDT on October 27, 2026 |

| Gate | Result |
| --- | --- |
| `ruff check src tests` | PASS |
| `ruff` on `scripts/verify_do016_integration_evidence.py` | PASS |
| `mypy` | PASS, 173 source files |
| `pytest --cov --cov-report=term-missing` | 3554 passed, 3 skipped, 95.34% in 87.42s on `76f033a` |
| `npm test` in `web/mvp1` | 591 passed, 0 failed |
| Stage 6 witness | PASS, 0 failures |
| Stage 8 witness | PASS, 0 failures; begin 5, message 8, finish 3, cancel 2 |
| Integration witness | PASS, 0 failures |
| Strict verifier on the fresh packet | PASS |
| Legacy verifier on the Stage 9 packet | PASS |
| Strict verifier on the Stage 9 packet | FAIL, null playback citation |
| `verify_do015_certification.py` | OK (9 of 9) |
| `verify_do015_publication.py` | OK (8 of 8) |
| `build_do015_certification_evidence.py --check` | OK |
| `check_in_flight.py` | OK (1 row, 0 notes) |
| DO-015 certification capture | exit 0, `CLOSED`, 3 attempts |

The assertion that reloads the committed provenance packet passed after that
suite. It does not change the drivers the witness executed.

Restart epochs on one origin: A pid 7018, B pid 7373, C pid 7403, each with
`delivery_count_at_ready` 0. Stage 8's unknown-attempt finish remains
simulated. The integration 404s come from the restarted process.

The DO-015 capture rewrote `docs/mvp2/do015_artifacts/browser_smoke_summary.json`
and that file was restored. Its sha256 is
`11af5e8656b87785d152735777702b9a025fd0d5f06c315a9b52b46cd38e42db`.
The other frozen DO-015 files were unchanged:

| File | sha256 |
| --- | --- |
| `certification_scenarios.json` | `e8543ac32ac131c98e02dac418bbaf818ccb82f80a3fc8f37d543937f0ec75c0` |
| `certified_session.json` | `8dd997eb492a992347d627509b81b39793ca045a505b4b7494b4c8b0b95315fe` |
| `ci_seal.json` | `355d1e3f38cf2f3b0babdab1a706a377758c78a14427d33390626685d7397d19` |

## Commands

```bash
python scripts/smoke_do016_integration.py /tmp/mas-playback-provenance-run \
  --chrome-executable /usr/local/bin/google-chrome \
  --puppeteer-module /tmp/inbox-smoke/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js
python scripts/verify_do016_integration_evidence.py \
  docs/mvp2/do016_playback_provenance_artifacts/evidence.json \
  --root . --require-bound-playback
python scripts/verify_do016_integration_evidence.py \
  docs/mvp2/do016_integration_artifacts/evidence.json --root .
python scripts/smoke_do016_received_practice.py /tmp/mas-playback-s06
python scripts/smoke_do016_received_attempt.py /tmp/mas-playback-s08 \
  --chrome-executable /usr/local/bin/google-chrome \
  --puppeteer-module /tmp/inbox-smoke/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js
```

## Limits that remain

- Legacy and demo playback plans can still omit `canonical_revision_id`.
  This order does not change `orchestrator.py`.
- An unconfirmed begin is still not repeated.
- Deliveries, choices, and attempts still die with the process.
- One evaluation is not mastery or lesson completion.
- MIDI in the witness was injected. Physical input and speaker output stay
  unverified.
- Windows checkout line endings are a separate maintenance order. Nothing
  here normalizes files or relaxes a gate.
