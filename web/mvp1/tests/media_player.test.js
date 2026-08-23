import assert from "node:assert/strict";
import test from "node:test";
import { MediaPlayerController } from "../media-player.js";
import { stubRoot } from "./dom_stub.js";

// The local stub was replaced by the shared one in ./dom_stub.js, which models
// dataset/disabled/classList the way a real element does.
function fakeRoot() {
  return stubRoot();
}

test("clear resets media state", () => {
  const { root, store } = fakeRoot();
  const player = new MediaPlayerController({ root, onStatus: () => {} });
  player.items = [{ available: true }];
  player.loop = { enabled: true, start: 1, end: 2 };
  player.clear();
  assert.equal(player.items.length, 0);
  assert.equal(player.loop.enabled, false);
  assert.equal(store.get("[data-media-status]").textContent, "No teaching media");
  assert.equal(root.hidden, true);
});
