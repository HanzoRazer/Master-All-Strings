# MAS-BEGIN-RECOVERY-001

A lost Begin can now be resolved explicitly. One browser-generated key
creates at most one attempt. Recovery closes that attempt, or records that
this process never created one. It does not start playback, capture notes,
evaluate, or replay MIDI.

This is not a DO-016 publication and not a hardware certification.

## Contract

The four Stage 7 routes and `ReceivedLessonAttemptV1` 1.0.0 are unchanged.
The received-lesson page uses two new routes:

- `POST /api/education/lesson-practice-begin-requests`
- `POST /api/education/lesson-practice-begin-recoveries`

The key is a lowercase hyphenated UUID version 4. Uppercase and other
forms are `400` with no rewrite and no reservation. The nested Begin body
keeps the five existing fields exactly.

The same key and the same payload prepare once. A repeat after success is
`200` with the stored `STARTED` wrapper. A different delivery, digest,
device, or capture time is `409 begin_request_conflict` whether or not the
key is already sealed. A matching Begin after the key is sealed is
`409 begin_request_closed`.

Recovery before the request arrives stores a tombstone and returns
`200 NO_ATTEMPT`. Recovery while preparation is in progress returns
`202 PENDING`; the owner then cancels the attempt and does not publish
`STARTED`. Recovery of a stored open attempt returns `200 INTERRUPTED`
with the existing interrupted document and no evaluation. A failed cancel
stays unresolved so a later Resolve can finish it. A failure before insert
returns the existing public status and seals `NO_ATTEMPT`.

The page offers **Resolve start** after a lost, unreadable, `5xx`, or
`PENDING` response. Start stays disabled until `NO_ATTEMPT` or
`INTERRUPTED`. A definitive pre-insert refusal, such as an unknown choice,
clears the key without recovery.

## What was tested

```text
branch         agent/mas-begin-recovery-001
base           89626a4f040d1057fbb2b42e4465511977dfe15f
tested source  5381c4c8c56b31777d3f8f5932555b6230f63cd8
tested tree    640ecbdcf97a250b1c66e028ef3ccd6a01191930
```

The browser witnesses ran on that clean source. A later test-only commit
loads the schema fixtures without the `tests` package name. It does not
change the gateway, the page, or the witness.

| Runtime | Version |
| --- | --- |
| Python | 3.12.3 locally; CI uses 3.11 |
| Node | v22.23.4 |
| Chrome | 148.0.7778.96 |
| OS | Linux |

| Gate | Result |
| --- | --- |
| `ruff check src tests` and the new scripts | PASS |
| `mypy` | PASS, 175 source files |
| `pytest --cov --cov-report=term-missing` | 3580 passed, 3 skipped, 95.11% in 88.39s |
| `npm test` in `web/mvp1` | 596 passed, 0 failed |
| Stage 6 witness | PASS, 0 failures |
| Stage 8 witness | PASS, 0 failures; begin 6, message 8, finish 3, cancel 2 |
| Integration witness | PASS, 0 failures |
| Begin-recovery witness | PASS, 0 failures |
| Strict playback-provenance verifier | PASS |
| Legacy Stage 9 verifier | PASS |
| Fresh integration packet, strict mode | PASS |
| `verify_do015_certification.py` | OK |
| `verify_do015_publication.py` | OK |
| `build_do015_certification_evidence.py --check` | OK |
| DO-015 certification capture | exit 0, `CLOSED`, 3 attempts |

The begin-recovery packet records:

- W1 forwarded a live `201 STARTED` and then interrupted attempt `a35b1f7d-89e8-47c5-be9d-908888be6160`.
- W2 recovery returned `NO_ATTEMPT` before that Begin was released.
- W3 recovery returned `PENDING` while preparation was blocked.
- W4 repeated the stored `INTERRUPTED` document for attempt `ef08f117-3134-4366-9f3f-b9f315db2f2d`.
- W5 restarted from pid 12437 to pid 12611 and the new process refused the delayed Begin with `begin_request_closed`.

Frozen `browser_smoke_summary.json` remains
`11af5e8656b87785d152735777702b9a025fd0d5f06c315a9b52b46cd38e42db`.
The Stage 9 packet and the playback-provenance packet were not rewritten.

## Commands

```bash
python scripts/smoke_do016_begin_recovery.py /tmp/mas-begin-final \
  --chrome-executable /usr/local/bin/google-chrome \
  --puppeteer-module /tmp/inbox-smoke/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js
python scripts/verify_do016_begin_recovery_evidence.py \
  docs/mvp2/do016_begin_recovery_artifacts/evidence.json --root .
```

## Limits that remain

Unkeyed Begin callers can still leave an attempt when the response is lost.
Closing the tab can drop the key before the best-effort recovery is known
to have succeeded. Keys and tombstones last only as long as the server
process. A restart therefore answers `NO_ATTEMPT` even if an older process
had created an attempt. Physical MIDI and speaker output are not certified.
Nothing here adds persistence, remote delivery, mastery, or lesson completion.
