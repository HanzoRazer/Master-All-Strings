/**
 * Browser half of the DO-016 integration witness.
 *
 * MIDI is injected before the page boots. It is not a physical input.
 * Restart and reseed barriers talk to the parent harness. Finish and cancel
 * after a restart are answered by that new process, not by a fabricated body.
 */

import crypto from "node:crypto";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import net from "node:net";
import { pathToFileURL } from "node:url";

const launch = JSON.parse(readFileSync(process.argv[2], "utf8"));
const output = launch.output;
mkdirSync(output, { recursive: true });
const imported = await import(pathToFileURL(launch.puppeteer_module).href);
const puppeteer = imported.default?.launch ? imported.default : imported;
const launchArgs = ["--no-sandbox", "--disable-dev-shm-usage", "--autoplay-policy=no-user-gesture-required"];

const notes = [];
let failures = 0;
let currentScenario = "";
const exchanges = [];
const scenarios = {};
const startedAt = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

function check(name, ok, detail = "") {
  notes.push(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` - ${detail}` : ""}`);
  if (!ok) failures += 1;
  return ok;
}

function sha256(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function recordExchange({ scenario, operation, source, status, requestText, responseBytes, fabricated }) {
  const requestBytes = Buffer.from(requestText ?? "{}");
  exchanges.push({
    id: `${scenario}-${operation}-${exchanges.length}`,
    scenario,
    operation,
    source,
    fabricated,
    status,
    request_base64: requestBytes.toString("base64"),
    request_sha256: sha256(requestBytes),
    response_base64: responseBytes.toString("base64"),
    response_sha256: sha256(responseBytes),
    parsedResponse: JSON.parse(responseBytes.toString("utf8")),
  });
}

function operationOf(url) {
  const path = new URL(url).pathname;
  if (path === "/api/education/lesson-delivery-preview") return "preview";
  if (path === "/api/education/lesson-practice-choices") return "choice";
  if (path === "/api/education/lesson-practice-preparations") return "prepare";
  if (path === "/api/education/lesson-practice-attempts") return "begin";
  if (path === "/api/education/lesson-practice-attempt-messages") return "message";
  if (path === "/api/education/lesson-practice-attempt-finishes") return "finish";
  if (path === "/api/education/lesson-practice-attempt-cancellations") return "cancel";
  return "";
}

function countsOf(items) {
  return {
    begin: items.filter((item) => item.operation === "begin").length,
    message: items.filter((item) => item.operation === "message").length,
    finish: items.filter((item) => item.operation === "finish").length,
    cancel: items.filter((item) => item.operation === "cancel").length,
    guided: 0,
    performance: 0,
  };
}

function pinsOf(begin, finish) {
  return {
    delivery_id: begin.delivery_id,
    assignment_id: begin.assignment_id,
    content_id: begin.content_id,
    assignment_artifact_digest: begin.assignment_artifact_digest,
    assignment_behavior_digest: begin.assignment_behavior_digest,
    revision_id: begin.preparation?.score?.canonical_revision?.revision_id,
    attempt_id: begin.attempt_id,
    capture_id: begin.capture_id,
    performance_session_id: begin.performance_session_id,
    evaluation_digest: finish.evaluation?.evaluation_digest,
  };
}

function scenarioItems(id) {
  return exchanges.filter((item) => item.scenario === id);
}

function connectControl(port) {
  return new Promise((resolve, reject) => {
    const socket = net.connect({ host: "127.0.0.1", port });
    socket.setEncoding("utf8");
    let buffer = "";
    const pending = new Map();
    let seq = 0;
    socket.on("data", (chunk) => {
      buffer += chunk;
      let splitAt = buffer.indexOf("\n");
      while (splitAt >= 0) {
        const line = buffer.slice(0, splitAt);
        buffer = buffer.slice(splitAt + 1);
        splitAt = buffer.indexOf("\n");
        if (!line.trim()) continue;
        const message = JSON.parse(line);
        const waiter = pending.get(message.id);
        if (!waiter) continue;
        clearTimeout(waiter.timer);
        pending.delete(message.id);
        if (message.ok) waiter.resolve(message);
        else waiter.reject(new Error(message.error || `${message.op || "barrier"} failed`));
      }
    });
    socket.once("error", reject);
    socket.once("connect", () => resolve({
      request(op, extra = {}) {
        const id = String(++seq);
        return new Promise((resolveRequest, rejectRequest) => {
          const timer = setTimeout(() => {
            pending.delete(id);
            rejectRequest(new Error(`barrier ${op} timed out`));
          }, 45000);
          pending.set(id, { resolve: resolveRequest, reject: rejectRequest, timer });
          socket.write(`${JSON.stringify({ id, op, ...extra })}\n`);
        });
      },
    }));
  });
}

let responseQueue = Promise.resolve();

function watch(page) {
  page.setDefaultTimeout(45000);
  page.on("console", (message) => {
    if (message.type() === "error" && !/favicon/i.test(message.text())) {
      notes.push(`console: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => {
    failures += 1;
    notes.push(`FAIL pageerror - ${error.message}`);
  });
  page.on("requestfailed", (request) => {
    const reason = request.failure()?.errorText || "";
    if (reason.includes("ERR_FAILED") || reason.includes("ERR_ABORTED")) {
      notes.push(`NOTE browser transport closed ${request.url()} ${reason}`);
      return;
    }
    notes.push(`request failed: ${request.url()} ${reason}`);
  });
  page.on("response", (response) => {
    const scenario = currentScenario;
    const operation = operationOf(response.url());
    const url = response.url();
    if (!operation) {
      if (url.includes("/api/education/guided-sessions") || url.includes("/api/performance/")) {
        failures += 1;
        notes.push(`FAIL forbidden request - ${url}`);
      }
      return;
    }
    responseQueue = responseQueue.then(async () => {
      const responseBytes = Buffer.from(await response.content());
      recordExchange({
        scenario,
        operation,
        source: "browser",
        status: response.status(),
        requestText: response.request().postData() ?? "{}",
        responseBytes,
        fabricated: false,
      });
    }).catch((error) => {
      failures += 1;
      notes.push(`FAIL response capture - ${error.message}`);
    });
  });
}

async function settle() {
  await responseQueue;
}

async function text(page, selector) {
  return page.$eval(selector, (node) => node.textContent || "");
}

async function installMidi(page) {
  await page.evaluateOnNewDocument(() => {
    const input = {
      id: "injected-stage9-input",
      name: "Injected Stage 9 input",
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

async function chooseAndOpen(page) {
  await page.goto(`${launch.base}/lesson-inbox.html`, { waitUntil: "networkidle0" });
  await page.waitForFunction(() => document.querySelector("#inbox-status")?.textContent === "");
  const selected = await page.$$eval("#delivery-list button", (buttons, deliveryId) => {
    const button = buttons.find((item) => item.deliveryId === deliveryId);
    if (!button) return false;
    button.click();
    return true;
  }, launch.delivery_id);
  check("inbox lists the custom delivery", selected, launch.delivery_id);
  await page.waitForFunction(() => document.querySelector("#choose")?.disabled === false);
  const preview = await text(page, "#preview-fields");
  check("preview shows the custom title", preview.includes(launch.title), preview.slice(0, 180));
  await page.click("#choose");
  await page.waitForFunction(() => document.querySelector("#open-practice")?.getAttribute("href"));
  const href = await page.$eval("#open-practice", (node) => node.getAttribute("href"));
  check(
    "open practice carries only the delivery id",
    href === `lesson-practice.html?delivery_id=${launch.delivery_id}`,
    href,
  );
  await page.click("#open-practice");
  await page.waitForFunction(() => /Paused/.test(document.querySelector("#status")?.textContent || ""));
  await settle();
}

async function enableMidi(page) {
  if (!await page.$eval("#btn-enable-midi", (node) => node.disabled)) {
    await page.click("#btn-enable-midi");
  }
  await page.waitForFunction(() => /ready/.test(document.querySelector("#midi-status")?.textContent || ""));
}

async function emitNotes(page, count) {
  const sent = await page.evaluate((count) => {
    const now = performance.now();
    const results = [];
    for (let index = 0; index < count; index += 1) {
      results.push(window.__emitMidi([0x90, 60 + (index % 12), 80], now + index + 1));
    }
    return results;
  }, count);
  check("injected notes reached the input", sent.every(Boolean), String(sent.length));
}

async function waitAck(page, count) {
  await page.waitForFunction((expected) => (
    document.querySelector("#attempt-count")?.textContent || ""
  ).includes(`Acknowledged messages: ${expected}`), {}, count);
  await settle();
}

async function practiceState(page) {
  return page.evaluate(() => ({
    status: document.querySelector("#attempt-status")?.textContent || "",
    feedback: document.querySelector("#attempt-feedback")?.textContent || "",
    retryHidden: document.querySelector("#btn-retry-finish")?.hidden,
    startDisabled: document.querySelector("#btn-start-attempt")?.disabled,
    playDisabled: document.querySelector("#btn-play")?.disabled,
    refreshDisabled: document.querySelector("#refresh-lesson")?.disabled,
    rate: document.querySelector('[data-rate="1"]')?.getAttribute("aria-pressed"),
    slow: document.querySelector('[data-rate="0.75"]')?.getAttribute("aria-pressed"),
    slowDisabled: document.querySelector('[data-rate="0.75"]')?.disabled,
    loop: document.querySelector("#loop-enabled")?.checked,
    loopDisabled: document.querySelector("#loop-enabled")?.disabled,
    seekDisabled: document.querySelector("#seek")?.disabled,
    seek: document.querySelector("#seek")?.value,
    restartDisabled: document.querySelector("#btn-restart")?.disabled,
    clock: document.querySelector("#clock")?.textContent || "",
    sound: document.querySelector("#sound-enabled")?.checked,
    delivery: document.querySelector("#identity-delivery")?.textContent || "",
    assignment: document.querySelector("#identity-assignment")?.textContent || "",
    content: document.querySelector("#identity-content")?.textContent || "",
  }));
}

let browser;
const evidence = {
  run_id: crypto.randomUUID(),
  started_at: startedAt,
  started_at_central: new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Chicago",
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  }).format(new Date()),
  node: process.version,
  os: process.platform,
  browser: "",
  launch: {
    executablePath: launch.chrome_executable,
    puppeteerModule: launch.puppeteer_module,
    headless: "new",
    args: launchArgs,
  },
  complete: false,
  failures: 0,
  notes,
  scenarios,
  exchanges,
};

try {
  browser = await puppeteer.launch({
    executablePath: launch.chrome_executable,
    headless: "new",
    args: launchArgs,
  });
  evidence.browser = await browser.version();
  const control = await connectControl(launch.control_port);
  const page = await browser.newPage();
  watch(page);
  await installMidi(page);
  await page.setViewport({ width: 1280, height: 900 });

  currentScenario = "T1";
  scenarios.T1 = {};
  scenarios.T2 = {};
  await chooseAndOpen(page);
  check("practice opens paused", (await text(page, "#status")).includes("Paused"));
  check("custom title is on the practice page", (await text(page, "#lesson-title")) === launch.title);
  check("MIDI was injected before boot", await page.evaluate(() => window.__midiInjected === true));
  await page.click('[data-rate="0.75"]');
  const slowBefore = await page.$eval('[data-rate="0.75"]', (node) => node.getAttribute("aria-pressed"));
  const loopBefore = await page.$eval("#loop-enabled", (node) => node.checked);
  await page.click("#loop-enabled");
  const loopAfter = await page.$eval("#loop-enabled", (node) => node.checked);
  await page.$eval("#seek", (node) => {
    node.value = "800";
    node.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.waitForFunction(() => (document.querySelector("#clock")?.textContent || "") !== "0.00s");
  const clockBefore = await text(page, "#clock");
  scenarios.T2 = {
    non_normal_rate_before: slowBefore === "true",
    loop_toggled_before: loopBefore !== loopAfter,
    normal_rate_during: false,
    loop_off_during: false,
    controls_locked: false,
    timeline_not_moved: false,
    position_restarted: false,
    controls_restored: false,
  };
  check("ordinary rate can leave normal before an attempt", scenarios.T2.non_normal_rate_before, slowBefore);
  check("ordinary loop can change before an attempt", scenarios.T2.loop_toggled_before);

  await enableMidi(page);
  await page.click("#btn-start-attempt");
  await page.waitForFunction(() => document.querySelector("#attempt-status")?.textContent === "Capturing.");
  await page.waitForFunction(() => Number(document.querySelector("#seek")?.value || "1000") < 200);
  const during = await practiceState(page);
  scenarios.T2.normal_rate_during = during.rate === "true" && during.slow !== "true";
  scenarios.T2.loop_off_during = during.loop === false;
  scenarios.T2.controls_locked = during.slowDisabled && during.loopDisabled && during.seekDisabled
    && during.restartDisabled && during.refreshDisabled;
  scenarios.T2.position_restarted = Number.parseFloat(during.clock) < Number.parseFloat(clockBefore);
  await page.evaluate(() => {
    document.querySelector('[data-rate="0.75"]').click();
    const seek = document.querySelector("#seek");
    seek.value = "950";
    seek.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await new Promise((resolve) => setTimeout(resolve, 200));
  const nudged = await practiceState(page);
  scenarios.T2.timeline_not_moved = nudged.rate === "true" && Number(nudged.seek) < 500;
  check("capture installs normal speed and loop off", scenarios.T2.normal_rate_during && scenarios.T2.loop_off_during);
  check("capture locks timeline controls", scenarios.T2.controls_locked, JSON.stringify(during));
  check("capture restarts before the locked pass", scenarios.T2.position_restarted, `${clockBefore} -> ${during.clock}`);
  check("locked controls do not move the timeline", scenarios.T2.timeline_not_moved, nudged.seek);
  await emitNotes(page, 2);
  await waitAck(page, 2);
  await page.click("#btn-finish-attempt");
  await page.waitForFunction(() => document.querySelector("#attempt-status")?.textContent === "Evaluated.");
  await settle();
  const evaluated = await practiceState(page);
  scenarios.T1.feedback_text = evaluated.feedback;
  const identities = pinsOf(
    scenarioItems("T1").find((item) => item.operation === "begin").parsedResponse,
    scenarioItems("T1").find((item) => item.operation === "finish").parsedResponse,
  );
  scenarios.T1.identities = identities;
  scenarios.T1.requests = countsOf(scenarioItems("T1"));
  check("displayed delivery matches the attempt", evaluated.delivery === identities.delivery_id, evaluated.delivery);
  check("feedback names this attempt", evaluated.feedback.includes(identities.attempt_id));
  check("feedback shows counts without a completion claim", /Matched:/.test(evaluated.feedback)
    && /Missing:/.test(evaluated.feedback) && /Extra:/.test(evaluated.feedback)
    && !/lesson complete|mastered/i.test(evaluated.feedback));
  check("sound stayed off through finish", evaluated.sound === false);
  await page.click('[data-rate="0.75"]');
  const restored = await page.$eval('[data-rate="0.75"]', (node) => ({
    pressed: node.getAttribute("aria-pressed"),
    disabled: node.disabled,
  }));
  const playEnabled = await page.$eval("#btn-play", (node) => node.disabled === false);
  scenarios.T2.controls_restored = restored.disabled === false && restored.pressed === "true" && playEnabled;
  check("ordinary practice returns after evaluation", scenarios.T2.controls_restored, JSON.stringify(restored));
  await page.screenshot({ path: `${output}/t1-evaluated.png`, fullPage: true });

  currentScenario = "T3";
  scenarios.T3 = {};
  await page.click("#btn-start-attempt");
  await page.waitForFunction(() => document.querySelector("#attempt-status")?.textContent === "Capturing.");
  await emitNotes(page, 1);
  await waitAck(page, 1);
  await page.click("#btn-cancel-attempt");
  await page.waitForFunction(() => {
    const status = document.querySelector("#attempt-status")?.textContent || "";
    return status.includes("cancelled") || status === "Interrupted.";
  });
  await settle();
  const interrupted = await practiceState(page);
  scenarios.T3.feedback_text = interrupted.feedback;
  const t3Begin = scenarioItems("T3").find((item) => item.operation === "begin").parsedResponse;
  scenarios.T3.attempt_id = t3Begin.attempt_id;
  check("cancel shows interruption without counts", interrupted.feedback.includes("No evaluation was produced.")
    && !interrupted.feedback.includes("Matched:"), interrupted.feedback.slice(0, 180));

  currentScenario = "T4";
  scenarios.T4 = {};
  await page.click("#btn-start-attempt");
  await page.waitForFunction(() => document.querySelector("#attempt-status")?.textContent === "Capturing.");
  await emitNotes(page, 1);
  await waitAck(page, 1);
  const restartFinish = await control.request("restart");
  const stillCapturing = (await text(page, "#attempt-status")) === "Capturing.";
  check("finish restart leaves the attempt capturing", stillCapturing, await text(page, "#attempt-status"));
  await page.click("#btn-finish-attempt");
  await page.waitForFunction(() => (
    document.querySelector("#attempt-status")?.textContent || ""
  ).includes("no longer has this attempt"));
  await settle();
  const lostFinish = await practiceState(page);
  const t4Begin = scenarioItems("T4").find((item) => item.operation === "begin").parsedResponse;
  scenarios.T4.attempt_id = t4Begin.attempt_id;
  scenarios.T4.epoch_before = restartFinish.epoch_before;
  scenarios.T4.epoch_after = restartFinish.epoch_after;
  scenarios.T4.status_text = lostFinish.status;
  scenarios.T4.feedback_text = lostFinish.feedback;
  scenarios.T4.retry_hidden = lostFinish.retryHidden === true;
  scenarios.T4.start_enabled = lostFinish.startDisabled === false;
  scenarios.T4.reference_enabled = lostFinish.playDisabled === false && lostFinish.refreshDisabled === false;
  check("T3's next attempt has a new id", t4Begin.attempt_id !== scenarios.T3.attempt_id);
  check("restarted finish is the lost-attempt refusal", lostFinish.status.includes("no longer has this attempt")
    && lostFinish.status.includes("not evaluated"), lostFinish.status);
  check("restarted finish clears evaluation and retry", scenarios.T4.retry_hidden && !lostFinish.feedback.includes("Matched:"));
  check("restarted finish restores practice", scenarios.T4.start_enabled && scenarios.T4.reference_enabled);
  await page.screenshot({ path: `${output}/t4-restart-finish.png`, fullPage: true });

  const reseedForCancel = await control.request("reseed");
  check("reseed before the cancel restart succeeded", reseedForCancel.ok === true);
  currentScenario = "T5";
  scenarios.T5 = {};
  await chooseAndOpen(page);
  await enableMidi(page);
  await page.click("#btn-start-attempt");
  await page.waitForFunction(() => document.querySelector("#attempt-status")?.textContent === "Capturing.");
  await emitNotes(page, 1);
  await waitAck(page, 1);
  const restartCancel = await control.request("restart");
  check(
    "cancel restart leaves the attempt capturing",
    (await text(page, "#attempt-status")) === "Capturing.",
    await text(page, "#attempt-status"),
  );
  await page.click("#btn-cancel-attempt");
  await page.waitForFunction(() => (
    document.querySelector("#attempt-status")?.textContent || ""
  ).includes("no longer has this attempt"));
  await settle();
  const lostCancel = await practiceState(page);
  const t5Begin = scenarioItems("T5").find((item) => item.operation === "begin").parsedResponse;
  scenarios.T5.attempt_id = t5Begin.attempt_id;
  scenarios.T5.epoch_before = restartCancel.epoch_before;
  scenarios.T5.epoch_after = restartCancel.epoch_after;
  scenarios.T5.status_text = lostCancel.status;
  scenarios.T5.feedback_text = lostCancel.feedback;
  scenarios.T5.retry_hidden = lostCancel.retryHidden === true;
  scenarios.T5.start_enabled = lostCancel.startDisabled === false;
  scenarios.T5.reference_enabled = lostCancel.playDisabled === false && lostCancel.refreshDisabled === false;
  check("restarted cancel is not a recorded cancellation", lostCancel.status.includes("not recorded")
    && !lostCancel.feedback.includes("No evaluation was produced."), lostCancel.status);

  currentScenario = "T6";
  scenarios.T6 = {};
  await page.goto(`${launch.base}/lesson-inbox.html`, { waitUntil: "networkidle0" });
  await page.waitForFunction(() => {
    const empty = document.querySelector("#inbox-empty");
    return empty && empty.hidden === false;
  });
  const emptyText = await text(page, "#inbox-empty");
  scenarios.T6.inbox_empty = true;
  scenarios.T6.empty_text = emptyText;
  check("restart clears the inbox", emptyText.includes("No deliveries"), emptyText);
  const reseedRecovery = await control.request("reseed");
  check("recovery receive succeeded", reseedRecovery.ok === true);
  await page.click("#refresh-inbox");
  await chooseAndOpen(page);
  await enableMidi(page);
  await page.click("#btn-start-attempt");
  await page.waitForFunction(() => document.querySelector("#attempt-status")?.textContent === "Capturing.");
  check("a new attempt clears the previous feedback", (await text(page, "#attempt-feedback")) === "");
  await emitNotes(page, 2);
  await waitAck(page, 2);
  await page.click("#btn-finish-attempt");
  await page.waitForFunction(() => document.querySelector("#attempt-status")?.textContent === "Evaluated.");
  await settle();
  const recovered = await practiceState(page);
  const recoveredPins = pinsOf(
    scenarioItems("T6").find((item) => item.operation === "begin").parsedResponse,
    scenarioItems("T6").find((item) => item.operation === "finish").parsedResponse,
  );
  scenarios.T6.identities = recoveredPins;
  scenarios.T6.requests = countsOf(scenarioItems("T6"));
  scenarios.T6.feedback_text = recovered.feedback;
  check("recovered attempt ids differ", recoveredPins.attempt_id !== identities.attempt_id
    && recoveredPins.capture_id !== identities.capture_id
    && recoveredPins.performance_session_id !== identities.performance_session_id);
  check("old feedback does not leak", !recovered.feedback.includes(identities.attempt_id));
  await page.screenshot({ path: `${output}/t6-recovered.png`, fullPage: true });

  currentScenario = "T7";
  scenarios.T7 = {};
  await page.click("#btn-start-attempt");
  await page.waitForFunction(() => document.querySelector("#attempt-status")?.textContent === "Capturing.");
  await emitNotes(page, 2);
  await waitAck(page, 2);
  let withheld = false;
  page.on("request", async (request) => {
    try {
      if (!withheld && request.url().endsWith("/api/education/lesson-practice-attempt-finishes")) {
        withheld = true;
        const posted = request.postData() ?? "{}";
        const forwarded = await fetch(request.url(), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: posted,
        });
        const responseBytes = Buffer.from(await forwarded.arrayBuffer());
        recordExchange({
          scenario: "T7",
          operation: "finish",
          source: "forwarded_server",
          status: forwarded.status,
          requestText: posted,
          responseBytes,
          fabricated: false,
        });
        await request.abort("failed");
        return;
      }
      await request.continue();
    } catch (error) {
      notes.push(`intercept: ${error.message}`);
      try {
        await request.continue();
      } catch {
        // The request may already have been handled.
      }
    }
  });
  await page.setRequestInterception(true);
  await page.click("#btn-finish-attempt");
  await page.waitForFunction(() => document.querySelector("#btn-retry-finish")?.hidden === false);
  await settle();
  const unconfirmed = await practiceState(page);
  const beforeRetry = exchanges.filter((item) => item.scenario === "T7");
  scenarios.T7.status_before_retry = unconfirmed.status;
  scenarios.T7.browser_outcome = "transport_failure";
  scenarios.T7.retry_hidden_before = unconfirmed.retryHidden === true;
  check("lost finish stays unconfirmed", unconfirmed.status.includes("did not finish"), unconfirmed.status);
  check("lost finish offers retry", unconfirmed.retryHidden === false);
  await page.click("#btn-retry-finish");
  await page.waitForFunction(() => document.querySelector("#attempt-status")?.textContent === "Evaluated.");
  await settle();
  const retried = await practiceState(page);
  const t7Items = scenarioItems("T7");
  const finishes = t7Items.filter((item) => item.operation === "finish");
  const beginCountAfter = t7Items.filter((item) => item.operation === "begin").length;
  const messageCountAfter = t7Items.filter((item) => item.operation === "message").length;
  const beginCountBefore = beforeRetry.filter((item) => item.operation === "begin").length;
  const messageCountBefore = beforeRetry.filter((item) => item.operation === "message").length;
  scenarios.T7.attempt_id = t7Items.find((item) => item.operation === "begin").parsedResponse.attempt_id;
  scenarios.T7.begin_during_retry = beginCountAfter - beginCountBefore;
  scenarios.T7.appends_during_retry = messageCountAfter - messageCountBefore;
  scenarios.T7.feedback_text = retried.feedback;
  check("retry keeps one stored finish and one browser finish", finishes.length === 2
    && finishes[0].source === "forwarded_server" && finishes[1].source === "browser");
  check("retry sends no new MIDI", scenarios.T7.begin_during_retry === 0 && scenarios.T7.appends_during_retry === 0);
  check("retry shows the same attempt", retried.feedback.includes(scenarios.T7.attempt_id), retried.status);
  await page.screenshot({ path: `${output}/t7-retried.png`, fullPage: true });
  evidence.complete = failures === 0;
} catch (error) {
  failures += 1;
  notes.push(`FAIL driver - ${error.stack || error.message}`);
  evidence.complete = false;
} finally {
  if (browser) await browser.close();
  evidence.failures = failures;
  evidence.exchanges = exchanges.map((item) => {
    const published = { ...item };
    delete published.parsedResponse;
    return published;
  });
  writeFileSync(`${output}/browser_evidence.json`, `${JSON.stringify(evidence, null, 2)}\n`);
  console.log(notes.join("\n"));
  process.exit(failures === 0 ? 0 : 1);
}
