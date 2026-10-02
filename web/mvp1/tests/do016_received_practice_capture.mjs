/**
 * Browser witness for DO-016 Stage 6.
 *
 * Drives the inbox and practice page in headless Chrome. Scheduling evidence
 * shows that the reference scheduler accepted events. It does not certify
 * that a speaker produced sound.
 */

import { mkdirSync, writeFileSync } from "node:fs";

const puppeteer = await import("/tmp/inbox-smoke/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js");

const base = process.argv[2];
const output = process.argv[3];
mkdirSync(output, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: "/usr/local/bin/google-chrome",
  headless: "new",
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--autoplay-policy=no-user-gesture-required"],
});
const notes = [];
let failures = 0;
const page = await browser.newPage();
page.setDefaultTimeout(60000);
page.on("console", (message) => {
  notes.push(`console ${message.type()}: ${message.text()}`);
});
page.on("pageerror", (error) => {
  notes.push(`pageerror: ${error.message}`);
});
page.on("requestfailed", (request) => {
  notes.push(`request failed: ${request.url()} ${request.failure()?.errorText || ""}`);
});
await page.setViewport({ width: 1280, height: 900 });

function check(name, ok, detail = "") {
  notes.push(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failures += 1;
}

async function shot(name) {
  const path = `${output}/${name}.png`;
  await page.screenshot({ path, fullPage: true });
}

async function text(selector) {
  return page.$eval(selector, (node) => node.textContent || "");
}

async function openInbox() {
  await page.goto(`${base}/lesson-inbox.html`, { waitUntil: "networkidle0" });
  await page.waitForFunction(() => document.querySelector("#inbox-status").textContent === "");
}

async function selectDelivery(id) {
  const clicked = await page.$$eval(
    "#delivery-list button",
    (buttons, deliveryId) => {
      const button = buttons.find((item) => item.deliveryId === deliveryId);
      if (!button) return false;
      button.click();
      return true;
    },
    id,
  );
  if (!clicked) throw new Error(`no inbox row for ${id}`);
}

try {
  await openInbox();
  await selectDelivery("delivery-practice");
  await page.waitForFunction(
    () => document.querySelector("#choose").disabled === false
      || document.querySelector("#status").classList.contains("is-error"),
  );
  check(
    "choose is available for an unchosen delivery",
    await page.$eval("#choose", (node) => node.disabled === false),
    await text("#status"),
  );
  check("open practice disabled before choice", await page.$eval("#open-practice", (node) => !node.hasAttribute("href")));
  await page.click("#choose");
  await page.waitForFunction(() => document.querySelector("#open-practice").getAttribute("href"));
  const href = await page.$eval("#open-practice", (node) => node.getAttribute("href"));
  check("open practice encodes only the delivery id", href === "lesson-practice.html?delivery_id=delivery-practice");
  check("choice did not navigate by itself", page.url().includes("lesson-inbox.html"));
  await shot("01-inbox-chosen");
  await page.click("#open-practice");
  await page.waitForFunction(() => /Paused/.test(document.querySelector("#status").textContent));
  check("practice stays paused", (await text("#status")).includes("Paused"));
  check("sound starts off", await page.$eval("#sound-enabled", (node) => node.checked === false));
  await page.waitForFunction(() => document.querySelectorAll("#scrollCanvas .note").length > 0);
  await page.waitForFunction(() => document.querySelector("#tabView").childElementCount > 0);
  await page.waitForFunction(() => document.querySelector("#notationView").childElementCount > 0);
  check("fretboard, tab, and notation are present", true);
  await shot("02-practice-paused-desktop");

  await page.click("#btn-play");
  await page.waitForFunction(() => document.querySelector("#status").textContent.includes("Playing"));
  await page.click("#btn-pause");
  await page.waitForFunction(() => document.querySelector("#status").textContent.includes("Paused"));
  await page.$eval("#seek", (node) => {
    node.value = "250";
    node.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.click('[data-rate="0.75"]');
  const ratePressed = await page.$eval('[data-rate="0.75"]', (node) => node.getAttribute("aria-pressed"));
  check("rate control is pressed", ratePressed === "true");
  const loopBefore = await page.$eval("#loop-enabled", (node) => node.checked);
  await page.click("#loop-enabled");
  const loopAfter = await page.$eval("#loop-enabled", (node) => node.checked);
  check("loop can be switched", loopBefore !== loopAfter);
  await page.click("#btn-play");
  await page.click("#sound-enabled");
  await page.waitForFunction(() => document.querySelector("#audio-status").textContent.includes("Sound ready"));
  await page.waitForFunction(
    () => Number(document.querySelector("#audio-status").dataset.scheduledNotes) > 0,
    { timeout: 4000 },
  ).catch(() => {});
  const scheduled = await page.$eval("#audio-status", (node) => node.dataset.scheduledNotes || "0");
  check("scheduler accepted at least one event", Number(scheduled) > 0, `scheduled=${scheduled}`);
  await shot("03-playing-with-sound");

  await page.click("#refresh-lesson");
  await page.waitForFunction(() => /Paused/.test(document.querySelector("#status").textContent));
  check("refresh returns to paused", (await text("#status")).includes("Playback has not started") || (await text("#status")).includes("Paused"));
  check("refresh clears sound", await page.$eval("#sound-enabled", (node) => node.checked === false));
  await shot("04-refreshed");

  await page.reload({ waitUntil: "networkidle0" });
  await page.waitForFunction(() => /Paused/.test(document.querySelector("#status").textContent));
  check("reload stays paused", (await text("#status")).includes("Paused"));
  check("reload leaves sound off", await page.$eval("#sound-enabled", (node) => node.checked === false));
  const playedOnLoad = await page.$eval("#status", (node) => node.textContent.includes("Playing"));
  check("reload does not autoplay", playedOnLoad === false);
  await shot("05-reloaded");

  const failuresToShow = [
    ["delivery-missing-choice", "unknown_practice_choice"],
    ["delivery-removed", "unknown delivery_id"],
    ["delivery-corrupt", "integrity_mismatch"],
    ["delivery-stale", "stale_preview"],
  ];
  for (const [id, expected] of failuresToShow) {
    await page.goto(`${base}/lesson-practice.html?delivery_id=${encodeURIComponent(id)}`, {
      waitUntil: "networkidle0",
    });
    await page.waitForFunction(() => document.querySelector("#status").classList.contains("is-error"));
    const status = await text("#status");
    check(`${id} fails closed`, status.toLowerCase().includes(expected) || status.includes("invalid"), status);
    check(`${id} leaves playback off`, await page.$eval("#btn-play", (node) => node.disabled));
    await shot(`06-${id}`);
  }

  await page.goto(`${base}/lesson-practice.html?delivery_id=delivery-practice`, { waitUntil: "networkidle0" });
  await page.waitForFunction(() => /Paused/.test(document.querySelector("#status").textContent));
  await page.setViewport({ width: 390, height: 844 });
  await shot("07-narrow");
  const playVisible = await page.$eval("#btn-play", (node) => {
    const box = node.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  });
  check("narrow layout keeps play reachable", playVisible);
  await page.focus("#btn-play");
  const focused = await page.evaluate(() => document.activeElement?.id);
  check("play control is keyboard focusable", focused === "btn-play");
  await page.setViewport({ width: 1280, height: 900 });
  await shot("08-desktop-again");
} catch (error) {
  failures += 1;
  notes.push(`FAIL driver — ${error.stack || error.message}`);
  try {
    notes.push(`page: ${await page.evaluate(() => document.body?.innerText?.slice(0, 500) || "")}`);
  } catch (readError) {
    notes.push(`page read failed: ${readError.message}`);
  }
  try {
    await shot("99-driver-error");
  } catch {
    notes.push("FAIL screenshot after driver error");
  }
} finally {
  await browser.close();
}

const summary = {
  stage: "DO-016 Stage 6",
  base,
  failures,
  notes,
  physical_audio: "not certified",
};
writeFileSync(`${output}/summary.json`, `${JSON.stringify(summary, null, 2)}\n`);
console.log(summary.notes.join("\n"));
process.exit(failures === 0 ? 0 : 1);
