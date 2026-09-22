/**
 * DO-015 Stage 9 reproducible browser witness.
 *
 * Boots the real `app.js` against the in-repo harness and drives the whole
 * guided-practice lifecycle through the page's own controls: Arm, Start,
 * perform, Stop, Accept, Apply, again, and again until the session closes.
 * Then it checks the two fail-closed boundaries a certification has to show
 * -- a re-cut revision and a lesson switch -- and writes what it observed.
 *
 * The evaluation and guidance it serves are not invented here. They come from
 * `docs/mvp2/do015_artifacts/certification_scenarios.json`, which the real
 * Python evaluator produced and a pytest regenerates, so the digests this
 * witness correlates are the product's own.
 *
 * What it proves: application orchestration, the real UI event path, and a
 * deterministic guided flow that anyone can re-run with
 *
 *     node web/mvp1/tests/do015_certification_capture.mjs
 *
 * What it does not prove: rendering. It mints DOM objects rather than laying
 * anything out. Rendering is the real-browser witness's job.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createFetch, failWith, installBrowserGlobals, waitFor } from "./browser_harness.js";

const repoPath = (path) => fileURLToPath(new URL(`../../../${path}`, import.meta.url));

const SCENARIOS = JSON.parse(
  readFileSync(repoPath("docs/mvp2/do015_artifacts/certification_scenarios.json"), "utf-8"),
);
const LESSON_A = "ascending_scale";
const LESSON_B = "descending_scale";
const RECUT_REVISION = "rev-000000000000certification";

/** A guided-session endpoint following the Stage 2 lifecycle. */
function lifecycleServer() {
  const sessions = new Map();
  const attemptOf = (evaluation, guidance, attemptId, index) => ({
    schema_version: "1.0.0",
    attempt_id: attemptId,
    attempt_index: index,
    assignment_id: evaluation.assignment_id,
    content_id: evaluation.content_id,
    canonical_revision_id: guidance.canonical_revision_id,
    performance_session_id: evaluation.performance_session_id,
    evaluation_digest: evaluation.evaluation_digest,
    guidance_digest: guidance.guidance_digest,
    action: {
      schema_version: "1.0.0",
      recommended_action: guidance.next_action,
      action_disposition: "PENDING",
      execution_status: "NOT_REQUESTED",
      executed_action: null,
    },
    practice_context: { schema_version: "1.0.0", playback_rate: null },
  });
  const store = (session) => {
    sessions.set(session.session_id, session);
    return JSON.parse(JSON.stringify(session));
  };
  const withCurrent = (session, action, status) => ({
    ...session,
    status,
    attempts: [
      ...session.attempts.slice(0, -1),
      { ...session.attempts[session.attempts.length - 1], action },
    ],
  });
  return {
    sessions,
    routes: {
      "POST /api/education/guided-sessions": ({ body }) =>
        store({
          schema_version: "1.0.0",
          policy_version: "guided-practice-session-v1",
          session_id: body.session_id,
          assignment_id: body.evaluation.assignment_id,
          content_id: body.evaluation.content_id,
          canonical_revision_id: body.guidance.canonical_revision_id,
          status: "AWAITING_ACTION",
          attempts: [attemptOf(body.evaluation, body.guidance, body.attempt_id, 0)],
          current_attempt_index: 0,
          session_digest: "sha256:certification-mirror",
          provenance: [],
        }),
      "POST /api/education/guided-sessions/*": ({ path, body }) => {
        const [rawId, verb] = path.replace("/api/education/guided-sessions/", "").split("/");
        const session = sessions.get(decodeURIComponent(rawId));
        if (!session) return failWith(404, "unknown session_id");
        const current = session.attempts[session.attempts.length - 1];
        if (verb === "disposition") {
          if (session.status !== "AWAITING_ACTION") {
            return failWith(409, "disposition requires AWAITING_ACTION");
          }
          return store(
            withCurrent(
              session,
              {
                ...current.action,
                action_disposition: body.disposition,
                execution_status: body.disposition === "ACCEPTED" ? "PENDING" : "NOT_REQUESTED",
              },
              body.disposition === "DECLINED" ? "AWAITING_ATTEMPT" : "AWAITING_ACTION",
            ),
          );
        }
        if (verb === "execution") {
          if (current.action.action_disposition !== "ACCEPTED") {
            return failWith(409, "execution cannot be recorded before acceptance");
          }
          const actionType = current.action.recommended_action.action_type;
          const closes = body.execution_status === "SUCCEEDED" && actionType === "continue";
          return store(
            withCurrent(
              session,
              {
                ...current.action,
                execution_status: body.execution_status,
                executed_action:
                  body.execution_status === "UNSUPPORTED" ? null : body.executed_action,
              },
              closes ? "CLOSED" : "AWAITING_ATTEMPT",
            ),
          );
        }
        if (verb === "attempts") {
          if (session.status !== "AWAITING_ATTEMPT") {
            return failWith(409, "append requires AWAITING_ATTEMPT");
          }
          if (
            body.evaluation.assignment_id !== session.assignment_id ||
            body.evaluation.content_id !== session.content_id ||
            body.guidance.canonical_revision_id !== session.canonical_revision_id
          ) {
            return failWith(409, "append identity does not match session");
          }
          const index = session.attempts.length;
          return store({
            ...session,
            status: "AWAITING_ACTION",
            attempts: [
              ...session.attempts,
              attemptOf(body.evaluation, body.guidance, body.attempt_id, index),
            ],
            current_attempt_index: index,
          });
        }
        if (verb === "transition") {
          if (["CLOSED", "TRANSITIONED", "ABORTED"].includes(session.status)) {
            return failWith(409, "transition is not valid for a terminal session");
          }
          return store({ ...session, status: "TRANSITIONED" });
        }
        return failWith(400, `unrouted verb ${verb}`);
      },
    },
  };
}

function scoreFilesAt(net, demoId, revisionId) {
  const artifact = (name) =>
    JSON.parse(readFileSync(repoPath(`web/mvp1/projections/${demoId}/${name}.json`), "utf-8"));
  if (revisionId === null) {
    for (const name of ["canonical_revision", "tab", "notation"]) {
      net.unroute(`GET projections/${demoId}/${name}.json`);
    }
    return;
  }
  net.route(`GET projections/${demoId}/canonical_revision.json`, {
    ...artifact("canonical_revision"),
    revision_id: revisionId,
  });
  for (const kind of ["tab", "notation"]) {
    const envelope = artifact(kind);
    net.route(`GET projections/${demoId}/${kind}.json`, {
      ...envelope,
      canonical_revision_id: revisionId,
      payload: { ...envelope.payload, canonical_revision_id: revisionId },
    });
  }
}

export async function runCertification() {
  const legs = Object.values(SCENARIOS.legs).filter((leg) => leg.lesson === LESSON_A);
  const secondLessonLeg = Object.values(SCENARIOS.legs).find((leg) => leg.lesson === LESSON_B);
  const guided = lifecycleServer();
  const served = [];
  const consoleErrors = [];

  const net = createFetch({
    "POST /api/education/begin_lesson": {},
    "GET /api/v1/lessons/*": { media: [] },
    "POST /api/performance/arm": {},
    "POST /api/performance/start": {},
    "POST /api/performance/message": {},
    "POST /api/performance/stop": () => ({
      status: "complete",
      raw_capture: { session_id: `capture-${served.length}` },
      observed_events: [{ observed_event_id: "obs-1", midi_note: 60, onset_ms: 0, velocity: 90 }],
    }),
    // The evaluator's own answers, keyed to whichever lesson is loaded, in the
    // order the certified flow uses them.
    "POST /api/education/evaluate": ({ body }) => {
      const pool = body.content_id === LESSON_B ? [secondLessonLeg] : legs;
      const used = served.filter((name) => pool.some((leg) => leg.leg === name)).length;
      const leg = pool[Math.min(used, pool.length - 1)];
      served.push(leg.leg);
      return leg.response;
    },
    ...guided.routes,
  });

  const env = installBrowserGlobals({ search: "?fakeMidi=1", fetchImpl: net.fetch });
  const el = env.element;
  const originalError = console.error;
  console.error = (...args) => consoleErrors.push(args.map(String).join(" "));

  await import("../app.js");
  const app = env.window.__mvp2a;
  await waitFor(() => app.state.payload, { label: "the first lesson" });
  app.scheduler.stop();

  const perform = async () => {
    await el("btnMidiPermission").fire("click");
    el("midiDevice").value = el("midiDevice").children[0]?.value ?? "";
    await el("btnArm").fire("click");
    await el("btnStartAttempt").fire("click");
    await el("btnFakeMidi").fire("click");
    await el("btnStopAttempt").fire("click");
  };
  const switchTo = async (demoId) => {
    el("demoSelect").value = demoId;
    await el("demoSelect").fire("change", { target: el("demoSelect") });
  };
  const snapshot = (label) => {
    const session = app.guidedSessions.activeSession ?? app.guidedSessions.session;
    const attempt = session?.attempts?.[session.current_attempt_index ?? 0];
    return {
      label,
      session_status: session?.status ?? null,
      attempt_count: session?.attempts?.length ?? 0,
      current_attempt_index: session?.current_attempt_index ?? null,
      recommended_action: attempt?.action?.recommended_action?.action_type ?? null,
      action_disposition: attempt?.action?.action_disposition ?? null,
      execution_status: attempt?.action?.execution_status ?? null,
      history_rendered: Number(el("guidedSessionHistory").dataset.attemptCount ?? 0),
      accept_enabled: !el("btnAcceptGuidance").disabled,
      apply_enabled: !el("btnApplyPrimary").hidden && !el("btnApplyPrimary").disabled,
      transport_rate: app.transport.playbackRate,
      transport_loop: app.transport.loop
        ? {
            start: Number(app.transport.loop.startSeconds.toFixed(6)),
            end: Number(app.transport.loop.endSeconds.toFixed(6)),
          }
        : null,
    };
  };

  const steps = [];
  const immutability = [];
  let attemptZeroFrozen = null;

  for (const [index, leg] of legs.entries()) {
    await perform();
    await waitFor(() => (app.guidedSessions.session?.attempts?.length ?? 0) === index + 1, {
      label: `attempt ${index}`,
    });
    steps.push(snapshot(`${leg.leg}:evaluated`));
    if (attemptZeroFrozen !== null) {
      // Immutability is a claim about an attempt that is no longer current.
      // Attempt 0 changes through its own Accept and Apply, legitimately;
      // what must never change is what it looks like afterwards.
      immutability.push({
        after_attempt: index,
        attempt_0_unchanged:
          JSON.stringify(app.guidedSessions.session.attempts[0]) === attemptZeroFrozen,
      });
    }

    const rateBefore = app.transport.playbackRate;
    const loopBefore = JSON.stringify(app.transport.loop);
    await el("btnAcceptGuidance").fire("click");
    const accepted = snapshot(`${leg.leg}:accepted`);
    accepted.transport_untouched_by_accept =
      app.transport.playbackRate === rateBefore && JSON.stringify(app.transport.loop) === loopBefore;
    steps.push(accepted);

    await el("btnApplyPrimary").fire("click");
    steps.push(snapshot(`${leg.leg}:applied`));
    if (index === 0) {
      attemptZeroFrozen = JSON.stringify(app.guidedSessions.session.attempts[0]);
    }
  }

  const closed = app.guidedSessions.session;
  const identityChain = closed.attempts.map((attempt, index) => {
    const leg = legs[index];
    const evaluation = leg.response.evaluation;
    const guidance = leg.response.guidance;
    return {
      attempt_index: index,
      attempt_id: attempt.attempt_id,
      performance_session_id: attempt.performance_session_id,
      matches_guidance_performance:
        attempt.performance_session_id === evaluation.performance_session_id,
      evaluation_digest: attempt.evaluation_digest,
      matches_evaluation_digest: attempt.evaluation_digest === evaluation.evaluation_digest,
      guidance_digest: attempt.guidance_digest,
      matches_guidance_digest: attempt.guidance_digest === guidance.guidance_digest,
      canonical_revision_id: attempt.canonical_revision_id,
      recommended_action: attempt.action.recommended_action.action_type,
      action_disposition: attempt.action.action_disposition,
      execution_status: attempt.action.execution_status,
    };
  });

  // Fail-closed 1: the same lesson re-cut at another canonical revision.
  scoreFilesAt(net, LESSON_A, RECUT_REVISION);
  await switchTo(LESSON_A);
  const revisionFailClosed = {
    session_preserved: app.guidedSessions.session !== null,
    active_session: app.guidedSessions.activeSession,
    accept_enabled: !el("btnAcceptGuidance").disabled,
    apply_enabled: !el("btnApplyPrimary").hidden && !el("btnApplyPrimary").disabled,
    history_rendered: Number(el("guidedSessionHistory").dataset.attemptCount ?? 0),
  };
  scoreFilesAt(net, LESSON_A, null);

  // Fail-closed 2: a lesson switch out of an open session.
  await switchTo(LESSON_B);
  await perform();
  await waitFor(() => app.guidedSessions.session?.content_id === LESSON_B, {
    label: "a session on the second lesson",
  });
  const openOnB = app.guidedSessions.session.session_id;
  await switchTo(LESSON_A);
  const lessonTransition = {
    previous_session_id: openOnB,
    previous_session_status: guided.sessions.get(openOnB)?.status ?? null,
    new_lesson_session: app.guidedSessions.session,
    history_rendered: Number(el("guidedSessionHistory").dataset.attemptCount ?? 0),
  };

  console.error = originalError;
  env.restore();

  const failedRequests = net.calls.filter((call) => call.path.startsWith("/api/") === false).length;
  return {
    witness: "reproducible (in-repo browser harness driving web/mvp1/app.js)",
    proves: ["application orchestration", "real UI event path", "deterministic guided flow"],
    does_not_prove: ["DOM rendering", "visual presentation"],
    scenario_source: "docs/mvp2/do015_artifacts/certification_scenarios.json",
    node_version: process.version,
    platform: process.platform,
    lesson: LESSON_A,
    legs_served: served,
    session_id: closed.session_id,
    final_status: closed.status,
    attempt_ids: closed.attempts.map((attempt) => attempt.attempt_id),
    canonical_revision_id: closed.canonical_revision_id,
    steps,
    attempt_0_immutable: immutability,
    identity_chain: identityChain,
    revision_fail_closed: revisionFailClosed,
    lesson_transition: lessonTransition,
    console_errors: consoleErrors,
    unrouted_or_disk_requests: failedRequests,
  };
}

if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href.replace(/\\/g, "/")) {
  const summary = await runCertification();
  const out = repoPath("docs/mvp2/do015_artifacts/browser_smoke_summary.json");
  writeFileSync(out, `${JSON.stringify(summary, null, 2)}\n`, "utf-8");
  console.log(`wrote ${out}`);
  console.log(`final status ${summary.final_status}, attempts ${summary.attempt_ids.length}`);
}
