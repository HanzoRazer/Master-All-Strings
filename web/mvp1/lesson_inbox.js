/** Local lesson inbox.

The list is summary metadata. Choosing happens only from a fresh READY
preview of the selected delivery, and only when choice GET says no choice is
stored. This page does not receive deliveries, accept on a student's behalf,
or start practice.
*/

import { LessonDeliveryClient } from "./lesson_delivery_client.js";
import {
  failureMessage,
  isAvailable,
  isChosen,
  isDeliveryList,
  isReadyPreview,
  practicePageHref,
} from "./lesson_delivery_validation.js";

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
  const openPractice = required(root, "#open-practice");
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
    setOpenPractice(null);
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

  function setOpenPractice(deliveryId) {
    if (deliveryId) {
      openPractice.setAttribute("href", practicePageHref(deliveryId));
      openPractice.setAttribute("aria-disabled", "false");
      return;
    }
    openPractice.removeAttribute("href");
    openPractice.setAttribute("aria-disabled", "true");
  }

  function applyChoice(choice, deliveryId) {
    choosable = false;
    chooseButton.disabled = true;
    setOpenPractice(null);
    if (isAvailable(choice)) {
      blocking = null;
      showAvailable();
      choosable = true;
      chooseButton.disabled = false;
      renderStatus();
      return;
    }
    if (isChosen(choice, pinnedPreview)) {
      blocking = null;
      showChosen(choice.body);
      setOpenPractice(choice.body.delivery_id);
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
    setOpenPractice(null);
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
    setOpenPractice(null);
    const result = await client.choose(deliveryId, artifactDigest, behaviorDigest);
    if (generation !== selectionGeneration) return;
    if (pinnedPreview !== preview) return;
    if (isChosen(result, preview, true)) {
      blocking = null;
      showChosen(result.body);
      setOpenPractice(result.body.delivery_id);
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
  openPractice.addEventListener("click", (event) => {
    if (!openPractice.getAttribute("href")) event.preventDefault();
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
