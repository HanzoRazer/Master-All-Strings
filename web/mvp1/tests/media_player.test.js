import assert from "node:assert/strict";
import test from "node:test";
import { MediaPlayerController } from "../media-player.js";

function fakeRoot() {
  const store = new Map();
  const root = {
    hidden: true,
    querySelector(sel) {
      if (!store.has(sel)) {
        const el = {
          textContent: "",
          hidden: false,
          value: "1",
          replaceChildren(...nodes) {
            this.children = nodes;
          },
          addEventListener() {},
          pause() {
            this.paused = true;
          },
          play() {
            this.paused = false;
            return Promise.resolve();
          },
          load() {},
          removeAttribute() {},
          setAttribute() {},
          children: [],
        };
        store.set(sel, el);
      }
      return store.get(sel);
    },
  };
  return { root, store };
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
