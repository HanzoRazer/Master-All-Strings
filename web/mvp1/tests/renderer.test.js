import assert from "node:assert/strict";
import test from "node:test";

import {
  observedEvidencePresentation,
  oneStringViewProjection,
  zonePresentationClasses,
  zoneReadoutText,
} from "../renderer.js";

test("Zone renderer consumes semantic IDs without pitch calculations", () => {
  assert.deepEqual(
    zonePresentationClasses({
      zone_id: "ZONE_1",
      semantic_roles: ["ZONE_1", "TRITONE_ANCHOR", "HALF_STEP_CROSSING"],
    }),
    ["zone-1", "tritone-anchor", "half-step-crossing"],
  );
});

test("missing Zone semantics preserves normal presentation", () => {
  assert.deepEqual(zonePresentationClasses(null), []);
});

test("unknown presentation roles are ignored rather than inferred", () => {
  assert.deepEqual(
    zonePresentationClasses({
      zone_id: "ZONE_2",
      semantic_roles: ["FUTURE_ROLE"],
    }),
    ["zone-2"],
  );
});

test("one-string view uses only precomputed positions and exposes impossible events", () => {
  const projection = {
    notes: [
      {
        event_id: "a",
        status: "selected",
        string_id: "normal-a",
        fret_number: 3,
      },
      {
        event_id: "b",
        status: "selected",
        string_id: "normal-b",
        fret_number: 5,
      },
    ],
  };
  const teaching = {
    events: [
      {
        event_id: "a",
        status: "playable",
        requested_string_id: "string-2",
        display_order: 4,
        physical_fret_number: 8,
        relative_semitone_position: 8,
        normalized_position: 0.4,
        is_open_string: false,
      },
      {
        event_id: "b",
        status: "unplayable",
        requested_string_id: "string-2",
        unresolved_reason: "unplayable_on_requested_string",
      },
    ],
  };

  const result = oneStringViewProjection(projection, teaching);

  assert.equal(result.notes[0].string_id, "string-2");
  assert.equal(result.notes[0].fret_number, 8);
  assert.equal(result.notes[1].status, "unplayable");
  assert.equal(result.notes[1].string_id, null);
  assert.equal(
    result.notes[1].unresolved_reason,
    "unplayable_on_requested_string",
  );
  assert.equal(projection.notes[0].string_id, "normal-a");
});

test("observed overlay consumes evidence without assessment labels", () => {
  const marker = observedEvidencePresentation({
    observed_event_id: "obs-1",
    midi_note: 61,
    practice_onset_seconds: 0.5,
  });
  assert.equal(marker.presentationRole, "OBSERVED");
  assert.doesNotMatch(marker.label, /right|wrong|pass|fail/i);
});


// --- Zone readout (DO-012A gap 4) --------------------------------------------
//
// D10: the axis is copied from the Zone artifact. The case that needed a guard
// is a Zone that is present but declares no tritone axis -- the readout must
// then omit the Anchor segment entirely rather than emit a dangling label.

test("a Zone with no declared tritone axis produces no Anchor segment", () => {
  assert.equal(zoneReadoutText([{ zoneId: "ZONE_1", tritoneAxisId: null }]), "Zone: ZONE_1");
});

test("an undefined axis is treated the same as an absent one", () => {
  assert.equal(zoneReadoutText([{ zoneId: "ZONE_1" }]), "Zone: ZONE_1");
});

test("a declared axis is named", () => {
  assert.equal(
    zoneReadoutText([{ zoneId: "ZONE_2", tritoneAxisId: "5-11" }]),
    "Zone: ZONE_2 · Anchor: 5-11",
  );
});

test("simultaneous Zones are listed in projection order, not sorted", () => {
  assert.equal(
    zoneReadoutText([
      { zoneId: "ZONE_2", tritoneAxisId: "5-11" },
      { zoneId: "ZONE_1", tritoneAxisId: "0-6" },
    ]),
    "Zone: ZONE_2, ZONE_1 · Anchor: 5-11, 0-6",
  );
});

test("an axis shared by simultaneous notes is named once", () => {
  assert.equal(
    zoneReadoutText([
      { zoneId: "ZONE_1", tritoneAxisId: "0-6" },
      { zoneId: "ZONE_2", tritoneAxisId: "0-6" },
    ]),
    "Zone: ZONE_1, ZONE_2 · Anchor: 0-6",
  );
});

test("a partially annotated set names only the declared axes", () => {
  assert.equal(
    zoneReadoutText([
      { zoneId: "ZONE_1", tritoneAxisId: null },
      { zoneId: "ZONE_2", tritoneAxisId: "0-6" },
    ]),
    "Zone: ZONE_1, ZONE_2 · Anchor: 0-6",
  );
});

test("no active Zones reads as none", () => {
  assert.equal(zoneReadoutText([]), "Zone: none");
  assert.equal(zoneReadoutText(null), "Zone: none");
});

test("the readout copies artifact values and computes no intervals", () => {
  // A nonsense axis string must survive verbatim: this layer displays the
  // artifact, it does not evaluate or correct it.
  assert.equal(
    zoneReadoutText([{ zoneId: "ZONE_9", tritoneAxisId: "not-an-interval" }]),
    "Zone: ZONE_9 · Anchor: not-an-interval",
  );
});
