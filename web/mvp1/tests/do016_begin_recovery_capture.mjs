/**
 * Browser half of the keyed Begin recovery witness.
 * Restart and lost responses are real. The preparation barrier is the parent.
 */

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

function record(scenario, source, status, requestText, responseText) {
  exchanges.push({
    scenario,
    source,
    status,
    request: JSON.parse(requestText || "{}"),
    response: JSON.parse(responseText || "{}"),
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
  const control = await connectControl(launch.control_port);
  const page = await browser.newPage();
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
        const text = await forwarded.text();
        record("W1", "forwarded_server", forwarded.status, posted, text);
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

  // W2: recovery reaches the server before the delayed Begin is released.
  scenarios.W2 = {};
  let delayed = false;
  await page.setRequestInterception(true);
  page.on("request", async (request) => {
    try {
      if (!delayed && request.url().endsWith(BEGIN)) {
        delayed = true;
        const posted = request.postData() || "{}";
        const recovered = await control.request("recover", { body: JSON.parse(posted) });
        record("W2", "recovery_before_begin", recovered.status, posted, JSON.stringify(recovered.response));
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
  await control.request("arm");
  let blockedBegin = false;
  await page.setRequestInterception(true);
  page.on("request", async (request) => {
    try {
      if (!blockedBegin && request.url().endsWith(BEGIN)) {
        blockedBegin = true;
        const posted = request.postData() || "{}";
        const barrier = control.request("recover-while-blocked", { body: JSON.parse(posted) });
        await request.continue();
        const recovered = await barrier;
        record("W3", "recovery_during_prepare", recovered.status, posted, JSON.stringify(recovered.response));
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

  // W4: hide one successful recovery, then repeat it.
  scenarios.W4 = {};
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
        record("W4", "forwarded_begin", forwarded.status, posted, await forwarded.text());
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
        const text = await forwarded.text();
        record("W4", "forwarded_recovery", forwarded.status, posted, text);
        scenarios.W4.first = JSON.parse(text);
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

  // W5: a restarted process tombs the key and refuses the delayed Begin.
  scenarios.W5 = {};
  let restartBegin = "";
  await page.setRequestInterception(true);
  page.on("request", async (request) => {
    try {
      if (!restartBegin && request.url().endsWith(BEGIN)) {
        restartBegin = request.postData() || "{}";
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
  const restarted = await control.request("restart");
  evidence.epochs.push({ name: "B", pid: restarted.pid, previous_pid: restarted.previous_pid });
  await page.click("#btn-resolve-start");
  await page.waitForFunction(() => /No attempt is available/.test(
    document.querySelector("#attempt-status")?.textContent || ""
  ));
  const replay = await control.request("replay-begin", { body: JSON.parse(restartBegin) });
  record("W5", "replayed_begin", replay.status, restartBegin, JSON.stringify(replay.response));
  check("restart refuses the delayed begin", replay.status === 409 && replay.response?.error === "begin_request_closed");

  evidence.complete = failures === 0;
} catch (error) {
  failures += 1;
  notes.push(`FAIL driver - ${error.stack || error.message}`);
  evidence.complete = false;
} finally {
  if (browser) await browser.close();
  evidence.failures = failures;
  evidence.notes = notes;
  writeFileSync(`${output}/browser_evidence.json`, `${JSON.stringify(evidence, null, 2)}\n`);
  console.log(notes.join("\n"));
  process.exit(failures === 0 ? 0 : 1);
}
