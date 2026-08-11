import assert from "node:assert/strict";
import test from "node:test";

import { zonePresentationClasses } from "../renderer.js";

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
    zonePresentationClasses({ zone_id: "ZONE_2", semantic_roles: ["FUTURE_ROLE"] }),
    ["zone-2"],
  );
});
