/** Results panel helpers for Educational PracticeEvaluationResultV1. */

export function renderResultsPanel(root, payload) {
  if (!root) return;
  root.replaceChildren();
  if (!payload?.evaluation) {
    root.textContent = "No practice evaluation yet.";
    return;
  }
  const evaluation = payload.evaluation;
  const messages = payload.messages || {};
  const primary = evaluation.primary_next_action;
  const summary = document.createElement("div");
  summary.className = "results-summary";
  summary.innerHTML = `
    <p class="results-action" data-action="${primary.action_type}">
      <strong>Next:</strong> ${messages[primary.message_key] || primary.message_key}
    </p>
    <p class="hint subtle">
      CONTINUE means no immediate repetition is required under this policy —
      not mastery.
    </p>
    <p class="hint">
      Findings: ${evaluation.findings.length} · Actionable:
      ${evaluation.summary.actionable_finding_count}
    </p>
  `;
  root.append(summary);

  const list = document.createElement("ul");
  list.className = "results-findings";
  for (const finding of evaluation.findings) {
    const item = document.createElement("li");
    item.dataset.severity = finding.severity;
    item.dataset.type = finding.finding_type;
    item.textContent = messages[finding.message_key] || finding.message_key;
    list.append(item);
  }
  root.append(list);

  const hardware = document.createElement("p");
  hardware.className = "hint subtle";
  const midi = payload.hardware_status?.midi_input || "UNVERIFIED_PHYSICAL_MIDI_INPUT";
  const audio = payload.hardware_status?.audio_output || "UNVERIFIED_AUDIO_OUTPUT";
  hardware.textContent = `Hardware: ${midi} · ${audio}`;
  root.append(hardware);
}

export function focusRangeFromEvaluation(evaluation, projection) {
  const focus = evaluation?.summary?.focus_ranges?.[0];
  if (!focus || !projection?.notes?.length) return null;
  const notes = projection.notes;
  const startNote =
    notes.find((note) => note.onset_tick === focus.start_tick) ||
    notes.find((note) => note.onset_tick >= focus.start_tick) ||
    notes[0];
  const endNote =
    [...notes].reverse().find((note) => note.onset_tick <= focus.end_tick) ||
    notes[notes.length - 1];
  return {
    startSeconds: startNote.onset_seconds,
    endSeconds: endNote.release_seconds ?? endNote.onset_seconds,
    findingIds: focus.finding_ids || [],
  };
}
