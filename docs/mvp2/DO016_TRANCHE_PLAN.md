# DO-016 — Teacher-to-student lesson delivery

Deliver an already-authored `LessonAssignmentV1` across an explicit boundary
into a student-side inbox, and prove it arrived unchanged — without touching the
assignment contract that carries it.

## Published predecessor

DO-015 is closed: implemented, certified, published to `main`. Its three
identities stay distinct, because collapsing them is how a tooling commit ends
up cited as the product.

| Identity | Sha |
| --- | --- |
| `do015_certified_product_sha` | `3fcf618b655c3f51b020d11a0bb3f96571da08d7` |
| `do015_stage9_merge_sha` | `102b7959ac6a99c924baada89ce3b04d779c209d` |
| `do015_stage10_head_sha` | `7b7ccc991bf66cf2fdb321bad394d3bc9a73a339` |
| `do015_publication_baseline_sha` | `0efda5d3701455585e92f673a0c634b44f9a6dc7` |
| `do016_base_sha` | `280982c53d2d9f6873a73570f0ef224851908ecb` |

`do016_base_sha` is not the publication baseline. Two pull requests merged
between them — #41's publication closeout and #42's branch pruning — and neither
touched a product file.

### Stage 11 entry gate

Run against the published baseline before this branch existed, and again in
this branch's first commit:

| Gate | Result |
| --- | --- |
| PR #41 merged | yes, at `0efda5d` |
| `3fcf618`, `102b795`, `7b7ccc9` ancestors of the baseline | yes |
| Protected product surface since `3fcf618` | 0 files |
| Stage 9 certification verifier | OK (9 of 9) |
| Stage 9 evidence generator `--check` | OK |
| Stage 10 publication verifier | OK (9 of 9) |
| `mvp-1` | `ac38819b23ed9d85b651755e7612f42d7d528ddc`, unchanged |
| MVP 2 tag | none, locally or on `origin` |

The publication verifier notes that it cannot enforce `stage10_base_sha` from
`main`, because `HEAD` is `origin/main` and there is no branch point left to
compare. That is the documented post-merge behaviour, not a failure.

## Stage 1 — delivery envelope and local inbox

| Field | Value |
| --- | --- |
| Branch | `cursor/do016-assignment-delivery-cc04` |
| Base | `280982c53d2d9f6873a73570f0ef224851908ecb` |
| Agent | Claude |
| Merge / tag / release | not authorized |

### What it adds

```text
LessonAssignmentV1  (frozen, 1.0.0)
        |
LessonDeliveryEnvelopeV1   addressing + both assignment digests
        |
LessonDeliveryService      receive / get / list
        |
in-memory inbox            deterministic order, duplicate IDs rejected
        |
localhost API              POST/GET /api/education/lesson-deliveries
```

### What it deliberately does not add

Receiving is not accepting, and it is not loading. A received delivery sits in
an inbox: no canonical resolution, no Transport, no evaluation, no guided
session, no playback. Addressing is opaque strings — no accounts, no
authentication, no authorization, no device discovery. Storage is in memory,
and there is no networking beyond the localhost seam.

### Where delivery lives, and why

`lesson/` owns `LessonAssignmentV1`. `education/` owns delivering it. Putting
the envelope beside the assignment would suggest delivery is part of the lesson
contract; the point of this tranche is that it is not. The assignment stays at
schema `1.0.0`, unmodified, and the envelope wraps it from outside.

`LessonRoutingV1` inside an assignment stays semantically inert. It is carried
through untouched and is never delivery authority — the envelope's own
`sender_ref` / `recipient_ref` / `classroom_ref` decide where a delivery goes.
The two are not required to agree, and delivery never rewrites the assignment's
routing.

### Two digests, two questions

Every envelope pins both, and both are recomputed on receipt:

| Digest | Answers |
| --- | --- |
| `assignment_artifact_digest` | did the exact serialized artifact change? |
| `assignment_behavior_digest` | did the musical or instructional behaviour change? |

They differ on purpose: changing an assignment's routing changes the artifact
digest and leaves the behaviour digest alone. Delivery therefore states two
independent integrity facts rather than one blurred one.

## Verification

| Gate | Result |
| --- | --- |
| DO-016 suites (6 files) | 96 passed |
| `tests/education` + `tests/lesson` | 512 passed, 2 skipped |
| Full pytest | 3178 passed, 3 skipped, 2 failed |
| Coverage | 95.65% (floor 95%) |
| Node (`web/mvp1`) | 505 passed, 0 failed |
| Ruff / strict mypy | PASS |
| Guided-session fixtures `--check` | OK |
| In-flight register | OK |
| DO-015 certification verifier | OK (9 of 9) |
| DO-015 evidence generator `--check` | OK |
| DO-015 publication verifier | OK (8 of 8), successor mode |

The two pytest failures are the documented Windows-only pair, unchanged by this
tranche and green on Linux CI.

Fifteen mutations, each breaking one delivery rule — unchecked digests, accepted
unknown fields, an unpinned schema, an insertion-ordered inbox, an ignored
recipient filter, overwriting duplicates, storing before checking, listing
whole lessons, a conflict reported as a bad request — are each caught by at
least one test.

### The predecessor gate, resolved

It did not pass when this tranche was first pushed. The publication verifier
failed on two counts — DO-016's two authorized file modifications read as a
changed product surface, and Stage 10's branch point cannot be re-derived from
a later branch — and both were defects in the verifier's applicability to
successor branches rather than evidence about DO-015.

They were fixed outside this tranche, in PR #44 and its follow-up #45, and this
branch merged the result. The verifier now runs in successor mode here and
reports OK: the certified product is still an ancestor, and the certification
and publication artifacts are still the bytes that were published.

### Uniqueness is decided where the write happens

Review found a race the threading local server makes real: `contains()` then
`put()` is two operations, so two requests carrying one `delivery_id` could
both pass the check and both be told they succeeded, with one lesson silently
replacing the other.

The repository now offers `put_if_absent()` and no unconditional write at all,
so the check and the insert are one step under its own lock, and a durable
implementation inherits the obligation rather than re-deriving it. Two
regression tests drive it — one through the service, one through two
simultaneous POSTs against the real server carrying *different* lessons under
one identity — and both fail if check and write are pulled apart.

### Two smaller corrections from the same review

Bytes that are not UTF-8 are named where the decoding happens, as a malformed
delivery in the same family as malformed JSON, rather than reaching a caller as
a `UnicodeDecodeError` from inside the boundary.

An unexpected exception is a `500` carrying no detail, not a `400`. A defect in
this application is not a malformed request, and answering `400` would send a
caller looking for a mistake in a correct payload.

## Stage 2 — local lesson selection and verified preview

| Field | Value |
| --- | --- |
| Branch | `cursor/do016-lesson-preview-s02` |
| Base | `a5cf2640a733ffdafef4bd46280d092a60a3ecaf` |
| Agent | Cursor |
| Merge / tag / release | not authorized |

Stage 1 left a received envelope in an inbox and returned that same envelope on
GET. Stage 2 lets a caller name one of those deliveries and read a bounded
summary of the lesson it carries. The summary is produced on this device. It
is not acceptance, not a start, not playback, and not completion.

### Route

```text
GET /api/education/lesson-delivery-preview?delivery_id=<encoded-value>
```

This is an exact sibling of `/api/education/lesson-deliveries`, not a path
beneath it. A delivery id that ends in `/preview`, or that contains `/`, `%`,
space, `#`, `?`, or `&`, is still a Stage 1 id when it is fetched through the
collection. The preview route matches the path by equality and reads the id
from exactly one query value.

The query value is percent-decoded once, by `parse_qs` with blank values kept,
at the HTTP boundary. It is not passed through `unquote()` again and it is not
stripped. A missing, blank, whitespace-only, or repeated `delivery_id` is
`400`. Any method other than GET on that exact path is `405`, including
`HEAD` (the static handler would otherwise treat the path as a file) and
verbs the server does not implement on any other route.

### What a preview checks, and what it returns

The stored envelope comes from `LessonDeliveryService.get()`. Both declared
digests are rechecked with `validate_delivery_integrity()` before
`resolve_lesson_assignment()` runs. `envelope_for()` is not used on the way
out, so the response carries the digests the envelope declared rather than a
freshly substituted pair.

`LessonDeliveryPreviewV1` (`master_all_strings.lesson_delivery_preview`,
`1.0.0`) is a closed document:

| Field | Source |
| --- | --- |
| `preview_status` | always `READY` on success; failures are HTTP errors, not a partial document |
| `delivery_id`, `assignment_id`, `content_id` | the delivery and the resolved lesson identity |
| both digests | the envelope's declared values |
| `title`, `canonical_event_count`, `canonical_event_ids` | resolver event order |
| `playback_policy` | the resolver's playback request, not a second planner |
| `spatial_policy` | the resolver's spatial intent |
| `meter_change_count` | the resolver's meter map, after its same-tick dedupe |
| `instruction_objective`, `teacher_note` | the resolver, null when the lesson has none |

`sender_ref`, `recipient_ref`, and `classroom_ref` stay off the document. They
are opaque labels and authorize nothing. The document does not claim the lesson
can be played on a particular device.

### Failures

| Condition | Status | Body |
| --- | --- | --- |
| Missing, blank, or repeated `delivery_id` | 400 | `{"error": ...}` |
| Unknown delivery | 404 | Stage 1 not-found text |
| Declared digest does not recompute | 409 | `{"error": "integrity_mismatch"}` |
| Envelope is intact but the assignment cannot resolve | 422 | `{"error": "unresolvable_assignment"}` |
| Method other than GET on the preview path | 405 | `{"error": "method not allowed"}` |
| Unexpected failure | 500 | `{"error": "internal server error"}` |

A failure returns no preview fields. Serializing the preview document happens
inside the same handler, so a failure there is the sanitized `500` and not an
uncaught exception. Stage 1 POST, list, and GET-one are unchanged, including
duplicate-identity `409` and digest `400` on receive.

### What this stage does not do

No student UI, no teacher send path, no remote transport, no accounts, no
authorization, no persistence, no acceptance record, no guided session, no
evaluation, and no playback. `LessonAssignmentV1` and
`LessonDeliveryEnvelopeV1` stay at schema 1.0.0. DO-015 frozen artifacts and
the certified browser runtime are not part of this stage.

### Verification

Recorded on `cursor/do016-lesson-preview-s02` after the gate run. The interpreter
here is Python 3.12.3. CI runs the same commands on Python 3.11; this
interpreter satisfies `requires-python >= 3.11`, and no gate was relaxed.

| Gate | Result |
| --- | --- |
| `ruff check src tests` | PASS |
| `mypy` (strict, `src` only) | PASS, 167 source files |
| `pytest --cov --cov-report=term-missing` | 3337 passed, 3 skipped, 95.67% (floor 95%) |
| `npm test` in `web/mvp1` | 505 passed, 0 failed |
| `python3 scripts/check_in_flight.py` | OK |
| `python3 scripts/verify_do015_certification.py` | OK (9 of 9) |
| `python3 scripts/verify_do015_publication.py` | OK (8 of 8), successor mode |
| `python3 scripts/build_do015_certification_evidence.py --check` | OK |
| Stage 9 browser witness | PASS |

The witness is `node web/mvp1/tests/do015_certification_capture.mjs`. It exited
0 with final status `CLOSED` and 3 attempts. The harness rewrites
`docs/mvp2/do015_artifacts/browser_smoke_summary.json` with fresh session
identifiers, so that file was restored after the run. The frozen Stage 9
artifact on this branch is the committed bytes.

Merge base is `a5cf2640a733ffdafef4bd46280d092a60a3ecaf`, the tip of
`origin/main` at verification. The diff against that base does not touch
`LessonAssignmentV1`, `LessonDeliveryEnvelopeV1` schema 1.0.0, `web/mvp1`
product files, or the DO-015 frozen artifacts.

## Stage 3 — local practice choice

| Field | Value |
| --- | --- |
| Branch | `cursor/do016-local-practice-choice-s03` |
| Base | `be22591367bab376a3ad88db4a93ffa0b274c2c9` |
| Agent | Cursor |
| Merge / tag / release | not authorized |

Stage 2 previews a received delivery and changes nothing. Stage 3 records an
explicit choice, on this device, to use that delivery for later practice. The
record means chosen for practice here. It is not authenticated acceptance, and
it is not evidence that the lesson started, played, or was completed.

### Routes

```text
POST /api/education/lesson-practice-choices
GET  /api/education/lesson-practice-choices?delivery_id=<encoded-value>
```

Both are exact paths. A delivery id is not this route, including one that ends
in `/preview` or contains `/`, `%`, space, `#`, `?`, or `&`.

POST takes a JSON object and nothing else. Any query string on that path,
including `?delivery_id=`, is `400`. The body is the only source of the id:

```json
{
  "delivery_id": "<opaque delivery ID>",
  "expected_assignment_artifact_digest": "sha256:<64 lowercase hex>",
  "expected_assignment_behavior_digest": "sha256:<64 lowercase hex>"
}
```

GET reads exactly one nonblank `delivery_id`, percent-decoded once. The value
is not stripped. A missing, blank, whitespace-only, or repeated id is `400`.
Extra query fields do not filter or authorize. Any method other than GET or
POST on the exact path is `405`, including `HEAD`.

### What a choice checks

Recording calls `LessonDeliveryPreviewService.preview()` first. That rechecks
both stored digests and resolves the assignment. The expected digests are then
compared with the envelope's declared digests. `envelope_for()` is not used to
replace them. Only then does the choice repository run `put_if_absent` under
its own lock. A stale request returns before that write, so it cannot replace
a choice already stored.

The store is in memory, separate from the delivery inbox, and keyed by
`delivery_id`. There is no unconditional replacement.

`LocalPracticeChoiceV1` (`master_all_strings.local_practice_choice`, `1.0.0`)
is a closed document:

| Field | Source |
| --- | --- |
| `choice_status` | always `CHOSEN_FOR_PRACTICE`; the caller cannot send a status |
| `delivery_id`, `assignment_id`, `content_id` | the delivery and the resolved lesson |
| both digests | the envelope's declared values, pinned on the choice |

No student identity, addressing label, acceptance time, playback state, or
assignment object is included. `recipient_ref` does not authorize or merge
choices. Two deliveries of one assignment stay two choices.

GET loads the stored choice, then previews again. The choice is returned only
when that preview's identity and declared digests still match the pins. GET
does not mutate or delete the choice.

### Failures

| Condition | Status | Body |
| --- | --- | --- |
| Malformed body, or any POST query string | 400 | `{"error": ...}` |
| Missing, blank, or repeated GET `delivery_id` | 400 | `{"error": ...}` |
| No choice stored | 404 | `{"error": "unknown_practice_choice"}` |
| Delivery missing | 404 | `{"error": "unknown_delivery_id"}` |
| Stored digest does not recompute | 409 | `{"error": "integrity_mismatch"}` |
| Expected or pinned digests differ from the intact delivery | 409 | `{"error": "stale_preview"}` |
| Choice already stored with different pins | 409 | `{"error": "choice_conflict"}` |
| Assignment cannot resolve | 422 | `{"error": "unresolvable_assignment"}` |
| Method other than GET or POST | 405 | `{"error": "method not allowed"}` |
| Unexpected failure | 500 | `{"error": "internal server error"}` |

A failure returns no choice fields. The first valid POST is `201`. An identical
repeat — same delivery, assignment, content, and both digests — is `200` and
the same document. Two concurrent identical POSTs store one choice and answer
`201` and `200`.

Stage 1 receive, list, and GET, and Stage 2 preview, stay as they were.

### What this stage does not do

No student UI, no teacher-visible acceptance, no login, no remote transport, no
durable database, no synchronization, no guided session, no evaluation, no
history update, and no playback. Authenticated acceptance and practice
activation are a later order. `LessonAssignmentV1`, `LessonDeliveryEnvelopeV1`,
and `LessonDeliveryPreviewV1` stay unchanged. DO-015 frozen artifacts and the
certified browser runtime are not part of this stage.

### Verification

Recorded on `cursor/do016-local-practice-choice-s03` after the gate run. The
interpreter here is Python 3.12.3. CI runs the same commands on Python 3.11;
this interpreter satisfies `requires-python >= 3.11`, and no gate was relaxed.

| Gate | Result |
| --- | --- |
| `ruff check src tests` | PASS |
| `mypy` (strict, `src` only) | PASS, 169 source files |
| `pytest --cov --cov-report=term-missing` | 3401 passed, 3 skipped, 95.70% (floor 95%) |
| `npm test` in `web/mvp1` | 505 passed, 0 failed |
| `python3 scripts/check_in_flight.py` | OK |
| `python3 scripts/verify_do015_certification.py` | OK (9 of 9) |
| `python3 scripts/verify_do015_publication.py` | OK (8 of 8), successor mode |
| Stage 9 browser witness | PASS |

The witness is `node web/mvp1/tests/do015_certification_capture.mjs`. It exited
0 with final status `CLOSED` and 3 attempts. The harness rewrites
`docs/mvp2/do015_artifacts/browser_smoke_summary.json` with fresh session
identifiers, so that file was restored after the run.

Merge base is `be22591367bab376a3ad88db4a93ffa0b274c2c9`, the tip of
`origin/main` at verification. The diff against that base does not touch
`LessonAssignmentV1`, `LessonDeliveryEnvelopeV1`, `LessonDeliveryPreviewV1`,
`web/mvp1` product files, or the DO-015 frozen artifacts.

Two concurrent identical choice POSTs against the threaded localhost server
returned `201` and `200` and left one stored choice. This stage is local choice
only. Authenticated acceptance and practice activation remain a later order.
