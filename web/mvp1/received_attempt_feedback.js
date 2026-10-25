/** Safe feedback for one validated received-lesson attempt.

Server strings are text nodes. This does not execute a recommendation, and
it does not describe a continue action as mastery or lesson completion.
*/

/**
 * @param {ParentNode} container
 * @param {object} document
 */
export function renderEvaluatedFeedback(container, document) {
  const view = container.ownerDocument;
  const evaluation = document.evaluation;
  const summary = evaluation.summary;
  const action = evaluation.primary_next_action;
  const messages = document.messages;
  container.replaceChildren(
    heading(view, "Attempt feedback"),
    line(view, "Attempt", document.attempt_id),
    line(view, "Matched", String(summary.matched_count)),
    line(view, "Missing", String(summary.missing_count)),
    line(view, "Extra", String(summary.extra_count)),
    findingList(view, evaluation.findings, messages),
    recommendation(view, action, messages),
    warningList(view, document),
    line(view, "MIDI input", document.hardware_status.midi_input),
    line(view, "Audio output", document.hardware_status.audio_output),
  );
}

/**
 * @param {ParentNode} container
 * @param {object} document
 */
export function renderInterruptedFeedback(container, document) {
  const view = container.ownerDocument;
  container.replaceChildren(
    heading(view, "Attempt interrupted"),
    line(view, "Attempt", document.attempt_id),
    paragraph(view, "No evaluation was produced."),
    warningList(view, document),
    line(view, "MIDI input", document.hardware_status.midi_input),
    line(view, "Audio output", document.hardware_status.audio_output),
  );
}

/**
 * Warnings and unmatched note-offs, without an evaluation claim.
 *
 * @param {ParentNode} container
 * @param {object} document
 */
export function renderCapturedEvidence(container, document) {
  const view = container.ownerDocument;
  container.replaceChildren(warningList(view, document));
}

/**
 * @param {ParentNode} container
 */
export function clearAttemptFeedback(container) {
  container.replaceChildren();
}

/**
 * Apply guidance on the score channel. Playback and the active-event set stay
 * with the caller.
 *
 * @param {{ applyGuidance?: (projection: object) => unknown }} coordinator
 * @param {object} guidance
 */
export function presentGuidance(coordinator, guidance) {
  if (!coordinator || typeof coordinator.applyGuidance !== "function") return null;
  return coordinator.applyGuidance(guidance);
}

/**
 * @param {Document} view
 * @param {string} text
 */
function heading(view, text) {
  const node = view.createElement("h2");
  node.textContent = text;
  return node;
}

/**
 * @param {Document} view
 * @param {string} label
 * @param {string} value
 */
function line(view, label, value) {
  const node = view.createElement("p");
  const name = view.createElement("span");
  name.textContent = `${label}: `;
  const body = view.createElement("span");
  body.textContent = value;
  node.append(name, body);
  return node;
}

/**
 * @param {Document} view
 * @param {string} text
 */
function paragraph(view, text) {
  const node = view.createElement("p");
  node.textContent = text;
  return node;
}

/**
 * @param {Document} view
 * @param {object[]} findings
 * @param {Record<string, string>} messages
 */
function findingList(view, findings, messages) {
  const list = view.createElement("ul");
  for (const finding of findings) {
    const item = view.createElement("li");
    const key = typeof finding?.message_key === "string" ? finding.message_key : "";
    const kind = typeof finding?.finding_type === "string" ? finding.finding_type : "finding";
    item.textContent = `${kind}: ${messageText(messages, key)}`;
    list.append(item);
  }
  return list;
}

/**
 * @param {Document} view
 * @param {object} action
 * @param {Record<string, string>} messages
 */
function recommendation(view, action, messages) {
  const block = view.createElement("div");
  const key = typeof action?.message_key === "string" ? action.message_key : "";
  const kind = typeof action?.action_type === "string" ? action.action_type : "";
  block.append(paragraph(view, `Recommendation: ${kind}`));
  block.append(paragraph(view, messageText(messages, key)));
  if (kind === "continue") {
    block.append(paragraph(
      view,
      "No immediate repetition is required under this attempt policy.",
    ));
  }
  return block;
}

/**
 * @param {Document} view
 * @param {object} document
 */
function warningList(view, document) {
  const list = view.createElement("ul");
  const warnings = document.raw_capture?.warnings;
  if (Array.isArray(warnings)) {
    for (const warning of warnings) {
      if (typeof warning !== "string" || warning.length === 0) continue;
      const item = view.createElement("li");
      item.textContent = warning;
      list.append(item);
    }
  }
  for (const note of document.unmatched_note_offs) {
    const item = view.createElement("li");
    const midi = Number.isInteger(note.midi_note) ? String(note.midi_note) : "";
    item.textContent = `Unmatched note-off ${midi}`;
    list.append(item);
  }
  return list;
}

/**
 * @param {Record<string, string>} messages
 * @param {string} key
 */
function messageText(messages, key) {
  const text = messages?.[key];
  return typeof text === "string" ? text : key;
}
