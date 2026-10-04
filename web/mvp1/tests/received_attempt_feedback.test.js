import assert from "node:assert/strict";
import test from "node:test";

import {
  clearAttemptFeedback,
  presentGuidance,
  renderCapturedEvidence,
  renderEvaluatedFeedback,
  renderInterruptedFeedback,
} from "../received_attempt_feedback.js";
import {
  beginDocument,
  evaluatedDocument,
  interruptedDocument,
} from "./received_attempt_fixture.js";

function element(document, tag) {
  return {
    tag,
    ownerDocument: document,
    children: [],
    _text: "",
    get textContent() {
      if (this.children.length > 0) return this.children.map((child) => child.textContent).join("");
      return this._text;
    },
    set textContent(value) {
      this._text = value == null ? "" : String(value);
      this.children = [];
    },
    set innerHTML(value) {
      document.innerHtmlUsed = true;
      this._text = String(value);
    },
    append(...nodes) {
      this.children.push(...nodes);
    },
    replaceChildren(...nodes) {
      this.children = [...nodes];
    },
  };
}

function view() {
  const document = {
    innerHtmlUsed: false,
    createElement: (tag) => element(document, tag),
  };
  const root = element(document, "section");
  return { document, root };
}

test("evaluated feedback is text and continue is not completion", () => {
  const { document, root } = view();
  const begin = beginDocument({ attemptId: "<attempt>" });
  const body = evaluatedDocument(begin, {
    messages: {
      missing: "<b>missing</b>",
      next: "<i>go on</i>",
    },
  });
  renderEvaluatedFeedback(root, body);
  const text = root.textContent;
  assert.match(text, /Attempt feedback/);
  assert.match(text, /<attempt>/);
  assert.match(text, /Matched: 1/);
  assert.match(text, /Missing: 2/);
  assert.match(text, /Extra: 1/);
  assert.match(text, /missing_note: <b>missing<\/b>/);
  assert.match(text, /Recommendation: continue/);
  assert.match(text, /<i>go on<\/i>/);
  assert.match(text, /No immediate repetition is required under this attempt policy/);
  assert.match(text, /<script>alert\(1\)<\/script>/);
  assert.match(text, /Unmatched note-off 70/);
  assert.match(text, /UNVERIFIED_PHYSICAL_MIDI_INPUT/);
  assert.match(text, /UNVERIFIED_AUDIO_OUTPUT/);
  assert.equal(text.includes("mastered"), false);
  assert.equal(text.toLowerCase().includes("lesson complete"), false);
  assert.equal(document.innerHtmlUsed, false);

  const repeat = evaluatedDocument(begin, {
    action: { action_type: "repeat", message_key: "next" },
  });
  renderEvaluatedFeedback(root, repeat);
  assert.equal(
    root.textContent.includes("No immediate repetition is required"),
    false,
  );
});

test("interrupted feedback makes no evaluation claim", () => {
  const { document, root } = view();
  const evidence = element(document, "div");
  const body = interruptedDocument(beginDocument({ attemptId: "<id>" }));
  renderInterruptedFeedback(root, body);
  renderCapturedEvidence(evidence, body);
  assert.match(root.textContent, /Attempt interrupted/);
  assert.match(root.textContent, /<id>/);
  assert.match(root.textContent, /No evaluation was produced/);
  assert.equal(root.textContent.includes("Matched"), false);
  assert.equal(root.textContent.includes("Recommendation"), false);
  assert.match(evidence.textContent, /capture stopped/);
  assert.match(evidence.textContent, /Unmatched note-off 64/);
  assert.equal(evidence.textContent.includes("No evaluation was produced"), false);
  assert.equal(document.innerHtmlUsed, false);
  clearAttemptFeedback(root);
  assert.equal(root.textContent, "");
});

test("guidance is presented on the score channel only", () => {
  const calls = [];
  const coordinator = {
    activeEventIds: ["ev-1"],
    applyGuidance(projection) {
      calls.push(projection);
      return { tab: ["ev-1"] };
    },
  };
  const guidance = evaluatedDocument(beginDocument()).guidance;
  assert.deepEqual(presentGuidance(coordinator, guidance), { tab: ["ev-1"] });
  assert.equal(calls.length, 1);
  assert.deepEqual(coordinator.activeEventIds, ["ev-1"]);
  assert.equal(presentGuidance(null, guidance), null);
  assert.equal(presentGuidance({}, guidance), null);
});
