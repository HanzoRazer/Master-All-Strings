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

Filled in as the tranche proceeds.
