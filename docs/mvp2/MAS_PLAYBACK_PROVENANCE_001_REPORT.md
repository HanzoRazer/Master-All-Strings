# MAS-PLAYBACK-PROVENANCE-001

Received-lesson playback cites the Core score revision in its preparation.
Before binding, the producer also verifies that the playback content
corresponds to that score's events at the plan's effective tempo. The browser
requires matching citations before mounting reference practice or an attempt.

Software acceptance does not certify physical MIDI, speaker output,
persistence, remote delivery, mastery, or lesson completion.

## Contract and compatibility

The global playback schema is unchanged: `canonical_revision_id` remains
optional for legacy standalone documents. A received preparation requires a
nonblank string exactly equal to `score.canonical_revision.revision_id`.
The expected revision comes from the server's captured preparation, never
query parameters or local storage. No spelling/whitespace normalization occurs.

A fresh Begin may return a different, internally consistent revision for the
same pinned lesson. This remains supported. A preparation whose playback
and score cite different revisions is refused. There is no legacy exemption
inside the received-preparation gate.

The historical Stage 9 packet at `docs/mvp2/do016_integration_artifacts/`
is unchanged. It records the older null citation; legacy verification accepts
it and strict verification rejects it. The current provenance packet under
`do016_playback_provenance_artifacts/` is a fresh recording of the fixes.

## Production behavior and review findings

Only these production files change:

- `src/master_all_strings/mvp/local_practice_preparation.py`
- `web/mvp1/lesson_delivery_validation.js`

Preparation checks the original playback digest before binding. A stale digest
fails; recomputation cannot repair it. A null citation is filled from the
Core revision already in the response and the digest is recomputed. A
matching citation is preserved. A conflicting citation is refused.

The review reproduced an additional defect on `67455a5`: changing pitch,
velocity, cents offset, onset, release, ticks per quarter, total ticks, or total
seconds and rehashing the plan still allowed it to acquire the score's citation.
Eight regression cases now reject that drift.

The fix reuses the existing playback builder with the score's canonical events
and tick basis plus the plan's effective tempo map. Events, timeline, and
duration must match that authoritative derivation. Teacher tempo overrides
remain playback instructions; the authored score tempo is not substituted
for the effective map. No second timing algorithm is introduced.

Internal failures remain sanitized HTTP 500 responses with no partial
PREPARED document. Conflicting citations log expected/actual opaque revision
IDs server-side using repr formatting. Public errors disclose neither ID.

Browser validation already covered missing, null, blank, wrong-type, and
different citations. Invalid reference preparation now also tells the person
to refresh the lesson or reopen it from the inbox. New page integration tests
prove an inconsistent preparation mounts no runtime, refresh recovers, and
an inconsistent Begin is cancelled without MIDI capture or an attempt mount.
Existing positive tests preserve coherent fresh Begin revisions.

The expanded Stage 8 browser driver exercises the same reference and Begin
rejections using explicitly labeled mutations of live responses. Stage 6 now
reads the same browser/module environment settings as the other witnesses,
retaining its original Linux defaults. These are test-harness changes beyond
the original PR file list, authorized by the request for review fixes.

`orchestrator.py`, schemas, legacy exports, dependencies, and musical,
transport, and audio algorithms are unchanged.

## Tested identities and environment

| Item | Value |
| --- | --- |
| Branch | `agent/mas-playback-provenance-001` |
| Base | `67e909bd1d21fa9546641f13a807539273b1af11` |
| Reviewed head before fixes | `67455a5b3c755349cec2a0ddad5adf400994b9a5` |
| Fresh integration tested source | `ddb79a5047f4db7d63d01121b88cb9ee09ed5634` |
| Fresh integration tested tree | `6d53cc13c1c463edf4c107f2f0342d23b6026395` |
| Python | 3.11.17 |
| Node | v24.22.1 |
| Browser | Chrome Headless Shell 156.0.8078.73 |
| Platform | Linux |

The integration ran from a clean tree. Later commits change only documentation,
evidence, and the register. The original witness at `76f033a` is not cited
as verification of these review fixes.

Full Chrome could not create its process-singleton socket in this environment.
Chrome Headless Shell launched with the checked-in arguments. No driver source
was rewritten in scratch for these runs.

## Verification

| Gate | Result |
| --- | --- |
| Ruff on src/tests and verifier | PASS |
| mypy | PASS, 173 source files |
| Python 3.11 pytest with coverage | 3563 passed, 3 skipped, 95.35% |
| Frontend npm test | 593 passed, 0 failed |
| Stage 6 browser witness | PASS, 0 failures |
| Expanded Stage 8 browser witness | PASS, 0 failures |
| Fresh integration witness | PASS, 0 failures |
| Strict verifier, fresh packet | PASS |
| Legacy verifier, historical Stage 9 packet | PASS |
| DO-015 certification verifier | OK, 9 of 9 |
| DO-015 publication verifier | OK, 8 of 8 |
| DO-015 evidence generator --check | OK |
| DO-015 certification capture | CLOSED, 3 attempts |
| In-flight register | OK; remote PR reconciliation independently checked |

The register CLI noted `gh` was unavailable. GitHub plugin data independently
returned only PR #57 on this branch; feeding that snapshot and the actual
remote branches into its reconciliation function produced no failures/notes.

Stage 8 records Begin 6, message 8, Finish 3, Cancel 3, guided 0,
performance 0. Its revision mismatches and unknown-attempt 404 are simulated.
For the mismatch cases, requests reach the live server and only the returned
citation is mutated; an unusable Begin is cancelled against its stored attempt.
They do not claim an actual server lesson changed.

The integration witness performs real restarts: epochs A/B/C have PIDs
9, 155, and 199 on one localhost origin. Lost-Finish retry still returns the
complete stored result without another Begin or append. The retained strict
verifier checks citations/digests; producer consistency regressions check
semantic correspondence before binding.

The DO-015 capture rewrote its known generated smoke summary. Its original
bytes were restored immediately afterward; frozen DO-015 and historical Stage 9
evidence are unchanged. Frozen smoke-summary SHA-256 remains
`11af5e8656b87785d152735777702b9a025fd0d5f06c315a9b52b46cd38e42db`.

## Reproduction

Configure `DO016_CHROME_EXECUTABLE` and `DO016_PUPPETEER_MODULE` to an
installed Chrome/Headless Shell executable and Puppeteer module respectively.
Stage 6 reads these variables; the other drivers accept them or matching flags.

```bash
python scripts/smoke_do016_received_practice.py /tmp/mas-playback-s06
python scripts/smoke_do016_received_attempt.py /tmp/mas-playback-s08
python scripts/smoke_do016_integration.py /tmp/mas-playback-provenance-run
python scripts/verify_do016_integration_evidence.py \
  docs/mvp2/do016_playback_provenance_artifacts/evidence.json \
  --root . --require-bound-playback
python scripts/verify_do016_integration_evidence.py \
  docs/mvp2/do016_integration_artifacts/evidence.json --root .
```

Exact integration paths and versions are in the retained packet. The Stage 8
review summary is retained alongside it. Hosted CI status on the final head
is recorded in the PR body after the push.

## Limits

Legacy/demo playback remains nullable. Lost Begin remains unrecoverable.
Deliveries, choices, and attempts die with the process. Injected MIDI and
headless scheduling do not certify hardware. Windows line-ending policy is
unchanged. One evaluated attempt does not establish mastery or completion.
