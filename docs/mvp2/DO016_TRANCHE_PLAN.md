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

## Stage 4 — local lesson inbox

| Field | Value |
| --- | --- |
| Branch | `cursor/do016-local-lesson-inbox-s04` |
| Base | `537dfb30b5f5fe2e6154408e89e761d7f904a53e` |
| Agent | Cursor |
| Page | `/lesson-inbox.html` |
| Merge / tag / release | not authorized |

Stage 3 records a choice and does not show it. Stage 4 is a page on the
existing localhost server so a person on this device can see received
deliveries, request a fresh preview of one, see whether a valid local choice
already exists, and explicitly choose that previewed delivery for later
practice. The page calls the Stage 1–3 HTTP contracts. It adds no backend
route, schema, or production hook.

### What the page shows

The list is summary metadata in server order: `delivery_id`, `assignment_id`,
`content_id`, `sender_ref`, `recipient_ref`, and `classroom_ref`. A row does
not resolve the lesson and does not authorize practice. Title, notes, event
details, and both declared digests appear only after a successful `READY`
preview. Choice status appears only in the selected panel. The list does not
request a choice for every row.

`recipient_ref` is an opaque recipient label. It is not the person using the
page and it does not authorize.

The page is a separate entry point. Certified `index.html` does not link to
it. Styles live in `lesson-inbox.css`. Server strings are text, not HTML.
Delivery ids are not read from a free-text field, the URL fragment, or
browser storage.

The inbox and the choice are in memory. The page says that they disappear
when the server process ends.

### How a selection becomes a choice

Selecting a row, or refreshing the selected delivery, requests a new preview.
Choice GET runs only after that preview is `READY`, the `delivery_id` matches
the selection, and both declared digests are present. The client returns the
HTTP status and the public `error` code. The page decides whether Choose is
enabled.

**Choose for practice** is enabled only when that full sequence succeeds and
choice GET returns `404` with `unknown_practice_choice`. A successful preview
does not clear `choice_conflict` or any other choice-GET failure. Any failure
leaves Choose disabled until a later full sequence reaches that 404.

Choose POSTs the preview document's declared digests as
`expected_assignment_artifact_digest` and
`expected_assignment_behavior_digest`. The page does not recompute them, does
not take them from the list row, and does not retry POST. `201` and an
identical `200` display `CHOSEN_FOR_PRACTICE` and do not open the lesson.
An existing valid choice does not POST again.

`stale_preview` keeps the pinned digests and tells the person to refresh the
selected delivery. Refresh inbox reloads the list only. An older response
cannot paint a newer selection. Opaque ids are encoded once with
`encodeURIComponent`.

### What this stage does not do

No practice activation, remote delivery, student acceptance, guided session,
Transport, playback, evaluation, or completion. No new backend endpoint.
Corrupt or removed envelopes are injected only by the browser-smoke harness
into that test server's in-memory repository. `LessonAssignmentV1`,
`LessonDeliveryEnvelopeV1`, `LessonDeliveryPreviewV1`, and
`LocalPracticeChoiceV1` stay unchanged. DO-015 frozen artifacts and the
certified browser runtime are not part of this stage.

This is a device-local choice UI only.

### Verification

Recorded on `cursor/do016-local-lesson-inbox-s04` after the gate run. The
interpreter here is Python 3.12.3. CI runs the same commands on Python 3.11;
this interpreter satisfies `requires-python >= 3.11`, and no gate was relaxed.

| Gate | Result |
| --- | --- |
| `ruff check src tests` | PASS |
| `mypy` (strict, `src` only) | PASS, 169 source files |
| `pytest --cov --cov-report=term-missing` | 3401 passed, 3 skipped, 95.70% (floor 95%) |
| `npm test` in `web/mvp1` | 523 passed, 0 failed |
| `python3 scripts/check_in_flight.py` | OK |
| `python3 scripts/verify_do015_certification.py` | OK (9 of 9) |
| `python3 scripts/verify_do015_publication.py` | OK (8 of 8), successor mode |
| Stage 9 browser witness | PASS |

The witness is `node web/mvp1/tests/do015_certification_capture.mjs`. It exited
0 with final status `CLOSED` and 3 attempts. The harness rewrites
`docs/mvp2/do015_artifacts/browser_smoke_summary.json`, so that file was
restored. Its sha256 is
`11af5e8656b87785d152735777702b9a025fd0d5f06c315a9b52b46cd38e42db`.

Merge base is `537dfb30b5f5fe2e6154408e89e761d7f904a53e`, the tip of
`origin/main` at verification. The diff against that base is the register,
this plan, and the new inbox page, client, stylesheet, and Node tests. It
does not touch `LessonAssignmentV1`, `LessonDeliveryEnvelopeV1`,
`LessonDeliveryPreviewV1`, `LocalPracticeChoiceV1`, certified `index.html`,
`app.js`, `styles.css`, or the DO-015 frozen artifacts.

The localhost browser smoke is `python3 /tmp/inbox-smoke/harness.py` against
`serve_mvp_directory` on `web/mvp1` with the existing
`LocalLessonDeliveryApi`. Chrome is `/usr/local/bin/google-chrome`, driven
headless by puppeteer-core. It seeds a valid delivery with Stage 1 POST, then
the harness injects a corrupt envelope and deletes one from that server's
in-memory repository. There is no production route for either injection.
Empty inbox, summary list, READY preview, `stale_preview` without a second
POST, `CHOSEN_FOR_PRACTICE` after reload, `integrity_mismatch`, a removed
delivery, and HTML-like text all passed. A desktop Chrome walkthrough of the
same page showed the empty inbox, the choice, the reload, and the corrupt
delivery.

This is a device-local choice UI only. The inbox and the choice disappear
when the server process ends. Practice activation remains a later order.

## Stage 5 — prepare a chosen delivery

| Field | Value |
| --- | --- |
| Branch | `cursor/do016-local-practice-preparation-s05` |
| Base | `e2929f73a9a649c06d9692483e7099420c6fe977` |
| Agent | Cursor |
| Predecessor | PR #51, merged |
| Route | `POST /api/education/lesson-practice-preparations` |
| Merge / tag / release | not authorized |

Stage 4 shows a choice. Stage 5 turns that choice into the projection,
playback plan, practice policy, and score artifacts a later practice screen
will read. It does not open that screen, play the lesson, or record that
practice started.

### Route

```text
POST /api/education/lesson-practice-preparations
```

The path is exact. A trailing slash and any sibling path keep the routing
they already had. The body is a JSON object and nothing else:

```json
{
  "delivery_id": "<opaque ID>",
  "expected_assignment_artifact_digest": "sha256:<64 lowercase hex>",
  "expected_assignment_behavior_digest": "sha256:<64 lowercase hex>"
}
```

The id is nonblank and preserved exactly. It is read only from the body,
never from the path, and it is not decoded again. Digests use the existing
declared format. A missing field, an extra field, or any nonempty query
string is `400` under the same sanitized request-validation sentences Stage 3
uses. Every method other than POST on this exact path is `405`, including
GET, HEAD, PUT, DELETE, PATCH, and OPTIONS.

POST computes. It does not store a preparation, create a choice, open a
session, or write a file. A repeated POST prepares again from the current
verified state.

### What a success contains

`200` returns `LocalPracticePreparationV1`:

| Field | Value |
| --- | --- |
| `schema_id` | `master_all_strings.local_practice_preparation` |
| `schema_version` | `1.0.0` |
| `preparation_status` | `PREPARED` |
| `delivery_id`, `assignment_id`, `content_id` | The verified delivery |
| `assignment_artifact_digest`, `assignment_behavior_digest` | The verified declared pins |
| `projection` | The existing web projection export, with `demo_id` null |
| `playback` | The existing serialized playback plan |
| `practice` | The existing practice export, including Python loop seconds |
| `score` | `canonical_revision`, `tab`, and `notation` |

Every top-level field is required, and additional properties are forbidden.
`score` is closed and requires all three artifacts. Nested artifacts keep
their existing wire shapes. A received delivery is not a bundled demo, so
`demo_id` is null. The two assignment pins stay distinct fields from the
projection digest and from the canonical revision id.

`PREPARED` means the existing pipeline produced the whole bundle. It does
not say the device can play it, that every note has a position, or that
practice started. Warnings, unsupported features, and unresolved notes stay
as the pipeline already represents them.

### What a failure contains

A failure is `{"error": "<code>"}` and nothing else. `400` uses the existing
request-validation sentences.

| Condition | HTTP | Error |
| --- | ---: | --- |
| Malformed body, invalid fields, or a POST query string | 400 | sanitized request validation |
| No stored practice choice | 404 | `unknown_practice_choice` |
| Delivery missing | 404 | `unknown_delivery_id` |
| Stored assignment fails its declared pins | 409 | `integrity_mismatch` |
| Choice pins or request pins differ from the verified delivery | 409 | `stale_preview` |
| Assignment cannot resolve | 422 | `unresolvable_assignment` |
| Declared instrument is unavailable | 422 | `unsupported_instrument` |
| Known assignment validation fails during preparation | 422 | `unpreparable_assignment` |
| Any method other than POST | 405 | `method not allowed` |
| Unexpected pipeline, serialization, or consistency failure | 500 | `internal server error` |

Not every `MvpError` is `422`. An unexpected projection, playback-plan, or
practice-policy failure stays a sanitized `500`. No failure returns part of
a preparation. Serializing the success document is inside that same boundary.

### How a choice becomes a bundle

1. Validate the request.
2. `LocalPracticeChoiceService.get` on the Stage 3 repositories. That
   previews again.
3. Compare both request digests with the choice's pins.
4. Read the stored envelope once.
5. Recheck that envelope's integrity, then its delivery, assignment,
   content, and both declared digests against the choice.
6. Prepare that captured assignment through
   `MvpApplication.run_assignment_json` and the existing assignment
   serializer. No instrument override: the declared profile is the one used.
7. Build the existing export payloads in memory.
8. Check the bundle and return it.

Step 5 is what makes a swapped envelope visible. A missing delivery is
missing. A corrupt envelope is an integrity failure. An intact envelope
whose pins differ from the choice is stale. Artifact builders keep the
captured envelope; they do not load the delivery again.

The behavior digest on the prepared assignment must match the declared
behavior pin. The instrument must match the declared profile. TAB and
notation must cite the exported canonical revision. Canonical event
references must stay consistent with the resolved assignment under each
artifact's own inclusion rules: simultaneous notes, unsupported positions,
and score rests are not forced into one row per event.

Musical resolution, spatial selection, tempo, playback planning, practice
policy, and score generation stay with their existing Python authorities.
The preparation service lives under `mvp/` and composes those artifacts.
`education/` does not import the MVP application. A title, a demo lookup, a
recipient label, or routing metadata does not select or authorize anything.
Preparations are not cached.

### What this stage does not do

No practice screen, playback execution, performance attempt, guided session,
evaluation, history update, persistence, remote delivery, account, or
authenticated acceptance. Stage 1–4 contracts stay as they are. Certified
browser files and frozen DO-015 artifacts stay as they are.

### Verification

Recorded when the gates for this branch have been run. The numbers below are
filled from that run, not copied from Stage 4.

### Response validation follow-up

The page checks the closed top-level preview and choice documents at their declared
schema IDs and version 1.0.0. READY requires event-count/array agreement and
unique, nonblank event IDs, as well as the required policy and metadata
fields. Policy objects remain opaque to preserve browser authority boundaries.
Digests must be strings in the declared format.

Both choice GET and choice POST compare delivery, assignment, content, and
both declared digests with the pinned READY preview before displaying
CHOSEN_FOR_PRACTICE. GET accepts only 200; POST accepts 200 or 201. An
inconsistent success leaves Choose disabled and displays no choice claim.

The follow-up passed all 526 Node tests on Node 24.19.0, including malformed
preview cases and independent pin mismatches on GET and POST. The existing
DO-015 certification scenario tests also pass. The localhost browser smoke
above belongs to the original Stage 4 validation; it was not rerun for this
follow-up because the repair environment refuses listening sockets.
