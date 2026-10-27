# DO-016 integration and recovery witness

This record accepts the scoped software integration only. It does not certify
physical MIDI or audio, remote delivery, persistence, or lesson completion.
It does not merge, tag, or release DO-016.

The machine-readable packet is
[`do016_integration_artifacts/evidence.json`](do016_integration_artifacts/evidence.json).
`python scripts/verify_do016_integration_evidence.py` recomputes the recorded
hashes and does not trust the packet's own pass flag.

## What was tested

```text
branch            agent/do016-integration-recovery-s09
entry / base      7a1aecfb2ab4b03872a571fbebaca7ee22418093
tested source     8804f0c90cab1ff3a2f84def68e43c1eb1afa871
tested tree       293162586de1c9c843b7886fbc21b265828e6c5e
```

The tested tree was clean. `8804f0c` contains the witness drivers, the
verifier, and this plan's scope. The evidence packet, this report, the
measured table, and the assertion that reloads the committed packet come
after that revision. They do not change the drivers the witness executed.

Local environment, recorded from the run rather than assumed:

| Runtime | Version |
| --- | --- |
| Python | 3.12.3 |
| Node | v22.23.4 |
| Chrome | 148.0.7778.96 at `/usr/local/bin/google-chrome` |
| Puppeteer | `/tmp/inbox-smoke/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js` |
| OS | Linux |
| Clock | 11:37:39 AM CDT on October 27, 2026 |

CI runs pytest on Python 3.11. This machine does not.

## What the witness did

One custom assignment, "Stage 9 Integration Etude" (`delivery-stage9`), was
posted to the Stage 1 receive route. Its tempo is 8 BPM. The browser chose
it from the inbox, opened paused practice, and started the attempt. No
guided-session or legacy performance request was observed.

Restart is a real process replacement. Epoch A (pid 3684) served
`http://127.0.0.1:38443`. The parent stopped it, started epoch B (pid 3854)
on that same origin with empty stores, and only then let the open page
finish. Epoch C (pid 3871) did the same for cancel. Each restarted process
reported `delivery_count_at_ready: 0`.

| Scenario | Result |
| --- | --- |
| T1 Full chain | One begin and one finish. Delivery, assignment, content, both digests, revision, attempt, capture, session, and evaluation digest are distinct and match the displayed feedback. |
| T2 Policy | Rate 0.75 and looping were on before Start. Capture showed rate 1, loop off, clock `18.00s` to `0.01s`, and locked controls. A seek nudge left the timeline at 9. Ordinary practice returned after evaluation. |
| T3 Cancel | One acknowledged message, then `INTERRUPTED`. Feedback says no evaluation was produced. The next attempt id is different. |
| T4 Restart at Finish | Finish from the still-open page received the live 404 `{"error": "unknown_attempt"}`. Retry stayed hidden. Start and reference controls recovered. |
| T5 Restart at Cancel | A separate attempt, after a new receive and inbox choice, got the same live 404. The page did not claim a recorded cancellation. |
| T6 Recovery | The inbox read "No deliveries have been received on this device." A new receive, preview, choice, and evaluation used attempt `60887ba6-59c4-48c5-bd72-50efd50ab2eb`, not T1's `3b35511f-35e8-473f-af0c-4acabb50652d`. |
| T7 Lost Finish | The server stored `EVALUATED` for attempt `30973382-dca1-417b-9de5-91accbddf925` and digest `sha256:34975f96701ecb28a2fe4b7f5fd54262841f60a603ac02400eea79413ccf796c`. The page saw a transport failure and stayed unconfirmed. Retry used that attempt id, began nothing, and appended nothing. The stored and retried capture and session ids match. |

T1's pins, from the begin and finish bytes:

| Pin | Value |
| --- | --- |
| Delivery | `delivery-stage9` |
| Assignment | `teacher_smith_student_42_2026_08_10` |
| Content | `blues_turnaround_01` |
| Artifact digest | `sha256:bedefe36c5b46dd314aa91c927d11593e62a46ea716c350daccca9676ab84125` |
| Behavior digest | `sha256:c6986fbfcc49c3d92fe5cb0011064797aee5d0d5adf0ffaefd7a3cc6d0a55cc4` |
| Revision | `rev-cf73ae5afa337ebe334e924b` |
| Attempt | `3b35511f-35e8-473f-af0c-4acabb50652d` |
| Capture | `f9c7659a-f957-4603-83f7-4cda3fe23ae8` |
| Performance session | `3fc2c986-2358-41aa-9a6b-b9ceaa5d2746` |
| Evaluation | `sha256:05045b9e3748efdceee34e58cd948f2daedd833d5622eff83624f1cf72e65a59` |

## Actual and simulated transport

The integration Finish and Cancel 404s are responses from the restarted
server. The harness did not write those bodies.

Stage 8 still intercepts one Finish and supplies `404 unknown_attempt`
itself. Its summary records `restart_witness: false` and
`simulated_responses[].source: "simulated"`. That run is regression coverage
for the page. It is not this restart witness.

T7 forwarded the Finish body once with a normal POST, kept the 200, and
failed only the browser-facing request (`net::ERR_FAILED`). The retry is a
second browser POST of the same attempt id.

## Commands

```bash
python scripts/smoke_do016_integration.py /tmp/do016-s09-integration \
  --chrome-executable /usr/local/bin/google-chrome \
  --puppeteer-module /tmp/inbox-smoke/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js
python scripts/verify_do016_integration_evidence.py \
  docs/mvp2/do016_integration_artifacts/evidence.json --root .
python scripts/smoke_do016_received_practice.py /tmp/do016-s06
python scripts/smoke_do016_received_attempt.py /tmp/do016-s08 \
  --chrome-executable /usr/local/bin/google-chrome \
  --puppeteer-module /tmp/inbox-smoke/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js
```

## Gates

| Gate | Result |
| --- | --- |
| `ruff check src tests` | PASS |
| `ruff` on the three touched scripts | PASS |
| `mypy` | PASS, 173 source files |
| `pytest --cov --cov-report=term-missing` | 3536 passed, 3 skipped, 95.34% in 92.11s |
| `npm test` in `web/mvp1` | 589 passed, 0 failed |
| Stage 6 witness | PASS, 0 failures |
| Stage 8 witness | PASS, 0 failures; begin 5, message 8, finish 3, cancel 2 |
| Integration witness | PASS, 0 failures |
| Evidence verifier | PASS |
| `verify_do015_certification.py` | OK (9 of 9) |
| `verify_do015_publication.py` | OK (8 of 8) |
| `build_do015_certification_evidence.py --check` | OK |
| `check_in_flight.py` | OK (1 row, 0 notes) |
| DO-015 certification capture | exit 0, final status `CLOSED`, 3 attempts |

The DO-015 capture rewrote `docs/mvp2/do015_artifacts/browser_smoke_summary.json`.
That file was restored. Its sha256 is
`11af5e8656b87785d152735777702b9a025fd0d5f06c315a9b52b46cd38e42db`,
matching the packet's before and after hashes. The other three frozen
DO-015 files were unchanged.

The committed npm count is 589. It is not 592.

## Limits that remain

- An unconfirmed begin is not repeated. The server may still hold that
  attempt until the process exits. This witness does not repair that.
- Deliveries, choices, and attempts disappear when the process stops.
- Evaluation of one attempt is not mastery and not lesson completion.
- MIDI in this witness was injected. Physical MIDI input is unverified.
- The injected notes were 60 and 61, note-on only. The lesson expects 64, 67,
  and 69, so every evaluation here scored matched 0, missing 3, extra 2. That
  is the correct score for that input, but no matched note was exercised.
  Stage 8's witness covers a match (matched 1).
- The prepared playback plan carries `canonical_revision_id: null`. The score
  and TAB cite `rev-cf73ae5afa337ebe334e924b`, but playback is not bound to a
  revision. This predates DO-016 and is outside this order.
- The scheduler can accept events. That is not certified speaker output.
- There is no durable inbox, teacher send UI, account, or remote delivery.
- No guided session was opened and no recommendation was executed.
