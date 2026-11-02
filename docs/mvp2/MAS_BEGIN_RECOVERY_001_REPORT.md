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

The original browser witnesses ran on that clean source on Linux. A later
test-only commit loads the schema fixtures without the `tests` package name.
The table below is that run. The review fixes and the rerun begin-recovery
witness come after it, under "Review fixes" and "Begin-recovery witness,
rerun".

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

The begin-recovery packet from that run was replaced by the rerun below.

Frozen `browser_smoke_summary.json` remains
`11af5e8656b87785d152735777702b9a025fd0d5f06c315a9b52b46cd38e42db`.
The Stage 9 packet and the playback-provenance packet were not rewritten.

## Review fixes

Review raised three items. One was withdrawn and two were real. Testing
the race turned up a third defect.

- **Lockup after a late Begin: withdrawn.** The concern was that a Begin
  arriving after a successful Resolve could lock the page. Resolve runs only
  after the page's Begin request has settled, and one request cannot settle
  twice. Tests now drive the real client and controller over a network that
  either holds the original Begin in flight or loses its response after the
  server stored it. The same two orderings also run through the server's
  HTTP API. In both, recovery settles and a fresh key starts and evaluates.
  The late original Begin gets `409 begin_request_closed` and creates
  nothing. This also passes against the controller as first submitted, so
  the lockup did not exist.
- **Recovered interruption feedback was cleared.** After a recovery that
  returned `INTERRUPTED`, from Resolve or from a Begin answered
  `INTERRUPTED`, the page drew the interrupted attempt and then cleared it
  in the same tick, leaving only the status line. Both paths now clear
  first and show the attempt second, as cancellation already did. The
  witness asserts the feedback stays visible in W1, W3 and W4.
- **The Stage 9 verifier trusted any begin wrapper.** It unwrapped any body
  carrying the begin-request schema id. Now the nested attempt counts only
  from a version 1.0.0 `STARTED` wrapper whose lowercase UUID v4 key is the
  key the recorded request sent. Its continuity check also read attempt pins
  from the wrapper rather than the attempt, which skipped T3, T4, T5 and T7
  on a keyed packet. Historical unwrapped packets still verify.
- **The begin-recovery evidence was parsed JSON.** That packet and its
  verifier are rebuilt, as described next.

## Begin-recovery witness, rerun

```text
tested source  ef0ba1c3b56e4ac5cf3dee0ee3dc815bf9b0c917
tested tree    074b25d2d6ae5863f470c7359700dd9f2585c036
dirty          no
started        2026-11-02T01:35:24Z
```

| Runtime | Version |
| --- | --- |
| Python | 3.11.9 |
| Node | v24.11.0 |
| Chrome | 156.0.8078.74 |
| puppeteer-core | 23.11.1 |
| OS | Windows 11 (`Windows-10-10.0.26100-SP0`) |

The witness exited 0 with nine checks passing and no failures, and the
verifier accepts the packet. Each exchange keeps its exact request and
response bytes and their sha256, beside the parsed documents. The verifier
reads the bytes, requires the parsed copies to match them, and checks how
the exchanges relate: the witnessed order of each scenario, one key per
scenario bound to one payload, one attempt per key, recovered interruptions
with no captured notes, the W5 replay being the page's own aborted bytes,
and epoch A and epoch B separated by the restart.

**Live and simulated.** Every server response in the packet is live. Each
exchange records who sent the request (`sender`) and what the page saw
(`page_outcome`).

| `page_outcome` | Meaning |
| --- | --- |
| `response` | The page sent the request and received the live response. |
| `network_failure` | Simulated. The harness aborted the page's request. Where the harness forwarded those bytes first (`sender: harness`), the response recorded is the live server's. W5's aborted Begin reached no server and has no response. |
| `not_sent_by_page` | The harness posted the bytes to the live server. The page never saw the answer. |

| Seq | Scenario | Sender | Page saw | Epoch | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | W1 Begin | harness, forwarded | simulated failure | A | `201 STARTED`, attempt `59844cc0-f644-489a-8519-72ddf0e7cc15` |
| 2 | W1 Resolve | page | live | A | `200 INTERRUPTED`, same attempt; feedback visible |
| 3 | W2 recovery | harness | not sent | A | `200 NO_ATTEMPT` before the Begin was released |
| 4 | W2 Begin | page | live | A | `409 begin_request_closed` |
| 5 | W2 Resolve | page | live | A | `200 NO_ATTEMPT` |
| 6 | W3 recovery | harness | not sent | A | `202 PENDING` while preparation was blocked |
| 7 | W3 Begin | page | live | A | `200 INTERRUPTED`, attempt `79c700df-b100-4710-9d4e-253aa255322f`; feedback visible |
| 8 | W4 Begin | harness, forwarded | simulated failure | A | `201 STARTED`, attempt `05be68a1-e16d-4cb2-89b8-0d726da28278` |
| 9 | W4 Resolve | harness, forwarded | simulated failure | A | `200 INTERRUPTED` |
| 10 | W4 Resolve | page | live | A | the same stored `INTERRUPTED` document; feedback visible |
| 11 | W5 Begin | none | simulated failure | A | never reached a server |
| 12 | restart | | | A to B | pid 36672 replaced by pid 14000 |
| 13 | W5 Resolve | page | live | B | `200 NO_ATTEMPT` |
| 14 | W5 replay | harness, W5's bytes | not sent | B | `409 begin_request_closed` |

The feedback fix changes what the page shows after a recovered
interruption, so the other browser witnesses were rerun on the same
machine.

- **Stage 8** at `3542427ed8a996aa0caa7507059b3d7e88c729e2` exited 0 with 31 checks passing and no
  failures. Request counts were begin 6, message 8, finish 3, cancel 2, as
  in the original run. Its check after Resolve closed a mismatched-revision
  Begin had required an empty feedback panel. That requirement was the
  defect itself, so the check now requires the interruption to show, with
  no evaluation counts. Its 404 is still simulated and labeled so.
- **Integration (Stage 9)**: all 48 browser checks passed with no failures,
  but the parent never wrote a packet on Windows. Its driver uses POSIX
  process groups (`start_new_session`, `os.killpg`). No integration packet
  was produced, and none is claimed. The original Linux run above stands
  for it.

## Commands

```bash
python scripts/smoke_do016_begin_recovery.py /tmp/mas-begin-final \
  --chrome-executable /usr/local/bin/google-chrome \
  --puppeteer-module /tmp/inbox-smoke/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js
python scripts/verify_do016_begin_recovery_evidence.py \
  docs/mvp2/do016_begin_recovery_artifacts/evidence.json --root .
```

The rerun used the same driver on Windows:

```bash
python scripts/smoke_do016_begin_recovery.py <output> \
  --chrome-executable "C:/Program Files/Google/Chrome/Application/chrome.exe" \
  --puppeteer-module C:/tmp/inbox-smoke/node_modules/puppeteer-core/lib/esm/puppeteer/puppeteer-core.js
```

## Limits that remain

Unkeyed Begin callers can still leave an attempt when the response is lost.
Closing the tab can drop the key before the best-effort recovery is known
to have succeeded. Keys and tombstones last only as long as the server
process. A restart therefore answers `NO_ATTEMPT` even if an older process
had created an attempt. Physical MIDI and speaker output are not certified.
Nothing here adds persistence, remote delivery, mastery, or lesson completion.

The rerun packet was recorded on Windows with Chrome 156 and Node 24, not
the Linux, Chrome 148 and Node 22 setup of the original run. CI does not
run any browser witness. Request bytes for the page's own requests come from
Chrome's record of the posted body, not from a socket capture. The verifier
can show that a packet is internally consistent. It cannot show that a
consistent packet was not fabricated as a whole.
