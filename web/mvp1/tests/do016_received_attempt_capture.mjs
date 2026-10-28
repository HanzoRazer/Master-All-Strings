/**
 * Browser witness for DO-016 Stage 8.
 *
 * MIDI is injected through navigator.requestMIDIAccess before the page boots.
 * That is not a physical input. Audio output is not certified either.
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const DEFAULT_CHROME = "/usr/local/bin/google-chrome";
const DEFAULT_PUPPETEER = "/tmp/inbox-smoke/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js";
const chromeExecutable = process.env.DO016_CHROME_EXECUTABLE || DEFAULT_CHROME;
const puppeteerModule = process.env.DO016_PUPPETEER_MODULE || DEFAULT_PUPPETEER;
const launchArgs = ["--no-sandbox", "--disable-dev-shm-usage", "--autoplay-policy=no-user-gesture-required"];
const imported = await import(pathToFileURL(puppeteerModule).href);
const puppeteer = imported.default?.launch ? imported.default : imported;

const base = process.argv[2];
const output = process.argv[3];
const deliveryId = process.argv[4];
mkdirSync(output, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: chromeExecutable,
  headless: "new",
  args: launchArgs,
});
const browserVersion = await browser.version();

const notes = [];
let failures = 0;
const counts = { begin: 0, message: 0, finish: 0, cancel: 0, guided: 0, performance: 0 };
const attempts = [];

function check(name, ok, detail = "") {
  notes.push(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failures += 1;
}

function tally(url) {
  if (url.includes("/api/education/guided-sessions")) counts.guided += 1;
  if (url.includes("/api/performance/")) counts.performance += 1;
  if (url.endsWith("/api/education/lesson-practice-attempts")) counts.begin += 1;
  if (url.endsWith("/api/education/lesson-practice-attempt-messages")) counts.message += 1;
  if (url.endsWith("/api/education/lesson-practice-attempt-finishes")) counts.finish += 1;
  if (url.endsWith("/api/education/lesson-practice-attempt-cancellations")) counts.cancel += 1;
}

async function installMidi(page) {
  await page.evaluateOnNewDocument(() => {
    const input = {
      id: "injected-stage8-input",
      name: "Injected Stage 8 input",
      state: "connected",
      onmidimessage: null,
    };
    const access = {
      inputs: new Map([[input.id, input]]),
      onstatechange: null,
    };
    navigator.requestMIDIAccess = async () => access;
    window.__emitMidi = (bytes, timeStamp) => {
      if (typeof input.onmidimessage !== "function") return false;
      input.onmidimessage({
        timeStamp: timeStamp ?? performance.now(),
        data: Uint8Array.from(bytes),
      });
      return true;
    };
    window.__midiInjected = true;
  });
}

function watch(page, label, tallyRequests = true) {
  page.setDefaultTimeout(60000);
  page.on("console", (message) => {
    if (message.type() === "error") notes.push(`console ${label}: ${message.text()}`);
  });
  page.on("pageerror", (error) => {
    failures += 1;
    notes.push(`FAIL pageerror ${label} — ${error.message}`);
  });
  if (tallyRequests) {
    page.on("request", (request) => {
      tally(request.url());
    });
  }
  page.on("response", async (response) => {
    if (!response.url().endsWith("/api/education/lesson-practice-attempts")) return;
    if (response.status() !== 201) return;
    try {
      const body = await response.json();
      attempts.push({
        label,
        attempt_id: body.attempt_id,
        capture_id: body.capture_id,
        performance_session_id: body.performance_session_id,
        revision_id: body.preparation?.score?.canonical_revision?.revision_id ?? null,
      });
    } catch (error) {
      notes.push(`begin body ${label}: ${error.message}`);
    }
  });
}

async function openPractice(page) {
  const query = new URLSearchParams({ delivery_id: deliveryId });
  await page.goto(`${base}/lesson-practice.html?${query}`, { waitUntil: "networkidle0" });
  await page.waitForFunction(() => /Paused/.test(document.querySelector("#status")?.textContent || ""));
}

async function startAttempt(page) {
  await page.click("#btn-enable-midi");
  await page.waitForFunction(() => /ready/.test(document.querySelector("#midi-status")?.textContent || ""));
  await page.click("#btn-start-attempt");
  await page.waitForFunction(() => document.querySelector("#attempt-status")?.textContent === "Capturing.");
}

async function text(page, selector) {
  return page.$eval(selector, (node) => node.textContent || "");
}

const contextA = await browser.createBrowserContext();
const contextB = await browser.createBrowserContext();
const pageA = await contextA.newPage();
const pageB = await contextB.newPage();
watch(pageA, "evaluated");
watch(pageB, "interrupted");
await installMidi(pageA);
await installMidi(pageB);
await pageA.setViewport({ width: 1280, height: 900 });
await pageB.setViewport({ width: 1280, height: 900 });

try {
  await openPractice(pageA);
  await openPractice(pageB);
  const titleA = await text(pageA, "#lesson-title");
  const titleB = await text(pageB, "#lesson-title");
  check("custom lesson title", titleA === "Stage 8 Received Etude" && titleB === titleA, titleA);
  check(
    "reference practice is available before an attempt",
    await pageA.$eval("#btn-play", (node) => node.disabled === false),
  );
  const injected = await pageA.evaluate(() => window.__midiInjected === true);
  check("MIDI is injected before boot", injected);

  await startAttempt(pageA);
  const emitted = await pageA.evaluate(() => {
    const now = performance.now();
    const notes = [
      [0x90, 64, 80],
      [0x90, 67, 80],
      [0x90, 64, 0],
      [0x80, 67, 0],
      [0x90, 72, 90],
      [0x80, 72, 0],
    ];
    return notes.map((bytes, index) => window.__emitMidi(bytes, now + index + 1));
  });
  check("injected notes were delivered to the connected input", emitted.every(Boolean));
  await startAttempt(pageB);
  for (let step = 0; step < 40 && attempts.length < 2; step += 1) {
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  const ids = attempts.map((item) => item.attempt_id);
  check("two contexts receive two attempt ids", new Set(ids).size === 2, ids.join(", "));
  check(
    "the other context is still capturing",
    (await text(pageB, "#attempt-status")) === "Capturing.",
    await text(pageB, "#attempt-status"),
  );
  check(
    "the other context has no evaluation",
    await pageB.$eval("#attempt-feedback", (node) => node.hidden || node.textContent === ""),
  );
  await pageB.click("#btn-cancel-attempt");
  let cancelStatus = "";
  for (let step = 0; step < 40; step += 1) {
    cancelStatus = await text(pageB, "#attempt-status");
    if (cancelStatus === "The attempt was cancelled." || cancelStatus === "Interrupted." || cancelStatus.includes("not confirmed")) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  const interrupted = await text(pageB, "#attempt-feedback");
  check("cancellation shows interruption", cancelStatus === "The attempt was cancelled." || cancelStatus === "Interrupted.", cancelStatus);
  check("interruption has no evaluation claim", interrupted.includes("No evaluation was produced.") && !interrupted.includes("Matched"));

  await pageA.waitForFunction(() => {
    const status = document.querySelector("#attempt-status")?.textContent || "";
    const count = document.querySelector("#attempt-count")?.textContent || "";
    return count.includes("Acknowledged messages: 6")
      || status === "Evaluated."
      || /Interrupted|not confirmed|rejected/.test(status);
  });
  check(
    "six notes were acknowledged",
    (await text(pageA, "#attempt-count")).includes("Acknowledged messages: 6"),
    await text(pageA, "#attempt-status"),
  );
  const finishEnabled = await pageA.$eval("#btn-finish-attempt", (node) => node.disabled === false);
  if (finishEnabled) await pageA.click("#btn-finish-attempt");
  await pageA.waitForFunction(() => {
    const status = document.querySelector("#attempt-status")?.textContent || "";
    return status === "Evaluated." || status.includes("not confirmed") || status.includes("rejected");
  });
  const feedback = await text(pageA, "#attempt-feedback");
  check("evaluation is shown", (await text(pageA, "#attempt-status")) === "Evaluated.", await text(pageA, "#attempt-status"));
  check("matched missing and extra counts are shown", /Matched:/.test(feedback) && /Missing:/.test(feedback) && /Extra:/.test(feedback), feedback.slice(0, 240));
  check("server hardware status stays unverified", feedback.includes("UNVERIFIED_PHYSICAL_MIDI_INPUT") && feedback.includes("UNVERIFIED_AUDIO_OUTPUT"));
  check("feedback does not claim lesson completion", !/lesson complete|mastered/i.test(feedback));
  if (feedback.includes("Recommendation: continue")) {
    check(
      "continue means no immediate repetition",
      feedback.includes("No immediate repetition is required under this attempt policy."),
    );
  }
  await pageA.screenshot({ path: `${output}/01-evaluated-desktop.png`, fullPage: true });
  await pageA.setViewport({ width: 390, height: 844 });
  await pageA.screenshot({ path: `${output}/02-evaluated-narrow.png`, fullPage: true });
  const controlHeight = await pageA.$eval("#btn-start-attempt", (node) => node.getBoundingClientRect().height);
  check("narrow attempt control meets the tap height", controlHeight >= 40, String(controlHeight));
  await pageB.screenshot({ path: `${output}/03-interrupted-desktop.png`, fullPage: true });

  const contextC = await browser.createBrowserContext();
  const pageC = await contextC.newPage();
  watch(pageC, "append-failure", false);
  await installMidi(pageC);
  await pageC.setViewport({ width: 1280, height: 900 });
  let aborted = false;
  await pageC.setRequestInterception(true);
  pageC.on("request", (request) => {
    tally(request.url());
    if (!aborted && request.url().endsWith("/api/education/lesson-practice-attempt-messages")) {
      aborted = true;
      request.abort("failed").catch(() => {});
      return;
    }
    request.continue().catch(() => {});
  });
  const finishesBefore = counts.finish;
  await openPractice(pageC);
  await startAttempt(pageC);
  await pageC.evaluate(() => window.__emitMidi([0x90, 64, 80], performance.now() + 5));
  let failedStatus = "";
  for (let step = 0; step < 40; step += 1) {
    failedStatus = await text(pageC, "#attempt-status");
    if (
      failedStatus === "A captured message was not accepted."
      || failedStatus === "Interrupted."
      || failedStatus.includes("not confirmed")
      || failedStatus.includes("could not be checked")
    ) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  const failed = await text(pageC, "#attempt-feedback");
  check(
    "an aborted append does not evaluate",
    failedStatus === "A captured message was not accepted."
      || failedStatus === "Interrupted."
      || failedStatus.includes("not confirmed"),
    failedStatus,
  );
  check("aborted append shows no matched count", !failed.includes("Matched:"), failed.slice(0, 180));
  check("aborted append sends no finish", counts.finish === finishesBefore, String(counts.finish - finishesBefore));
  check("the aborted message was intercepted", aborted);
  await pageC.screenshot({ path: `${output}/04-append-failure.png`, fullPage: true });
  await contextC.close();

  // Simulated 404. This driver does not stop or restart the server. The
  // integration witness is what exercises a real second process.
  const contextD = await browser.createBrowserContext();
  const pageD = await contextD.newPage();
  watch(pageD, "unknown-attempt", false);
  await installMidi(pageD);
  await pageD.setViewport({ width: 1280, height: 900 });
  let lostFinish = false;
  await pageD.setRequestInterception(true);
  pageD.on("request", (request) => {
    tally(request.url());
    if (!lostFinish && request.url().endsWith("/api/education/lesson-practice-attempt-finishes")) {
      lostFinish = true;
      request.respond({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: "unknown_attempt" }),
      }).catch(() => {});
      return;
    }
    request.continue().catch(() => {});
  });
  await openPractice(pageD);
  await startAttempt(pageD);
  await pageD.evaluate(() => window.__emitMidi([0x90, 64, 80], performance.now() + 5));
  await pageD.waitForFunction(() => (
    document.querySelector("#attempt-count")?.textContent || ""
  ).includes("Acknowledged messages: 1"));
  await pageD.click("#btn-finish-attempt");
  await pageD.waitForFunction(() => document.querySelector("#btn-finish-attempt")?.disabled === true
    && !/Finishing/.test(document.querySelector("#attempt-status")?.textContent || ""));
  const lostStatus = await text(pageD, "#attempt-status");
  const lostState = await pageD.evaluate(() => ({
    feedback: document.querySelector("#attempt-feedback").textContent,
    retryHidden: document.querySelector("#btn-retry-finish").hidden,
    startEnabled: !document.querySelector("#btn-start-attempt").disabled,
    playEnabled: !document.querySelector("#btn-play").disabled,
    refreshEnabled: !document.querySelector("#refresh-lesson").disabled,
  }));
  notes.push("NOTE the unknown-attempt finish is a simulated 404, not a restarted server.");
  check("a lost attempt says the server no longer has it", lostStatus.includes("no longer has this attempt"), lostStatus);
  check("a lost attempt claims no evaluation", !lostState.feedback.includes("Matched:"), lostState.feedback.slice(0, 180));
  check("a lost attempt offers no finish retry", lostState.retryHidden);
  check(
    "a lost attempt returns to reference practice",
    lostState.playEnabled && lostState.refreshEnabled,
    JSON.stringify(lostState),
  );
  check("a lost attempt allows a new attempt", lostState.startEnabled);
  await pageD.screenshot({ path: `${output}/05-unknown-attempt.png`, fullPage: true });
  await pageD.click("#btn-start-attempt");
  await pageD.waitForFunction(() => document.querySelector("#attempt-status")?.textContent === "Capturing.");
  await pageD.click("#btn-finish-attempt");
  await pageD.waitForFunction(() => {
    const status = document.querySelector("#attempt-status")?.textContent || "";
    return status === "Evaluated." || /not confirmed|rejected|no longer/.test(status);
  });
  check(
    "the next attempt after a lost one is evaluated",
    (await text(pageD, "#attempt-status")) === "Evaluated.",
    await text(pageD, "#attempt-status"),
  );
  await contextD.close();

  // Simulate a score revision changing without the playback citation. The
  // requests still reach the real server, so a rejected Begin must cancel
  // its actual stored attempt rather than leave it capturing.
  const contextE = await browser.createBrowserContext();
  const pageE = await contextE.newPage();
  watch(pageE, "revision-mismatch", false);
  await installMidi(pageE);
  let changedPreparation = false;
  let changedBegin = false;
  await pageE.setRequestInterception(true);
  pageE.on("request", async (request) => {
    tally(request.url());
    const prepare = request.url().endsWith("/api/education/lesson-practice-preparations");
    const begin = request.url().endsWith("/api/education/lesson-practice-attempts");
    if ((prepare && !changedPreparation) || (begin && !changedBegin)) {
      if (prepare) changedPreparation = true;
      if (begin) changedBegin = true;
      try {
        const response = await fetch(request.url(), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: request.postData(),
        });
        const body = await response.json();
        const preparation = begin ? body.preparation : body;
        preparation.playback.canonical_revision_id = "rev-simulated-stale-playback";
        await request.respond({
          status: response.status,
          contentType: "application/json",
          body: JSON.stringify(body),
        });
      } catch (error) {
        failures += 1;
        notes.push(`FAIL revision interception: ${error.message}`);
        await request.abort("failed");
      }
      return;
    }
    await request.continue();
  });
  const query = new URLSearchParams({ delivery_id: deliveryId });
  await pageE.goto(`${base}/lesson-practice.html?${query}`, { waitUntil: "networkidle0" });
  await pageE.waitForFunction(() => document.querySelector("#status")?.textContent.includes("invalid"));
  check("revision mismatch blocks reference playback before mount", await pageE.evaluate(() => (
    document.querySelector("#btn-play").disabled
    && document.querySelector("#btn-start-attempt").disabled
    && document.querySelectorAll("#scrollCanvas .note").length === 0
  )));
  check("invalid preparation gives a recovery action", (await text(pageE, "#status")).includes("Refresh the lesson"));
  await pageE.click("#refresh-lesson");
  await pageE.waitForFunction(() => /Paused/.test(document.querySelector("#status")?.textContent || ""));
  await pageE.click("#btn-enable-midi");
  await pageE.waitForFunction(() => /ready/.test(document.querySelector("#midi-status")?.textContent || ""));
  const beforeBadBegin = { ...counts };
  await pageE.click("#btn-start-attempt");
  await pageE.waitForFunction(() => /begin response could not be used/.test(document.querySelector("#attempt-status")?.textContent || ""));
  check("revision mismatch cancels the unusable Begin without capture", changedBegin
    && counts.cancel === beforeBadBegin.cancel + 1
    && counts.message === beforeBadBegin.message
    && counts.finish === beforeBadBegin.finish);
  check("rejected Begin restores ordinary practice", await pageE.evaluate(() => (
    !document.querySelector("#btn-play").disabled
    && !document.querySelector("#btn-start-attempt").disabled
    && document.querySelector("#attempt-feedback").textContent === ""
  )));
  notes.push("NOTE revision mismatches are simulated response mutations, not a changed server lesson.");
  await contextE.close();
} catch (error) {
  failures += 1;
  notes.push(`FAIL driver — ${error.stack || error.message}`);
  try {
    await pageA.screenshot({ path: `${output}/99-driver-error.png`, fullPage: true });
  } catch {
    notes.push("FAIL screenshot after driver error");
  }
} finally {
  await browser.close();
}

const summary = {
  stage: "DO-016 Stage 8",
  base,
  delivery_id: deliveryId,
  injected_midi: true,
  midi_evidence: "Injected through navigator.requestMIDIAccess before page boot. Not a physical MIDI device.",
  physical_midi: "UNVERIFIED_PHYSICAL_MIDI_INPUT",
  physical_audio: "UNVERIFIED_AUDIO_OUTPUT",
  restart_witness: false,
  simulated_responses: [
    {
      scenario: "revision-mismatch",
      operations: ["prepare", "begin"],
      mutation: "playback.canonical_revision_id",
      source: "mutated live response",
    },
    {
      scenario: "unknown-attempt",
      operation: "finish",
      status: 404,
      body: { error: "unknown_attempt" },
      source: "simulated",
    },
  ],
  node: process.version,
  browser: browserVersion,
  launch: {
    executablePath: chromeExecutable,
    puppeteerModule,
    headless: "new",
    args: launchArgs,
  },
  attempts,
  request_counts: counts,
  failures,
  notes,
};
writeFileSync(`${output}/summary.json`, `${JSON.stringify(summary, null, 2)}\n`);
console.log(notes.join("\n"));
process.exit(failures === 0 ? 0 : 1);
