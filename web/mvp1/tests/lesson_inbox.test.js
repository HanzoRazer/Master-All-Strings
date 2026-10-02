import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { mountLessonInbox } from "../lesson_inbox.js";

const repoFile = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const inboxSource = repoFile("../lesson_inbox.js");
const pageSource = repoFile("../lesson-inbox.html");

const ART = `sha256:${"ab".repeat(32)}`;
const BEH = `sha256:${"cd".repeat(32)}`;
const ART_B = `sha256:${"ef".repeat(32)}`;
const BEH_B = `sha256:${"12".repeat(32)}`;
const LIST_DIGEST = `sha256:${"99".repeat(32)}`;
const NASTY = "<img src=x onerror=alert(1)>";

class El {
  constructor(tag, doc) {
    this.tagName = tag.toUpperCase();
    this.ownerDocument = doc;
    this.children = [];
    this.id = "";
    this.className = "";
    this.hidden = false;
    this.disabled = false;
    this.type = "";
    this.deliveryId = undefined;
    this.attributes = {};
    this.listeners = {};
    this._text = "";
    const classes = new Set();
    this.classList = {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
    };
  }

  get textContent() {
    if (this.children.length > 0) return this.children.map((child) => child.textContent).join("");
    return this._text;
  }

  set textContent(value) {
    this._text = value == null ? "" : String(value);
    this.children = [];
  }

  set innerHTML(value) {
    this.ownerDocument.innerHtmlUsed = true;
    this._text = String(value);
    this.children = [];
    if (String(value).toLowerCase().includes("<img")) {
      this.children.push(this.ownerDocument.createElement("img"));
    }
  }

  append(...nodes) {
    this.children.push(...nodes);
  }

  replaceChildren(...nodes) {
    this.children = [...nodes];
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return Object.hasOwn(this.attributes, name) ? this.attributes[name] : null;
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  addEventListener(type, handler) {
    (this.listeners[type] ||= []).push(handler);
  }

  click() {
    if (this.disabled) return;
    for (const handler of this.listeners.click || []) handler();
  }
}

function createDocument() {
  return {
    innerHtmlUsed: false,
    createElement(tag) {
      return new El(tag, this);
    },
  };
}

function findId(node, id) {
  if (node.id === id) return node;
  for (const child of node.children) {
    const found = findId(child, id);
    if (found) return found;
  }
  return null;
}

function buildRoot() {
  const document = createDocument();
  const root = document.createElement("main");
  root.querySelector = (selector) => findId(root, selector.slice(1));
  const add = (tag, id) => {
    const node = document.createElement(tag);
    node.id = id;
    root.append(node);
    return node;
  };
  add("button", "refresh-inbox");
  const refreshSelected = add("button", "refresh-selected");
  refreshSelected.disabled = true;
  add("ul", "delivery-list");
  const empty = add("p", "inbox-empty");
  empty.hidden = true;
  add("p", "inbox-status");
  add("p", "preview-placeholder");
  const previewFields = add("dl", "preview-fields");
  previewFields.hidden = true;
  add("p", "status");
  const choose = add("button", "choose");
  choose.disabled = true;
  const openPractice = add("a", "open-practice");
  openPractice.setAttribute("aria-disabled", "true");
  add("p", "choice-status");
  add("p", "choice-note");
  const choiceFields = add("dl", "choice-fields");
  choiceFields.hidden = true;
  return root;
}

function summary(id, extra = {}) {
  return {
    delivery_id: id,
    assignment_id: `assignment-${id}`,
    content_id: `content-${id}`,
    sender_ref: "teacher-ana",
    recipient_ref: "student-bo",
    classroom_ref: "class-7b",
    assignment_artifact_digest: LIST_DIGEST,
    title: "Blues Turnaround",
    preview_status: "READY",
    choice_status: "CHOSEN_FOR_PRACTICE",
    ...extra,
  };
}

function listOf(rows) {
  return { ok: true, status: 200, error: null, body: { count: rows.length, deliveries: rows } };
}

function ready(id, extra = {}) {
  return {
    ok: true,
    status: 200,
    error: null,
    body: {
      schema_id: "master_all_strings.lesson_delivery_preview",
      schema_version: "1.0.0",
      preview_status: "READY",
      delivery_id: id,
      assignment_id: "asg-1",
      content_id: "content-1",
      assignment_artifact_digest: ART,
      assignment_behavior_digest: BEH,
      title: "Blues Turnaround",
      canonical_event_count: 3,
      canonical_event_ids: ["ev-1", "ev-2", "ev-3"],
      playback_policy: {
        tempo_bpm: null, start_tick: null, end_tick: null, loop_enabled: false,
        count_in_bars: null, ticks_per_quarter: 480, source_tempo_bpm: 120,
      },
      spatial_policy: {
        instrument_profile_id: "guitar-standard-6", fingering_policy_id: "default",
        preferred_fret_min: null, preferred_fret_max: null, open_string_preference: "allow",
      },
      meter_change_count: 0,
      instruction_objective: "Play the turnaround cleanly",
      teacher_note: "Watch the third",
      ...extra,
    },
  };
}

function failed(status, error) {
  return {
    ok: false,
    status,
    error,
    body: null,
    detail: "INTERNAL_EXCEPTION_TEXT",
    title: "PARTIAL_TITLE",
    assignment_artifact_digest: ART,
  };
}

function unknown() {
  return failed(404, "unknown_practice_choice");
}

function chosen(id, status = 200) {
  return {
    ok: true,
    status,
    error: null,
    body: {
      schema_id: "master_all_strings.local_practice_choice",
      schema_version: "1.0.0",
      choice_status: "CHOSEN_FOR_PRACTICE",
      delivery_id: id,
      assignment_id: "asg-1",
      content_id: "content-1",
      assignment_artifact_digest: ART,
      assignment_behavior_digest: BEH,
    },
  };
}

function clientWith(handlers) {
  const calls = [];
  return {
    calls,
    async list() {
      calls.push({ method: "list" });
      return handlers.list();
    },
    async preview(id) {
      calls.push({ method: "preview", id });
      return handlers.preview(id);
    },
    async getChoice(id) {
      calls.push({ method: "getChoice", id });
      return handlers.getChoice(id);
    },
    async choose(id, artifact, behavior) {
      calls.push({ method: "choose", id, artifact, behavior });
      return handlers.choose(id, artifact, behavior);
    },
  };
}

async function mount(handlers) {
  const root = buildRoot();
  const client = clientWith(handlers);
  const ui = mountLessonInbox(root, { client });
  await ui.idle();
  const q = (id) => root.querySelector(`#${id}`);
  return { root, client, ui, q };
}

function rows(list) {
  return list.children.map((item) => item.children[0]);
}

function calls(client, method) {
  return client.calls.filter((call) => call.method === method);
}

function hasTag(node, tag) {
  if (node.tagName === tag) return true;
  return node.children.some((child) => hasTag(child, tag));
}

async function waitFor(predicate) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setImmediate(resolve));
  }
  throw new Error("timed out waiting for inbox state");
}

test("the page is a separate entry point and renders text, not HTML", () => {
  assert.match(pageSource, /Received on this device/);
  assert.match(pageSource, /Chosen for practice on this device/);
  assert.match(pageSource, /disappear when the server process ends/);
  assert.match(pageSource, /lesson-inbox\.css/);
  assert.match(pageSource, /lesson_inbox\.js/);
  assert.match(pageSource, /id="choose" disabled/);
  assert.doesNotMatch(pageSource, /styles\.css|app\.js|innerHTML|transport\.js|renderer\.js/);
  assert.doesNotMatch(
    inboxSource,
    /innerHTML|localStorage|sessionStorage|decodeURIComponent|location\.hash/,
  );
  assert.doesNotMatch(
    inboxSource,
    /from "\.\/(?:app|transport|renderer|notation|guided_session|evaluation|playback)/,
  );
});

test("empty and multiple deliveries stay summary metadata in server order", async () => {
  const empty = await mount({
    list: () => listOf([]),
    preview: () => ready("none"),
    getChoice: () => unknown(),
    choose: () => chosen("none", 201),
  });
  assert.equal(empty.q("inbox-empty").hidden, false);
  assert.equal(rows(empty.q("delivery-list")).length, 0);
  assert.equal(calls(empty.client, "preview").length, 0);
  assert.equal(calls(empty.client, "getChoice").length, 0);
  assert.equal(empty.q("choose").disabled, true);

  const inbox = await mount({
    list: () => listOf([summary("m-2"), summary("m-1"), { delivery_id: "" }]),
    preview: () => ready("m-2"),
    getChoice: () => unknown(),
    choose: () => chosen("m-2", 201),
  });
  const buttons = rows(inbox.q("delivery-list"));
  assert.deepEqual(
    buttons.map((button) => button.deliveryId),
    ["m-2", "m-1"],
  );
  const listText = inbox.q("delivery-list").textContent;
  assert.match(listText, /Recipient label/);
  assert.match(listText, /student-bo/);
  assert.match(listText, /teacher-ana/);
  assert.match(listText, /class-7b/);
  assert.match(listText, /assignment-m-2/);
  assert.equal(listText.includes("Blues Turnaround"), false);
  assert.equal(listText.includes("READY"), false);
  assert.equal(listText.includes("CHOSEN_FOR_PRACTICE"), false);
  assert.equal(listText.includes(LIST_DIGEST), false);
  assert.equal(listText.includes("authorize"), false);
  assert.equal(calls(inbox.client, "getChoice").length, 0);
  assert.equal(inbox.q("choose").disabled, true);
});

test("only a fresh READY preview can lead to Choose", async () => {
  const inbox = await mount({
    list: () => listOf([summary("delivery-001")]),
    preview: () => ready("delivery-001"),
    getChoice: () => unknown(),
    choose: () => chosen("delivery-001", 201),
  });
  await inbox.ui.select("delivery-001");
  const preview = inbox.q("preview-fields").textContent;
  assert.match(preview, /Blues Turnaround/);
  assert.match(preview, /Play the turnaround cleanly/);
  assert.match(preview, /Watch the third/);
  assert.match(preview, /ev-1, ev-2, ev-3/);
  assert.match(preview, new RegExp(ART));
  assert.match(preview, new RegExp(BEH));
  assert.match(preview, /READY/);
  assert.equal(inbox.q("choose").disabled, false);

  const blocked = [
    failed(404, "unknown delivery_id 'delivery-001'"),
    failed(409, "integrity_mismatch"),
    failed(422, "unresolvable_assignment"),
    {
      ok: true,
      status: 200,
      error: null,
      body: { preview_status: "READY", title: "PARTIAL_TITLE", delivery_id: "delivery-001" },
    },
    ready("someone-else"),
  ];
  for (const previewResult of blocked) {
    const ui = await mount({
      list: () => listOf([summary("delivery-001")]),
      preview: () => previewResult,
      getChoice: () => {
        throw new Error("choice GET must not run");
      },
      choose: () => {
        throw new Error("POST must not run");
      },
    });
    await ui.ui.select("delivery-001");
    assert.equal(ui.q("choose").disabled, true);
    assert.equal(ui.q("preview-fields").hidden, true);
    assert.equal(ui.q("preview-fields").textContent.includes("READY"), false);
    assert.equal(ui.q("preview-fields").textContent.includes("PARTIAL_TITLE"), false);
    assert.equal(ui.q("choice-status").textContent.includes("CHOSEN_FOR_PRACTICE"), false);
    assert.equal(ui.q("status").textContent.includes("INTERNAL_EXCEPTION_TEXT"), false);
    assert.equal(ui.q("status").textContent.includes("PARTIAL_TITLE"), false);
  }
});

test("opaque ids are passed through unchanged", async () => {
  const ids = ["100%", "a/b", "a b", "a#b", "a?b", "a&b", "a%2Fb"];
  for (const id of ids) {
    const inbox = await mount({
      list: () => listOf([summary(id)]),
      preview: () => ready(id),
      getChoice: () => unknown(),
      choose: () => chosen(id, 201),
    });
    rows(inbox.q("delivery-list"))[0].click();
    await inbox.ui.idle();
    assert.equal(calls(inbox.client, "preview")[0].id, id);
    assert.equal(calls(inbox.client, "getChoice")[0].id, id);
    assert.notEqual(id === "a%2Fb" && calls(inbox.client, "preview")[0].id === "a/b", true);
    await inbox.ui.choose();
    assert.equal(calls(inbox.client, "choose")[0].id, id);
    assert.equal(calls(inbox.client, "choose")[0].artifact, ART);
    assert.equal(calls(inbox.client, "choose")[0].behavior, BEH);
  }
});

test("unknown_practice_choice allows one explicit choice and a stored choice does not POST", async () => {
  const fresh = await mount({
    list: () => listOf([summary("delivery-001")]),
    preview: () => ready("delivery-001"),
    getChoice: () => unknown(),
    choose: () => chosen("delivery-001", 201),
  });
  await fresh.ui.select("delivery-001");
  assert.equal(fresh.q("choose").disabled, false);
  assert.match(fresh.q("choice-status").textContent, /No practice choice is recorded/);
  await fresh.ui.choose();
  assert.equal(calls(fresh.client, "choose").length, 1);
  assert.equal(calls(fresh.client, "choose")[0].artifact, ART);
  assert.notEqual(calls(fresh.client, "choose")[0].artifact, LIST_DIGEST);
  assert.equal(fresh.q("choice-status").textContent, "CHOSEN_FOR_PRACTICE");
  assert.match(fresh.q("choice-note").textContent, /Practice has not started/);
  assert.equal(fresh.q("choose").disabled, true);
  await fresh.ui.choose();
  assert.equal(calls(fresh.client, "choose").length, 1);

  const repeat = await mount({
    list: () => listOf([summary("delivery-001")]),
    preview: () => ready("delivery-001"),
    getChoice: () => unknown(),
    choose: () => chosen("delivery-001", 200),
  });
  await repeat.ui.select("delivery-001");
  await repeat.ui.choose();
  assert.equal(repeat.q("choice-status").textContent, "CHOSEN_FOR_PRACTICE");
  assert.equal(repeat.q("choose").disabled, true);

  const stored = await mount({
    list: () => listOf([summary("delivery-001")]),
    preview: () => ready("delivery-001"),
    getChoice: () => chosen("delivery-001", 200),
    choose: () => {
      throw new Error("POST must not run");
    },
  });
  await stored.ui.select("delivery-001");
  assert.equal(stored.q("choice-status").textContent, "CHOSEN_FOR_PRACTICE");
  assert.equal(stored.q("choose").disabled, true);
  await stored.ui.choose();
  assert.equal(calls(stored.client, "choose").length, 0);
});

test("choice and transport failures do not claim chosen or ready-to-choose", async () => {
  const choiceFailures = [
    failed(404, "unknown_delivery_id"),
    failed(409, "integrity_mismatch"),
    failed(409, "stale_preview"),
    failed(409, "choice_conflict"),
    failed(422, "unresolvable_assignment"),
    failed(500, "internal server error"),
    { ok: false, status: 500, error: null, body: null, detail: "<html>secret traceback</html>" },
    { ok: false, status: 0, error: null, body: null, detail: "INTERNAL_EXCEPTION_TEXT" },
    {
      ok: true,
      status: 200,
      error: null,
      body: { choice_status: "CHOSEN_FOR_PRACTICE", title: "PARTIAL_TITLE" },
    },
  ];
  for (const choiceResult of choiceFailures) {
    const inbox = await mount({
      list: () => listOf([summary("delivery-001")]),
      preview: () => ready("delivery-001"),
      getChoice: () => choiceResult,
      choose: () => {
        throw new Error("POST must not run");
      },
    });
    await inbox.ui.select("delivery-001");
    assert.equal(inbox.q("choose").disabled, true);
    assert.equal(inbox.q("choice-status").textContent.includes("CHOSEN_FOR_PRACTICE"), false);
    assert.equal(inbox.q("choice-status").textContent.includes("No practice choice"), false);
    assert.equal(inbox.q("status").textContent.includes("PARTIAL_TITLE"), false);
    assert.equal(inbox.q("status").textContent.includes("INTERNAL_EXCEPTION_TEXT"), false);
    assert.equal(inbox.q("status").textContent.includes("secret traceback"), false);
    if (typeof choiceResult.error === "string") {
      assert.match(inbox.q("status").textContent, new RegExp(choiceResult.error));
      assert.match(inbox.q("status").textContent, new RegExp(String(choiceResult.status)));
    }
    if (choiceResult.error === "stale_preview") {
      assert.match(inbox.q("status").textContent, /Refresh the selected delivery/);
    }
  }

  const previewDown = await mount({
    list: () => listOf([summary("delivery-001")]),
    preview: () => failed(500, "internal server error"),
    getChoice: () => {
      throw new Error("choice GET must not run");
    },
    choose: () => {
      throw new Error("POST must not run");
    },
  });
  await previewDown.ui.select("delivery-001");
  assert.equal(previewDown.q("choose").disabled, true);
  assert.match(previewDown.q("status").textContent, /500/);
  assert.match(previewDown.q("status").textContent, /internal server error/);
  assert.equal(previewDown.q("preview-fields").textContent.includes("READY"), false);
});

test("a stale POST does not retry or replace the pinned digests", async () => {
  let previewBody = ready("delivery-001");
  let choiceBody = unknown();
  const inbox = await mount({
    list: () => listOf([summary("delivery-001")]),
    preview: () => previewBody,
    getChoice: () => choiceBody,
    choose: () => failed(409, "stale_preview"),
  });
  await inbox.ui.select("delivery-001");
  assert.equal(inbox.q("choose").disabled, false);
  await inbox.ui.choose();
  assert.equal(calls(inbox.client, "choose").length, 1);
  assert.equal(calls(inbox.client, "choose")[0].artifact, ART);
  assert.equal(calls(inbox.client, "choose")[0].behavior, BEH);
  assert.equal(inbox.q("choose").disabled, true);
  assert.match(inbox.q("status").textContent, /409/);
  assert.match(inbox.q("status").textContent, /stale_preview/);
  assert.match(inbox.q("status").textContent, /Refresh the selected delivery/);
  assert.equal(inbox.q("status").textContent.includes("PARTIAL_TITLE"), false);
  assert.equal(inbox.q("choice-status").textContent.includes("CHOSEN_FOR_PRACTICE"), false);
  await inbox.ui.choose();
  assert.equal(calls(inbox.client, "choose").length, 1);

  previewBody = ready("delivery-001", {
    assignment_artifact_digest: ART_B,
    assignment_behavior_digest: BEH_B,
    title: "Refreshed title",
  });
  choiceBody = unknown();
  await inbox.ui.refreshSelected();
  assert.match(inbox.q("preview-fields").textContent, /Refreshed title/);
  assert.match(inbox.q("preview-fields").textContent, new RegExp(ART_B));
  assert.equal(inbox.q("choose").disabled, false);
  await inbox.ui.choose();
  assert.equal(calls(inbox.client, "choose").length, 2);
  assert.equal(calls(inbox.client, "choose")[1].artifact, ART_B);
  assert.equal(calls(inbox.client, "choose")[1].behavior, BEH_B);
});

test("a successful preview does not clear a choice conflict on its own", async () => {
  let choiceCalls = 0;
  let release;
  let started;
  const inbox = await mount({
    list: () => listOf([summary("delivery-001")]),
    preview: () =>
      ready("delivery-001", {
        title: choiceCalls === 0 ? "First title" : "Second title",
      }),
    getChoice: () => {
      choiceCalls += 1;
      if (choiceCalls === 1) return failed(409, "choice_conflict");
      return new Promise((resolve) => {
        release = resolve;
        started();
      });
    },
    choose: () => {
      throw new Error("POST must not run");
    },
  });
  await inbox.ui.select("delivery-001");
  assert.equal(inbox.q("choose").disabled, true);
  assert.match(inbox.q("status").textContent, /409/);
  assert.match(inbox.q("status").textContent, /choice_conflict/);
  assert.equal(inbox.q("choice-status").textContent.includes("No practice choice"), false);
  const gate = new Promise((resolve) => {
    started = resolve;
  });
  const refreshing = inbox.ui.refreshSelected();
  await gate;
  await waitFor(() => inbox.q("preview-fields").textContent.includes("Second title"));
  assert.equal(inbox.q("choose").disabled, true);
  assert.match(inbox.q("status").textContent, /choice_conflict/);
  assert.equal(calls(inbox.client, "choose").length, 0);
  release(failed(409, "choice_conflict"));
  await refreshing;
  assert.equal(inbox.q("choose").disabled, true);
  assert.match(inbox.q("status").textContent, /choice_conflict/);

  release = null;
  const enabling = new Promise((resolve) => {
    started = resolve;
  });
  choiceCalls = 1;
  const again = inbox.ui.refreshSelected();
  await enabling;
  release(unknown());
  await again;
  assert.equal(inbox.q("choose").disabled, false);
  assert.equal(inbox.q("status").textContent.includes("choice_conflict"), false);
});

test("a late response cannot paint another delivery", async () => {
  const previewGates = new Map();
  const inbox = await mount({
    list: () => listOf([summary("a"), summary("b")]),
    preview: (id) =>
      new Promise((resolve) => {
        previewGates.set(id, resolve);
      }),
    getChoice: (id) => (id === "a" ? chosen("a") : unknown()),
    choose: () => {
      throw new Error("POST must not run");
    },
  });
  const first = inbox.ui.select("a");
  const second = inbox.ui.select("b");
  await waitFor(() => previewGates.has("b"));
  previewGates.get("b")(ready("b", { title: "Title B" }));
  await second;
  previewGates.get("a")(ready("a", { title: "SECRET_A" }));
  await first;
  assert.match(inbox.q("preview-fields").textContent, /Title B/);
  assert.equal(inbox.q("preview-fields").textContent.includes("SECRET_A"), false);
  assert.equal(inbox.q("choice-status").textContent.includes("CHOSEN_FOR_PRACTICE"), false);
  assert.equal(inbox.q("choose").disabled, false);

  let releaseA;
  const delayed = await mount({
    list: () => listOf([summary("a"), summary("b")]),
    preview: (id) => ready(id, { title: id === "a" ? "Title A" : "Title B" }),
    getChoice: (id) => {
      if (id === "a") {
        return new Promise((resolve) => {
          releaseA = resolve;
        });
      }
      return unknown();
    },
    choose: () => {
      throw new Error("POST must not run");
    },
  });
  const pendingA = delayed.ui.select("a");
  await waitFor(() => calls(delayed.client, "getChoice").some((call) => call.id === "a"));
  await delayed.ui.select("b");
  releaseA(chosen("a"));
  await pendingA;
  assert.match(delayed.q("preview-fields").textContent, /Title B/);
  assert.equal(delayed.q("choice-status").textContent.includes("CHOSEN_FOR_PRACTICE"), false);
  assert.match(delayed.q("choice-status").textContent, /No practice choice is recorded/);
});

test("list refresh drops a missing selection and ignores its late preview", async () => {
  let listed = [summary("a")];
  let release;
  const inbox = await mount({
    list: () => listOf(listed),
    preview: () =>
      new Promise((resolve) => {
        release = resolve;
      }),
    getChoice: () => unknown(),
    choose: () => {
      throw new Error("POST must not run");
    },
  });
  const pending = inbox.ui.select("a");
  await waitFor(() => typeof release === "function");
  listed = [];
  await inbox.ui.refreshInbox();
  release(ready("a", { title: "SECRET_A" }));
  await pending;
  assert.equal(inbox.q("preview-fields").textContent.includes("SECRET_A"), false);
  assert.equal(inbox.q("refresh-selected").disabled, true);
  assert.equal(inbox.q("choose").disabled, true);
  assert.equal(rows(inbox.q("delivery-list")).length, 0);

  let releaseKept;
  const kept = await mount({
    list: () => listOf([summary("a")]),
    preview: () =>
      new Promise((resolve) => {
        releaseKept = resolve;
      }),
    getChoice: () => unknown(),
    choose: () => chosen("a", 201),
  });
  const selecting = kept.ui.select("a");
  await waitFor(() => typeof releaseKept === "function");
  await kept.ui.refreshInbox();
  releaseKept(ready("a", { title: "Kept title" }));
  await selecting;
  assert.match(kept.q("preview-fields").textContent, /Kept title/);
  assert.equal(kept.q("choose").disabled, false);
});

test("HTML-like delivery text is shown as text", async () => {
  const id = `id${NASTY}`;
  const inbox = await mount({
    list: () =>
      listOf([
        summary(id, {
          sender_ref: `sender${NASTY}`,
          recipient_ref: `recipient${NASTY}`,
          classroom_ref: `room${NASTY}`,
          assignment_id: `assignment${NASTY}`,
          content_id: `content${NASTY}`,
        }),
      ]),
    preview: () =>
      ready(id, {
        title: `title${NASTY}`,
        teacher_note: `note${NASTY}`,
        instruction_objective: `objective${NASTY}`,
        canonical_event_count: 1,
        canonical_event_ids: [`ev${NASTY}`],
      }),
    getChoice: () => unknown(),
    choose: () => chosen(id, 201),
  });
  assert.equal(inbox.root.ownerDocument.innerHtmlUsed, false);
  assert.equal(hasTag(inbox.root, "IMG"), false);
  assert.match(inbox.q("delivery-list").textContent, new RegExp(escapeRegExp(`sender${NASTY}`)));
  await inbox.ui.select(id);
  assert.match(inbox.q("preview-fields").textContent, new RegExp(escapeRegExp(`title${NASTY}`)));
  assert.match(inbox.q("preview-fields").textContent, new RegExp(escapeRegExp(`note${NASTY}`)));
  assert.equal(inbox.root.ownerDocument.innerHtmlUsed, false);
  assert.equal(hasTag(inbox.root, "IMG"), false);
});

test("inconsistent or unsupported previews never reach choice GET or POST", async () => {
  const invalid = [
    { canonical_event_count: 1 },
    { canonical_event_ids: ["ev-1", "ev-1", "ev-3"] },
    { canonical_event_ids: ["ev-1", " ", "ev-3"] },
    { assignment_artifact_digest: [ART] },
    { assignment_behavior_digest: [BEH] },
    { assignment_id: " " },
    { content_id: " " },
    { title: " " },
    { teacher_note: "" },
    { instruction_objective: " " },
    { playback_policy: null },
    { playback_policy: [] },
    { spatial_policy: undefined },
    { spatial_policy: "not a policy object" },
    { meter_change_count: -1 },
    { unexpected: "extra field" },
    { schema_id: "master_all_strings.local_practice_choice" },
    { schema_version: "2.0.0" },
    { schema_id: undefined },
    { schema_version: undefined },
  ];
  for (const extra of invalid) {
    const inbox = await mount({
      list: () => listOf([summary("delivery-001")]),
      preview: () => ready("delivery-001", extra),
      getChoice: () => unknown(),
      choose: () => chosen("delivery-001", 201),
    });
    await inbox.ui.select("delivery-001");
    await inbox.ui.choose();
    assert.equal(inbox.q("choose").disabled, true, JSON.stringify(extra));
    assert.equal(inbox.q("preview-fields").hidden, true);
    assert.equal(calls(inbox.client, "getChoice").length, 0);
    assert.equal(calls(inbox.client, "choose").length, 0);
  }
});

test("choice GET and POST must match every identity and digest pinned by the preview", async () => {
  const invalid = [
    { delivery_id: "another-delivery" },
    { assignment_id: "another-assignment" },
    { content_id: "another-content" },
    { assignment_artifact_digest: ART_B },
    { assignment_behavior_digest: BEH_B },
    { schema_id: "master_all_strings.lesson_delivery_preview" },
    { schema_version: "2.0.0" },
    { schema_id: undefined },
    { schema_version: undefined },
    { unexpected: "extra field" },
  ];
  for (const phase of ["GET", "POST"]) {
    for (const extra of invalid) {
      const response = chosen("delivery-001", phase === "GET" ? 200 : 201);
      Object.assign(response.body, extra);
      const inbox = await mount({
        list: () => listOf([summary("delivery-001")]),
        preview: () => ready("delivery-001"),
        getChoice: () => phase === "GET" ? response : unknown(),
        choose: () => response,
      });
      await inbox.ui.select("delivery-001");
      await inbox.ui.choose();
      assert.equal(inbox.q("choose").disabled, true, phase + JSON.stringify(extra));
      assert.equal(inbox.q("choice-fields").hidden, true);
      assert.equal(inbox.q("choice-status").textContent.includes("CHOSEN_FOR_PRACTICE"), false);
      assert.match(inbox.q("status").textContent, /Request failed/);
      assert.equal(calls(inbox.client, "choose").length, phase === "GET" ? 0 : 1);
      await inbox.ui.choose();
      assert.equal(calls(inbox.client, "choose").length, phase === "GET" ? 0 : 1);
    }
  }
});

test("a choice GET cannot claim creation with 201", async () => {
  const inbox = await mount({
    list: () => listOf([summary("delivery-001")]),
    preview: () => ready("delivery-001"),
    getChoice: () => chosen("delivery-001", 201),
    choose: () => chosen("delivery-001", 201),
  });
  await inbox.ui.select("delivery-001");
  await inbox.ui.choose();
  assert.equal(inbox.q("choose").disabled, true);
  assert.equal(inbox.q("choice-status").textContent.includes("CHOSEN_FOR_PRACTICE"), false);
  assert.equal(calls(inbox.client, "choose").length, 0);
});

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function openHref(inbox) {
  return inbox.q("open-practice").getAttribute("href");
}

test("Open practice stays disabled until a matching choice and clears on refresh", async () => {
  assert.match(pageSource, /id="open-practice"/);
  assert.doesNotMatch(pageSource, /id="open-practice"[^>]*href=/);
  let previewMode = "ready";
  let releasePreview;
  const inbox = await mount({
    list: () => listOf([summary("delivery-001"), summary("delivery-002")]),
    preview: (id) => {
      if (previewMode === "hold") {
        return new Promise((resolve) => {
          releasePreview = () => resolve(ready(id));
        });
      }
      return ready(id);
    },
    getChoice: () => unknown(),
    choose: (id) => chosen(id, 201),
  });
  await inbox.ui.select("delivery-001");
  assert.equal(inbox.q("choose").disabled, false);
  assert.equal(openHref(inbox), null);
  await inbox.ui.choose();
  assert.equal(calls(inbox.client, "choose").length, 1);
  assert.equal(openHref(inbox), "lesson-practice.html?delivery_id=delivery-001");

  previewMode = "hold";
  const refreshing = inbox.ui.refreshSelected();
  assert.equal(openHref(inbox), null);
  releasePreview();
  await refreshing;
  assert.equal(inbox.q("choose").disabled, false);
  assert.equal(openHref(inbox), null);
});

test("a stored choice and a created choice enable one opaque practice URL", async () => {
  const nasty = "a/b c?x=1&y=2#frag";
  const stored = await mount({
    list: () => listOf([summary(nasty)]),
    preview: () => ready(nasty),
    getChoice: () => chosen(nasty),
    choose: () => {
      throw new Error("stored choice must not POST");
    },
  });
  await stored.ui.select(nasty);
  assert.equal(stored.q("choose").disabled, true);
  const href = openHref(stored);
  assert.equal(href, `lesson-practice.html?${new URLSearchParams({ delivery_id: nasty })}`);
  assert.equal(href.includes(nasty), false);
  assert.equal(href.includes("sha256"), false);
  assert.equal(calls(stored.client, "choose").length, 0);

  let release;
  const created = await mount({
    list: () => listOf([summary("delivery-001"), summary("delivery-002")]),
    preview: (id) => ready(id),
    getChoice: () => unknown(),
    choose: (id) => new Promise((resolve) => {
      release = () => resolve(chosen(id, 201));
    }),
  });
  await created.ui.select("delivery-001");
  const pending = created.ui.choose();
  await created.ui.select("delivery-002");
  assert.equal(openHref(created), null);
  release();
  await pending;
  assert.equal(openHref(created), null);
  assert.equal(created.q("choice-status").textContent.includes("CHOSEN_FOR_PRACTICE"), false);
});
