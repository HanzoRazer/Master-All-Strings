/**
 * Browser half of the keyed Begin recovery witness.
 * Restart and lost responses are real. The preparation barrier is the parent.
 *
 * Every exchange keeps the exact request and response bytes with their
 * sha256, plus who put the request on the wire (the page or this harness)
 * and what the page saw (the live response, a simulated network failure, or
 * nothing because the harness sent it). Server responses are always live.
 */

import { createHash } from "node:crypto";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import net from "node:net";
import { pathToFileURL } from "node:url";

const launch = JSON.parse(readFileSync(process.argv[2], "utf8"));
const output = launch.output;
mkdirSync(output, { recursive: true });
const imported = await import(pathToFileURL(launch.puppeteer_module).href);
const puppeteer = imported.default?.launch ? imported.default : imported;
const BEGIN = "/api/education/lesson-practice-begin-requests";
const RECOVERY = "/api/education/lesson-practice-begin-recoveries";

const notes = [];
let failures = 0;
const exchanges = [];
const scenarios = {};
let seq = 0;
let currentScenario = null;
let currentEpoch = "A";
// Live page records wait on this, so a harness exchange that happened first
// on the server is also numbered first.
let recordGate = Promise.resolve();
const pendingRecords = [];

function check(name, ok, detail = "") {
  notes.push(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` - ${detail}` : ""}`);
  if (!ok) failures += 1;
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
        else waiter.reject(new Error(message.error || "barrier failed"));
      }
    });
    socket.once("error", reject);
    socket.once("connect", () => resolve({
      request(op, extra = {}) {
        const id = String(++seq);
        return new Promise((resolveRequest, rejectRequest) => {
          const timer = setTimeout(() => rejectRequest(new Error(`barrier ${op} timed out`)), 30000);
          pending.set(id, { resolve: resolveRequest, reject: rejectRequest, timer });
          socket.write(`${JSON.stringify({ id, op, ...extra })}\n`);
        });
      },
    }));
  });
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function exchange(fields, requestBytes, responseBytes) {
  const request = Buffer.from(requestBytes);
  const response = responseBytes == null ? null : Buffer.from(responseBytes);
  return {
    seq: fields.seq ?? ++seq,
    scenario: fields.scenario,
    source: fields.source,
    route: fields.route,
    sender: fields.sender,
    page_outcome: fields.pageOutcome,
    epoch: fields.epoch ?? currentEpoch,
    status: fields.status ?? null,
    request_base64: request.toString("base64"),
    request_sha256: sha256(request),
    response_base64: response === null ? null : response.toString("base64"),
    response_sha256: response === null ? null : sha256(response),
    request: JSON.parse(request.toString("utf8")),
    response: response === null ? null : JSON.parse(response.toString("utf8")),
  };
}

// The harness sent these bytes, or forwarded the page's bytes, to the live server.
function recordHarness(scenario, source, route, pageOutcome, status, requestText, responseBytes) {
  exchanges.push(exchange(
    { scenario, source, route, sender: "harness", pageOutcome, status },
    Buffer.from(requestText, "utf8"),
    responseBytes,
  ));
}

function routeOf(url) {
  if (url.endsWith(BEGIN)) return "begin";
  if (url.endsWith(RECOVERY)) return "recovery";
  return null;
}

function decoded(base64) {
  return Buffer.from(base64, "base64");
}

async function feedbackState(page) {
  return page.evaluate(() => {
    const panel = document.querySelector("#attempt-feedback");
    return {
      visible: Boolean(panel) && panel.hidden === false,
      text: panel?.textContent || "",
    };
  });
}

let browser;
const evidence = { complete: false, failures: 0, notes, scenarios, exchanges, epochs: [] };
try {
  browser = await puppeteer.launch({
    executablePath: launch.chrome_executable,
    headless: "new",
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--autoplay-policy=no-user-gesture-required"],
  });
  evidence.chrome = await browser.version();
  evidence.epochs.push({ name: "A", pid: launch.pid });
  const control = await connectControl(launch.control_port);
  const page = await browser.newPage();
  // Every begin or recovery the page itself received from the live server.
  page.on("response", (response) => {
    const route = routeOf(response.url());
    if (!route || response.request().method() !== "POST") return;
    const scenario = currentScenario;
    const epoch = currentEpoch;
    const gate = recordGate;
    pendingRecords.push((async () => {
      await gate;
      const n = ++seq;
      const body = await response.buffer();
      exchanges.push(exchange(
        { seq: n, scenario, source: "browser", route, sender: "browser",
          pageOutcome: "response", epoch, status: response.status() },
        Buffer.from(response.request().postData() || "", "utf8"),
        body,
      ));
    })());
  });
  await page.evaluateOnNewDocument(() => {
    const input = {
      id: "injected-begin-recovery",
      name: "Injected Begin Recovery",
      state: "connected",
      onmidimessage: null,
    };
    navigator.requestMIDIAccess = async () => ({ inputs: new Map([[input.id, input]]), onstatechange: null });
    window.__midiInjected = true;
  });
  await page.goto(`${launch.base}/lesson-inbox.html`, { waitUntil: "networkidle0" });
  await page.waitForFunction((deliveryId) => {
    const button = [...document.querySelectorAll("#delivery-list button")]
      .find((item) => item.deliveryId === deliveryId);
    if (!button) return false;
    button.click();
    return true;
  }, {}, launch.delivery_id);
  await page.waitForFunction(() => document.querySelector("#choose")?.disabled === false);
  await page.click("#choose");
  await page.waitForFunction(() => document.querySelector("#open-practice")?.getAttribute("href"));
  await page.click("#open-practice");
  await page.waitForFunction(() => /Paused/.test(document.querySelector("#status")?.textContent || ""));
  await page.click("#btn-enable-midi");
  await page.waitForFunction(() => /ready/.test(document.querySelector("#midi-status")?.textContent || ""));

  // W1: the server stores Begin; the page only sees the failure, then resolves it.
  scenarios.W1 = {};
  currentScenario = "W1";
  let lost = false;
  await page.setRequestInterception(true);
  page.on("request", async (request) => {
    try {
      if (!lost && request.url().endsWith(BEGIN)) {
        lost = true;
        const posted = request.postData() || "{}";
        const forwarded = await fetch(request.url(), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: posted,
        });
        const bytes = Buffer.from(await forwarded.arrayBuffer());
        recordHarness("W1", "forwarded_server", "begin", "network_failure", forwarded.status, posted, bytes);
        await request.abort("failed");
        return;
      }
      await request.continue();
    } catch (error) {
      notes.push(`intercept: ${error.message}`);
      try { await request.continue(); } catch { /* already handled */ }
    }
  });
  await page.click("#btn-start-attempt");
  await page.waitForFunction(() => document.querySelector("#btn-resolve-start")?.hidden === false);
  check("lost begin offers resolve", true);
  await page.setRequestInterception(false);
  page.removeAllListeners("request");
  await page.click("#btn-resolve-start");
  await page.waitForFunction(() => /interrupted/.test(document.querySelector("#attempt-status")?.textContent || ""));
  scenarios.W1.interrupted = true;
  const storedAttempt = exchanges.find((item) => item.scenario === "W1")?.response?.attempt?.attempt_id;
  check("resolve interrupts the stored attempt", Boolean(storedAttempt), storedAttempt || "");
  const w1Feedback = await feedbackState(page);
  scenarios.W1.feedback_visible = w1Feedback.visible;
  scenarios.W1.feedback_text = w1Feedback.text;
  check(
    "recovered interruption feedback stays visible",
    w1Feedback.visible && Boolean(storedAttempt) && w1Feedback.text.includes(storedAttempt),
    w1Feedback.text.slice(0, 120),
  );

  // W2: recovery reaches the server before the delayed Begin is released.
  scenarios.W2 = {};
  currentScenario = "W2";
  let delayed = false;
  await page.setRequestInterception(true);
  page.on("request", async (request) => {
    try {
      if (!delayed && request.url().endsWith(BEGIN)) {
        delayed = true;
        const posted = request.postData() || "{}";
        const recovered = await control.request("recover", { raw: posted });
        recordHarness("W2", "recovery_before_begin", "recovery", "not_sent_by_page",
          recovered.status, posted, decoded(recovered.response_base64));
        await request.continue();
        return;
      }
      await request.continue();
    } catch (error) {
      notes.push(`w2: ${error.message}`);
      try { await request.continue(); } catch { /* already handled */ }
    }
  });
  await page.click("#btn-start-attempt");
  await page.waitForFunction(() => document.querySelector("#btn-resolve-start")?.hidden === false);
  page.removeAllListeners("request");
  await page.setRequestInterception(false);
  const closed = exchanges.find((item) => item.scenario === "W2");
  check("recovery before begin seals the key", closed?.response?.status === "NO_ATTEMPT");
  await page.click("#btn-resolve-start");
  await page.waitForFunction(() => /No attempt is available/.test(
    document.querySelector("#attempt-status")?.textContent || ""
  ));

  // W3: recovery reaches the gateway while preparation is blocked.
  scenarios.W3 = {};
  currentScenario = "W3";
  await control.request("arm");
  let blockedBegin = false;
  await page.setRequestInterception(true);
  page.on("request", async (request) => {
    try {
      if (!blockedBegin && request.url().endsWith(BEGIN)) {
        blockedBegin = true;
        const posted = request.postData() || "{}";
        const barrier = control.request("recover-while-blocked", { raw: posted });
        // The page's own Begin finishes only after this recovery released it.
        let opened;
        recordGate = new Promise((resolve) => { opened = resolve; });
        await request.continue();
        try {
          const recovered = await barrier;
          recordHarness("W3", "recovery_during_prepare", "recovery", "not_sent_by_page",
            recovered.status, posted, decoded(recovered.response_base64));
        } finally {
          opened();
        }
        return;
      }
      await request.continue();
    } catch (error) {
      notes.push(`w3: ${error.message}`);
      try { await request.continue(); } catch { /* already handled */ }
    }
  });
  await page.click("#btn-start-attempt");
  await page.waitForFunction(() => /interrupted/.test(document.querySelector("#attempt-status")?.textContent || ""));
  page.removeAllListeners("request");
  await page.setRequestInterception(false);
  check(
    "blocked preparation does not publish started",
    exchanges.some((item) => item.scenario === "W3" && item.response?.status === "PENDING"),
  );
  const w3Feedback = await feedbackState(page);
  scenarios.W3.feedback_visible = w3Feedback.visible;
  scenarios.W3.feedback_text = w3Feedback.text;
  check("interrupted begin feedback stays visible", w3Feedback.visible
    && w3Feedback.text.includes("Attempt interrupted"), w3Feedback.text.slice(0, 120));

  // W4: hide one successful recovery, then repeat it.
  scenarios.W4 = {};
  currentScenario = "W4";
  let hiddenRecovery = false;
  await page.setRequestInterception(true);
  page.on("request", async (request) => {
    try {
      if (!hiddenRecovery && request.url().endsWith(BEGIN)) {
        hiddenRecovery = true;
        const posted = request.postData() || "{}";
        const forwarded = await fetch(request.url(), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: posted,
        });
        recordHarness("W4", "forwarded_begin", "begin", "network_failure", forwarded.status, posted,
          Buffer.from(await forwarded.arrayBuffer()));
        await request.abort("failed");
        return;
      }
      if (hiddenRecovery && request.url().endsWith(RECOVERY) && !scenarios.W4.first) {
        const posted = request.postData() || "{}";
        const forwarded = await fetch(request.url(), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: posted,
        });
        const bytes = Buffer.from(await forwarded.arrayBuffer());
        recordHarness("W4", "forwarded_recovery", "recovery", "network_failure", forwarded.status, posted, bytes);
        scenarios.W4.first = JSON.parse(bytes.toString("utf8"));
        await request.abort("failed");
        return;
      }
      await request.continue();
    } catch (error) {
      notes.push(`w4: ${error.message}`);
      try { await request.continue(); } catch { /* already handled */ }
    }
  });
  await page.click("#btn-start-attempt");
  await page.waitForFunction(() => document.querySelector("#btn-resolve-start")?.hidden === false);
  await page.click("#btn-resolve-start");
  await page.waitForFunction(() => document.querySelector("#btn-resolve-start")?.hidden === false);
  page.removeAllListeners("request");
  await page.setRequestInterception(false);
  await page.click("#btn-resolve-start");
  await page.waitForFunction(() => /interrupted/.test(document.querySelector("#attempt-status")?.textContent || ""));
  check("repeated recovery stays interrupted", scenarios.W4.first?.status === "INTERRUPTED");
  const w4Feedback = await feedbackState(page);
  scenarios.W4.feedback_visible = w4Feedback.visible;
  scenarios.W4.feedback_text = w4Feedback.text;
  const w4Attempt = scenarios.W4.first?.attempt?.attempt_id || "";
  check("repeated recovery feedback stays visible", w4Feedback.visible && Boolean(w4Attempt)
    && w4Feedback.text.includes(w4Attempt), w4Feedback.text.slice(0, 120));

  // W5: a restarted process tombs the key and refuses the delayed Begin.
  scenarios.W5 = {};
  currentScenario = "W5";
  let restartBegin = "";
  await page.setRequestInterception(true);
  page.on("request", async (request) => {
    try {
      if (!restartBegin && request.url().endsWith(BEGIN)) {
        restartBegin = request.postData() || "{}";
        // This Begin never reaches a server. Only its bytes are kept, for the replay.
        exchanges.push(exchange(
          { scenario: "W5", source: "aborted_begin", route: "begin", sender: "none",
            pageOutcome: "network_failure" },
          Buffer.from(restartBegin, "utf8"),
          null,
        ));
        await request.abort("failed");
        return;
      }
      await request.continue();
    } catch (error) {
      notes.push(`w5: ${error.message}`);
      try { await request.continue(); } catch { /* already handled */ }
    }
  });
  await page.click("#btn-start-attempt");
  await page.waitForFunction(() => document.querySelector("#btn-resolve-start")?.hidden === false);
  page.removeAllListeners("request");
  await page.setRequestInterception(false);
  await Promise.all(pendingRecords);
  const restarted = await control.request("restart");
  currentEpoch = "B";
  evidence.epochs.push({
    name: "B",
    pid: restarted.pid,
    previous_pid: restarted.previous_pid,
    restart_seq: ++seq,
  });
  await page.click("#btn-resolve-start");
  await page.waitForFunction(() => /No attempt is available/.test(
    document.querySelector("#attempt-status")?.textContent || ""
  ));
  await Promise.all(pendingRecords);
  const replay = await control.request("replay-begin", { raw: restartBegin });
  recordHarness("W5", "replayed_begin", "begin", "not_sent_by_page", replay.status, restartBegin,
    decoded(replay.response_base64));
  const replayed = JSON.parse(decoded(replay.response_base64).toString("utf8"));
  check("restart refuses the delayed begin", replay.status === 409 && replayed?.error === "begin_request_closed");

  evidence.complete = failures === 0;
} catch (error) {
  failures += 1;
  notes.push(`FAIL driver - ${error.stack || error.message}`);
  evidence.complete = false;
} finally {
  try {
    await Promise.all(pendingRecords);
  } catch (error) {
    failures += 1;
    notes.push(`FAIL record - ${error.message}`);
  }
  exchanges.sort((left, right) => left.seq - right.seq);
  if (browser) await browser.close();
  evidence.failures = failures;
  evidence.notes = notes;
  writeFileSync(`${output}/browser_evidence.json`, `${JSON.stringify(evidence, null, 2)}\n`);
  console.log(notes.join("\n"));
  process.exit(failures === 0 ? 0 : 1);
}
