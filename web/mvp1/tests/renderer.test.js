import assert from "node:assert/strict";
import test from "node:test";

import {
  observedEvidencePresentation,
  oneStringViewProjection,
  zonePresentationClasses,
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
