/**
 * Whole-page test of `loadSession()` when a guided session cannot be
 * transitioned (DO-015 Stage 7).
 *
 * This is the path where stale state and what the page shows can come apart:
 * the guided session survives on purpose, the lesson underneath it has already
 * changed, and every control still points at the controller. Module-level
 * tests cannot see that disagreement, so this boots `app.js` and drives it
 * through the page's own buttons.
 *
 * Note that the tests share one imported `app.js`, since a module is evaluated
 * once per process. They run in order and hand the page on to each other, the
 * way a session in front of a learner does.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { createFetch, failWith, installBrowserGlobals, waitFor } from "./browser_harness.js";

const LESSON_A = "ascending_scale";
const LESSON_B = "descending_scale";

const SLOW_DOWN = {
  schema_version: "1.0.0",
  action_type: "slow_down",
  target_rate: 0.75,
  message_key: "action.slow_down",
  reason_finding_ids: [],
};

/**
 * A guided-session endpoint following the Stage 2 lifecycle.
 *
 * The Python service and its tests remain the authority for these rules; this
 * only has to be right enough for the browser to be driven through them.
 */
function guidedSessionEndpoint() {
  const sessions = new Map();
  let transitionFails = false;
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
  return {
    sessions,
    failTransitions: (on) => {
      transitionFails = on;
    },
    routes: {
      "POST /api/education/guided-sessions": ({ body }) => {
        const session = {
          schema_version: "1.0.0",
          policy_version: "guided-practice-session-v1",
          session_id: body.session_id,
          assignment_id: body.evaluation.assignment_id,
          content_id: body.evaluation.content_id,
          canonical_revision_id: body.guidance.canonical_revision_id,
          status: "AWAITING_ACTION",
          attempts: [attemptOf(body.evaluation, body.guidance, body.attempt_id, 0)],
          current_attempt_index: 0,
          session_digest: "sha256:session",
          provenance: [],
        };
        sessions.set(session.session_id, session);
        return session;
      },
      "POST /api/education/guided-sessions/*": ({ path, body }) => {
        const [sessionId, verb] = path
          .replace("/api/education/guided-sessions/", "")
          .split("/");
        const session = sessions.get(decodeURIComponent(sessionId));
        if (!session) return failWith(404, "unknown session_id");
        if (verb === "disposition") {
          const current = session.attempts[session.attempts.length - 1];
          const updated = {
            ...session,
            status: body.disposition === "DECLINED" ? "AWAITING_ATTEMPT" : "AWAITING_ACTION",
            attempts: [
              ...session.attempts.slice(0, -1),
              {
                ...current,
                action: {
                  ...current.action,
                  action_disposition: body.disposition,
                  execution_status: body.disposition === "ACCEPTED" ? "PENDING" : "NOT_REQUESTED",
                },
              },
            ],
          };
          sessions.set(session.session_id, updated);
          return updated;
        }
        if (verb === "transition") {
          if (transitionFails) return failWith(409, "transition requires an open session");
          const updated = { ...session, status: "TRANSITIONED" };
          sessions.set(session.session_id, updated);
          return updated;
        }
        return failWith(400, `unrouted guided-session verb ${verb}`);
      },
    },
  };
}

const guided = guidedSessionEndpoint();
const net = createFetch({
  "POST /api/education/begin_lesson": {},
  "GET /api/v1/lessons/*": { media: [] },
  "POST /api/performance/arm": {},
  "POST /api/performance/start": {},
  "POST /api/performance/message": {},
  "POST /api/performance/stop": () => ({
    status: "complete",
    raw_capture: { session_id: `performance-${net.calls.length}` },
    observed_events: [
      { observed_event_id: "obs-1", midi_note: 60, onset_ms: 0, velocity: 90 },
    ],
  }),
  // Echoes the lesson identity back the way the real evaluator does, so the
  // session's pins are the loaded lesson's rather than a fixture's.
  "POST /api/education/evaluate": ({ body }) => ({
    evaluation: {
      schema_version: "1.0.0",
      assignment_id: body.assignment_id,
      content_id: body.content_id,
      performance_session_id: body.performance_session_id,
      evaluation_digest: `sha256:eval-${body.content_id}`,
      findings: [],
      summary: { actionable_finding_count: 0, focus_ranges: [] },
      primary_next_action: SLOW_DOWN,
    },
    guidance: {
      schema_version: "1.0.0",
      canonical_revision_id: body.canonical_revision_id,
      guidance_digest: `sha256:guide-${body.content_id}`,
      items: [],
      next_action: SLOW_DOWN,
    },
    messages: { "action.slow_down": "Slow down" },
    hardware_status: {
      midi_input: "UNVERIFIED_PHYSICAL_MIDI_INPUT",
      audio_output: "UNVERIFIED_AUDIO_OUTPUT",
    },
  }),
  ...guided.routes,
});

// `?fakeMidi=1` is the page's own deterministic MIDI affordance, so an attempt
// can be played here exactly as the Arm / Start / Perform / Stop flow plays it.
const env = installBrowserGlobals({ search: "?fakeMidi=1", fetchImpl: net.fetch });
const el = env.element;
await import("../app.js");
const app = env.window.__mvp2a;
await waitFor(() => app.state.payload, { label: "the first lesson to load" });
// Nothing here needs the audio clock, and leaving it running holds the process.
app.scheduler.stop();

const appendCalls = () => net.calls.filter((call) => call.path.endsWith("/attempts"));
const createCalls = () =>
  net.calls.filter(
    (call) => call.method === "POST" && call.path === "/api/education/guided-sessions",
  );
const historyText = () =>
  el("guidedSessionHistory").children.map((node) => node.textContent);

/** Play one attempt through the page's buttons. */
async function performAttempt() {
  await el("btnMidiPermission").fire("click");
  el("midiDevice").value = el("midiDevice").children[0]?.value ?? "";
  await el("btnArm").fire("click");
  await el("btnStartAttempt").fire("click");
  await el("btnFakeMidi").fire("click");
  await el("btnStopAttempt").fire("click");
}

const artifact = (path) =>
  JSON.parse(readFileSync(fileURLToPath(new URL(`../${path}`, import.meta.url)), "utf-8"));

/**
 * Serve one lesson's score at a different canonical revision.
 *
 * All three files have to agree or the score coordinator refuses the lesson
 * outright, which would prove nothing about pinning.
 */
function serveRevision(demoId, revisionId) {
  const revision = { ...artifact(`projections/${demoId}/canonical_revision.json`) };
  revision.revision_id = revisionId;
  net.route(`GET projections/${demoId}/canonical_revision.json`, revision);
  for (const kind of ["tab", "notation"]) {
    const envelope = artifact(`projections/${demoId}/${kind}.json`);
    net.route(`GET projections/${demoId}/${kind}.json`, {
      ...envelope,
      canonical_revision_id: revisionId,
      payload: { ...envelope.payload, canonical_revision_id: revisionId },
    });
  }
}

function serveOriginalRevision(demoId) {
  for (const name of ["canonical_revision", "tab", "notation"]) {
    net.unroute(`GET projections/${demoId}/${name}.json`);
  }
}

async function switchLessonTo(demoId) {
  el("demoSelect").value = demoId;
  await el("demoSelect").fire("change", { target: el("demoSelect") });
}

let sessionBeforeSwitch = null;

test("an attempt on the first lesson opens a guided session the controls can act on", async () => {
  assert.equal(app.state.playback.content_id, LESSON_A);
  await performAttempt();
  await waitFor(() => app.guidedSessions.session, { label: "the guided session" });
  const session = app.guidedSessions.session;
  assert.equal(session.content_id, LESSON_A);
  assert.equal(session.status, "AWAITING_ACTION");
  assert.equal(el("btnAcceptGuidance").disabled, false);
  assert.equal(el("guidedSessionHistory").dataset.attemptCount, "1");

  await el("btnAcceptGuidance").fire("click");
  // Accepted and not yet applied: this is the state with the most to lose if a
  // lesson switch leaves the page pointing at it.
  assert.equal(app.guidedSessions.activeSession.attempts[0].action.action_disposition, "ACCEPTED");
  assert.equal(el("btnApplyPrimary").hidden, false);
  assert.equal(el("btnApplyPrimary").disabled, false);
  sessionBeforeSwitch = JSON.stringify(app.guidedSessions.session);
});

test("a lesson switch whose transition fails keeps the session and stands the page down", async () => {
  guided.failTransitions(true);
  const attemptsBefore = appendCalls().length;
  await switchLessonTo(LESSON_B);

  // The lesson did change: this is not a half-loaded page.
  assert.equal(app.state.playback.content_id, LESSON_B);

  // The session the server still holds is still here, unaltered.
  assert.equal(JSON.stringify(app.guidedSessions.session), sessionBeforeSwitch);
  assert.equal(app.guidedSessions.session.attempts.length, 1);
  assert.equal(app.guidedSessions.session.content_id, LESSON_A);
  assert.equal(app.guidedSessions.terminalSession, null);

  // And it acts on nothing, because the lesson it belongs to is gone.
  assert.equal(app.guidedSessions.activeSession, null);
  assert.equal(el("btnAcceptGuidance").disabled, true);
  assert.equal(el("btnDeclineGuidance").disabled, true);
  assert.equal(el("btnApplyPrimary").hidden, true);
  assert.equal(el("btnApplyPrimary").disabled, true);

  // Lesson B has no history of its own, and the failure is on screen rather
  // than only in a variable.
  assert.equal(el("guidedSessionHistory").dataset.attemptCount, "0");
  assert.equal(el("guidedSessionHistory").dataset.appendStatus, "FAILED");
  assert.deepEqual(historyText(), [
    "No guided attempts yet.",
    "transition requires an open session",
  ]);
  assert.equal(el("resultsStatus").textContent, "transition requires an open session");
  const diagnostics = env.window.__masDiagnostics.guidance();
  assert.equal(diagnostics.lastProgressionPhase, "transition");
  assert.equal(diagnostics.lastAppendStatus, "FAILED");
  assert.equal(diagnostics.guidedSessionId, null);

  // Nothing was recorded against the old session on the way out.
  assert.equal(appendCalls().length, attemptsBefore);
});

test("the lesson picker's status line does not have to carry the failure", () => {
  // It says what it did -- the lesson loaded -- and overwrites loadSession's
  // message as soon as it returns. The panel is where the guided-session
  // failure has to survive, and the assertions above are what hold it there.
  assert.equal(el("statusLine").textContent, `Loaded ${LESSON_B}`);
  assert.equal(el("guidedSessionHistory").dataset.appendStatus, "FAILED");
});

test("the new lesson's attempt is refused rather than recorded on the old session", async () => {
  const createsBefore = createCalls().length;
  await performAttempt();
  await waitFor(() => el("resultsStatus").textContent.includes("does not match"), {
    label: "the mismatch to be reported",
  });

  // The stale session is neither appended to nor replaced by lesson B's work.
  assert.equal(appendCalls().length, 0);
  assert.equal(createCalls().length, createsBefore);
  assert.equal(JSON.stringify(app.guidedSessions.session), sessionBeforeSwitch);
  assert.match(el("resultsStatus").textContent, /assignment_id does not match/);
  assert.equal(el("guidedSessionHistory").dataset.attemptCount, "0");
  assert.equal(env.window.__masDiagnostics.guidance().lastProgressionPhase, "append");
});

test("returning to the lesson it belongs to hands the preserved session back", async () => {
  // The transition never happened, so the session is still open on lesson A.
  // Coming back to A makes it the learner's again -- and the panel has to say
  // so, because the controls do.
  await switchLessonTo(LESSON_A);
  assert.equal(app.guidedSessions.activeSession, app.guidedSessions.session);
  assert.equal(el("btnApplyPrimary").hidden, false);
  assert.equal(el("btnApplyPrimary").disabled, false);
  assert.equal(el("guidedSessionHistory").dataset.attemptCount, "1");
  assert.equal(el("guidedSessionHistory").dataset.sessionStatus, "AWAITING_ACTION");
  const [attempt] = el("guidedSessionHistory").children.filter(
    (node) => node.className === "guided-history",
  )[0].children;
  assert.equal(attempt.dataset.current, "true");
  assert.equal(attempt.dataset.actionable, "true");
  assert.equal(attempt.dataset.disposition, "ACCEPTED");
  // Nothing was re-created or re-recorded to get it back.
  assert.equal(appendCalls().length, 0);
  assert.equal(JSON.stringify(app.guidedSessions.session), sessionBeforeSwitch);
});

test("once the transition succeeds the old session retires and the next lesson starts clean", async () => {
  guided.failTransitions(false);
  const staleSessionId = app.guidedSessions.session.session_id;
  await switchLessonTo(LESSON_B);

  assert.equal(guided.sessions.get(staleSessionId).status, "TRANSITIONED");
  assert.equal(app.guidedSessions.session, null);
  assert.equal(app.guidedSessions.terminalSession.status, "TRANSITIONED");
  assert.equal(app.guidedSessions.terminalSession.attempts.length, 1);
  assert.equal(el("guidedSessionHistory").dataset.attemptCount, "0");
  assert.equal(el("guidedSessionHistory").dataset.appendStatus, undefined);
  assert.deepEqual(historyText(), ["No guided attempts yet."]);

  // And this lesson's first attempt opens a session of its own.
  const createsBefore = createCalls().length;
  await performAttempt();
  await waitFor(() => app.guidedSessions.session, { label: "the new guided session" });
  assert.equal(createCalls().length, createsBefore + 1);
  assert.equal(appendCalls().length, 0);
  assert.equal(app.guidedSessions.session.content_id, LESSON_B);
  assert.notEqual(app.guidedSessions.session.session_id, staleSessionId);
  assert.equal(el("guidedSessionHistory").dataset.attemptCount, "1");
});

test.after(() => {
  app.scheduler.stop();
  env.restore();
});

test("the same lesson at another canonical revision is not the session's lesson", async () => {
  const session = app.guidedSessions.session;
  // The pin under test has to be a real revision, or this proves nothing.
  assert.match(session.canonical_revision_id, /^rev-[0-9a-f]+$/);
  assert.equal(app.guidedSessions.activeSession, session);
  assert.equal(el("btnAcceptGuidance").disabled, false);
  const recorded = JSON.stringify(session);
  const guidedPosts = () =>
    net.calls.filter(
      (call) => call.method === "POST" && call.path.startsWith("/api/education/guided-sessions"),
    ).length;
  const postsBefore = guidedPosts();

  // The lesson is re-cut: same assignment, same content, new revision.
  serveRevision(LESSON_B, "rev-0000000000000000second0cut");
  await switchLessonTo(LESSON_B);

  assert.equal(app.state.playback.content_id, LESSON_B);
  assert.equal(JSON.stringify(app.guidedSessions.session), recorded);
  assert.equal(app.guidedSessions.activeSession, null);
  assert.equal(el("btnAcceptGuidance").disabled, true);
  assert.equal(el("btnDeclineGuidance").disabled, true);
  assert.equal(el("btnApplyPrimary").hidden, true);
  assert.equal(el("btnApplyPrimary").disabled, true);
  assert.equal(el("guidedSessionHistory").dataset.attemptCount, "0");

  // Pressing them anyway records nothing: the guard is the session, not the
  // disabled attribute.
  await el("btnAcceptGuidance").fire("click");
  await el("btnDeclineGuidance").fire("click");
  await el("btnApplyPrimary").fire("click");
  assert.equal(guidedPosts(), postsBefore);
  assert.equal(appendCalls().length, 0);
  assert.equal(JSON.stringify(app.guidedSessions.session), recorded);
});

test("restoring the lesson's own revision hands the preserved session back", async () => {
  const recorded = JSON.stringify(app.guidedSessions.session);
  serveOriginalRevision(LESSON_B);
  await switchLessonTo(LESSON_B);

  assert.equal(app.guidedSessions.activeSession, app.guidedSessions.session);
  assert.equal(JSON.stringify(app.guidedSessions.session), recorded);
  assert.equal(el("btnAcceptGuidance").disabled, false);
  assert.equal(el("guidedSessionHistory").dataset.attemptCount, "1");
  assert.equal(appendCalls().length, 0);
});
