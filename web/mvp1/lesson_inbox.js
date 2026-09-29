/** Local lesson inbox.

The list is summary metadata. Choosing happens only from a fresh READY
preview of the selected delivery, and only when choice GET says no choice is
stored. This page does not receive deliveries, accept on a student's behalf,
or start practice.
*/

import { LessonDeliveryClient } from "./lesson_delivery_client.js";

const DIGEST = /^sha256:[0-9a-f]{64}$/;

const SUMMARY_FIELDS = [
  ["Delivery", "delivery_id"],
  ["Assignment", "assignment_id"],
  ["Content", "content_id"],
  ["Sender", "sender_ref"],
  ["Recipient label", "recipient_ref"],
  ["Classroom", "classroom_ref"],
];

/**
 * @param {ParentNode} root
 * @param {{ client?: LessonDeliveryClient }} [options]
 */
export function mountLessonInbox(root, { client = new LessonDeliveryClient() } = {}) {
  const document = root.ownerDocument;
  if (!document) throw new Error("lesson inbox root has no document");

  const refreshInboxButton = required(root, "#refresh-inbox");
  const refreshSelectedButton = required(root, "#refresh-selected");
  const listEl = required(root, "#delivery-list");
  const emptyEl = required(root, "#inbox-empty");
  const inboxStatus = required(root, "#inbox-status");
  const previewPlaceholder = required(root, "#preview-placeholder");
  const previewFields = required(root, "#preview-fields");
  const statusEl = required(root, "#status");
  const chooseButton = required(root, "#choose");
  const choiceStatus = required(root, "#choice-status");
  const choiceNote = required(root, "#choice-note");
  const choiceFields = required(root, "#choice-fields");

  let listGeneration = 0;
  let selectionGeneration = 0;
  /** @type {string|null} */
  let selectedId = null;
  /** @type {object|null} */
  let pinnedPreview = null;
  let choosable = false;
  /** @type {{ status: number, error: string|null }|null} */
  let blocking = null;
  /** @type {Promise<void>} */
  let idle = Promise.resolve();

  function track(promise) {
    idle = promise.then(
      () => undefined,
      () => undefined,
    );
    return promise;
  }

  function renderStatus() {
    if (!blocking) {
      statusEl.textContent = "";
      statusEl.classList.remove("is-error");
      return;
    }
    statusEl.textContent = failureMessage(blocking);
    statusEl.classList.add("is-error");
  }

  function markPressed() {
    for (const item of listEl.children) {
      const button = item.children[0];
      if (!button) continue;
      button.setAttribute("aria-pressed", button.deliveryId === selectedId ? "true" : "false");
    }
  }

  function clearChoiceClaim() {
    choiceStatus.textContent = "";
    choiceNote.textContent = "";
    choiceFields.hidden = true;
    choiceFields.replaceChildren();
  }

  function clearPreview() {
    pinnedPreview = null;
    previewFields.hidden = true;
    previewFields.replaceChildren();
    previewPlaceholder.hidden = false;
  }

  function clearSelection() {
    selectionGeneration += 1;
    selectedId = null;
    choosable = false;
    blocking = null;
    chooseButton.disabled = true;
    refreshSelectedButton.disabled = true;
    clearPreview();
    previewPlaceholder.textContent = "Select a delivery to request a fresh preview.";
    clearChoiceClaim();
    renderStatus();
    markPressed();
  }

  function renderList(deliveries) {
    const items = [];
    for (const row of deliveries) {
      if (!row || typeof row.delivery_id !== "string" || row.delivery_id.length === 0) continue;
      const deliveryId = row.delivery_id;
      const button = document.createElement("button");
      button.type = "button";
      button.deliveryId = deliveryId;
      button.setAttribute("aria-pressed", "false");
      for (const [label, key] of SUMMARY_FIELDS) {
        const line = document.createElement("span");
        line.className = "meta";
        const name = document.createElement("span");
        name.className = "k";
        name.textContent = label;
        const value = document.createElement("span");
        value.className = "v";
        value.textContent = typeof row[key] === "string" ? row[key] : "";
        line.append(name, value);
        button.append(line);
      }
      button.addEventListener("click", () => {
        track(loadSelection(deliveryId));
      });
      const item = document.createElement("li");
      item.append(button);
      items.push(item);
    }
    listEl.replaceChildren(...items);
    emptyEl.hidden = items.length > 0;
    markPressed();
  }

  function renderPreview(preview) {
    fillPairs(document, previewFields, [
      ["Title", preview.title],
      ["Instructional objective", preview.instruction_objective],
      ["Teacher note", preview.teacher_note],
      ["Canonical events", String(preview.canonical_event_count)],
      ["Event ids", preview.canonical_event_ids.join(", ")],
      ["Assignment artifact digest", preview.assignment_artifact_digest, true],
      ["Assignment behavior digest", preview.assignment_behavior_digest, true],
      ["Assignment", preview.assignment_id],
      ["Content", preview.content_id],
      ["Preview status", preview.preview_status],
    ]);
    previewFields.hidden = false;
    previewPlaceholder.hidden = true;
  }

  function showChosen(body) {
    choiceStatus.textContent = "CHOSEN_FOR_PRACTICE";
    choiceNote.textContent = "This device recorded the choice. Practice has not started.";
    fillPairs(document, choiceFields, [
      ["Delivery", body.delivery_id],
      ["Assignment", body.assignment_id],
      ["Content", body.content_id],
    ]);
    choiceFields.hidden = false;
  }

  function showAvailable() {
    choiceStatus.textContent = "No practice choice is recorded for this delivery.";
    choiceNote.textContent = "";
    choiceFields.hidden = true;
    choiceFields.replaceChildren();
  }

  function applyChoice(choice, deliveryId) {
    choosable = false;
    chooseButton.disabled = true;
    if (isAvailable(choice)) {
      blocking = null;
      showAvailable();
      choosable = true;
      chooseButton.disabled = false;
      renderStatus();
      return;
    }
    if (isChosen(choice, deliveryId)) {
      blocking = null;
      showChosen(choice.body);
      renderStatus();
      return;
    }
    blocking = { status: choice.status, error: choice.error };
    clearChoiceClaim();
    renderStatus();
  }

  async function refreshInbox() {
    const generation = ++listGeneration;
    inboxStatus.textContent = "Loading deliveries.";
    const result = await client.list();
    if (generation !== listGeneration) return;
    if (!isDeliveryList(result)) {
      inboxStatus.textContent = failureMessage(result);
      return;
    }
    inboxStatus.textContent = "";
    const deliveries = result.body.deliveries;
    renderList(deliveries);
    const stillThere =
      selectedId !== null &&
      deliveries.some((row) => row && row.delivery_id === selectedId);
    if (selectedId !== null && !stillThere) clearSelection();
  }

  async function loadSelection(deliveryId) {
    const generation = ++selectionGeneration;
    const sameDelivery = deliveryId === selectedId;
    if (!sameDelivery) blocking = null;
    selectedId = deliveryId;
    pinnedPreview = null;
    choosable = false;
    chooseButton.disabled = true;
    refreshSelectedButton.disabled = false;
    clearPreview();
    previewPlaceholder.textContent = "Requesting a fresh preview.";
    clearChoiceClaim();
    renderStatus();
    markPressed();

    const preview = await client.preview(deliveryId);
    if (generation !== selectionGeneration) return;
    if (!isReadyPreview(preview, deliveryId)) {
      blocking = { status: preview.status, error: preview.error };
      clearPreview();
      previewPlaceholder.textContent = "Preview unavailable.";
      renderStatus();
      return;
    }

    pinnedPreview = preview.body;
    renderPreview(preview.body);
    renderStatus();

    const choice = await client.getChoice(deliveryId);
    if (generation !== selectionGeneration) return;
    if (pinnedPreview !== preview.body || selectedId !== deliveryId) return;
    applyChoice(choice, deliveryId);
  }

  async function chooseForPractice() {
    const generation = selectionGeneration;
    const preview = pinnedPreview;
    if (!choosable || !preview || preview.delivery_id !== selectedId) return;
    const deliveryId = preview.delivery_id;
    const artifactDigest = preview.assignment_artifact_digest;
    const behaviorDigest = preview.assignment_behavior_digest;
    choosable = false;
    chooseButton.disabled = true;
    const result = await client.choose(deliveryId, artifactDigest, behaviorDigest);
    if (generation !== selectionGeneration) return;
    if (pinnedPreview !== preview) return;
    if (isChosen(result, deliveryId)) {
      blocking = null;
      showChosen(result.body);
      renderStatus();
      return;
    }
    blocking = { status: result.status, error: result.error };
    clearChoiceClaim();
    renderStatus();
  }

  refreshInboxButton.addEventListener("click", () => {
    track(refreshInbox());
  });
  refreshSelectedButton.addEventListener("click", () => {
    if (selectedId === null) return;
    track(loadSelection(selectedId));
  });
  chooseButton.addEventListener("click", () => {
    track(chooseForPractice());
  });

  track(refreshInbox());

  return {
    idle: () => idle,
    refreshInbox: () => track(refreshInbox()),
    select: (deliveryId) => track(loadSelection(deliveryId)),
    refreshSelected: () => {
      if (selectedId === null) return track(Promise.resolve());
      return track(loadSelection(selectedId));
    },
    choose: () => track(chooseForPractice()),
  };
}

function bootLessonInbox() {
  if (typeof document === "undefined") return;
  const root = document.querySelector("[data-lesson-inbox]");
  if (!root) return;
  mountLessonInbox(root);
}

bootLessonInbox();

/**
 * @param {ParentNode} root
 * @param {string} selector
 */
function required(root, selector) {
  const node = root.querySelector(selector);
  if (!node) throw new Error(`lesson inbox is missing ${selector}`);
  return node;
}

/**
 * @param {Document} document
 * @param {Element} list
 * @param {Array<[string, unknown, boolean?]>} rows
 */
function fillPairs(document, list, rows) {
  const nodes = [];
  for (const [label, value, mono] of rows) {
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    if (mono) detail.className = "mono";
    detail.textContent = value == null ? "None" : String(value);
    nodes.push(term, detail);
  }
  list.replaceChildren(...nodes);
}

/**
 * @param {{ status?: number, error?: string|null }} failure
 */
function failureMessage(failure) {
  const status =
    failure && Number.isInteger(failure.status) && failure.status > 0
      ? String(failure.status)
      : "unavailable";
  const code =
    failure && typeof failure.error === "string" && failure.error.length > 0
      ? failure.error
      : "unavailable";
  let text = `Request failed (${status}, ${code}).`;
  if (failure && failure.error === "stale_preview") {
    text += " Refresh the selected delivery before choosing again.";
  }
  return text;
}

/**
 * @param {{ ok?: boolean, status?: number, body?: { deliveries?: unknown } }} result
 */
function isDeliveryList(result) {
  return Boolean(result?.ok && result.status === 200 && Array.isArray(result.body?.deliveries));
}

/**
 * @param {{ ok?: boolean, status?: number, body?: object }} result
 * @param {string} deliveryId
 */
function isReadyPreview(result, deliveryId) {
  if (!result?.ok || result.status !== 200) return false;
  const body = result.body;
  if (!body || typeof body !== "object") return false;
  if (body.preview_status !== "READY") return false;
  if (body.delivery_id !== deliveryId) return false;
  if (typeof body.assignment_id !== "string" || body.assignment_id.length === 0) return false;
  if (typeof body.content_id !== "string" || body.content_id.length === 0) return false;
  if (!DIGEST.test(body.assignment_artifact_digest)) return false;
  if (!DIGEST.test(body.assignment_behavior_digest)) return false;
  if (typeof body.title !== "string" || body.title.length === 0) return false;
  if (!Number.isInteger(body.canonical_event_count) || body.canonical_event_count < 1) {
    return false;
  }
  if (!Array.isArray(body.canonical_event_ids) || body.canonical_event_ids.length === 0) {
    return false;
  }
  if (!body.canonical_event_ids.every((id) => typeof id === "string" && id.length > 0)) {
    return false;
  }
  if (body.instruction_objective !== null && typeof body.instruction_objective !== "string") {
    return false;
  }
  if (body.teacher_note !== null && typeof body.teacher_note !== "string") return false;
  return true;
}

/**
 * @param {{ status?: number, error?: string|null }} result
 */
function isAvailable(result) {
  return result?.status === 404 && result?.error === "unknown_practice_choice";
}

/**
 * @param {{ ok?: boolean, status?: number, body?: object }} result
 * @param {string} deliveryId
 */
function isChosen(result, deliveryId) {
  if (!result?.ok || (result.status !== 200 && result.status !== 201)) return false;
  const body = result.body;
  if (!body || typeof body !== "object") return false;
  if (body.choice_status !== "CHOSEN_FOR_PRACTICE") return false;
  if (body.delivery_id !== deliveryId) return false;
  if (typeof body.assignment_id !== "string" || typeof body.content_id !== "string") return false;
  if (!DIGEST.test(body.assignment_artifact_digest)) return false;
  if (!DIGEST.test(body.assignment_behavior_digest)) return false;
  return true;
}
