/**
 * Boot `app.js` the way a browser does, so a whole-page path can be tested.
 *
 * The other browser-module tests exercise one module against `dom_stub.js`.
 * That is not enough for `loadSession()`: what it does wrong when a guided
 * session cannot be transitioned is visible only once the real wiring is in
 * place -- the controller, the disposition controls, the results panel, and the
 * history region all reading the same state.
 *
 * So this mints elements on demand instead of modelling a document, serves the
 * lesson artifacts from disk, and routes everything else through a table the
 * test controls. What it deliberately does not do is stand in for the server:
 * responses come from the repository's own checked-in fixtures.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const repoFile = (path) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf-8");

function stubCanvasContext() {
  const noop = () => {};
  return {
    canvas: { width: 800, height: 400 },
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 1,
    font: "",
    textAlign: "",
    textBaseline: "",
    globalAlpha: 1,
    save: noop,
    restore: noop,
    clearRect: noop,
    fillRect: noop,
    strokeRect: noop,
    beginPath: noop,
    closePath: noop,
    moveTo: noop,
    lineTo: noop,
    arc: noop,
    fill: noop,
    stroke: noop,
    fillText: noop,
    setLineDash: noop,
    measureText: () => ({ width: 10 }),
    translate: noop,
    scale: noop,
  };
}

export function createElement(tagName = "div") {
  const classes = new Set();
  const selectorChildren = new Map();
  const element = {
    tagName: String(tagName).toUpperCase(),
    textContent: "",
    innerHTML: "",
    value: "",
    checked: false,
    hidden: false,
    disabled: false,
    className: "",
    readyState: 4,
    paused: true,
    currentTime: 0,
    duration: 0,
    playbackRate: 1,
    width: 800,
    height: 400,
    dataset: {},
    style: {},
    children: [],
    listeners: {},
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
      toggle: (name, force) => {
        const on = force === undefined ? !classes.has(name) : force;
        if (on) classes.add(name);
        else classes.delete(name);
        return on;
      },
    },
    replaceChildren(...nodes) {
      this.children = nodes;
    },
    append(...nodes) {
      this.children.push(...nodes);
    },
    appendChild(node) {
      this.children.push(node);
      return node;
    },
    insertBefore(node) {
      this.children.unshift(node);
      return node;
    },
    removeChild(node) {
      this.children = this.children.filter((item) => item !== node);
      return node;
    },
    remove() {},
    setAttribute(name, value) {
      this[name] = value;
    },
    getAttribute(name) {
      return this[name] ?? null;
    },
    removeAttribute(name) {
      delete this[name];
    },
    addEventListener(type, handler) {
      (this.listeners[type] ||= []).push(handler);
    },
    removeEventListener() {},
    /** Dispatch, and hand back the handlers' promises so a test can await. */
    fire(type, event = {}) {
      return Promise.all((this.listeners[type] || []).map((handler) => handler(event)));
    },
    querySelector(selector) {
      if (!selectorChildren.has(selector)) {
        selectorChildren.set(selector, createElement("div"));
      }
      return selectorChildren.get(selector);
    },
    querySelectorAll() {
      return [];
    },
    getContext: () => stubCanvasContext(),
    getBoundingClientRect: () => ({
      width: 800,
      height: 400,
      top: 0,
      left: 0,
      right: 800,
      bottom: 400,
    }),
    scrollTo() {},
    scrollIntoView() {},
    focus() {},
    load() {},
    play() {
      this.paused = false;
      return Promise.resolve();
    },
    pause() {
      this.paused = true;
    },
  };
  return element;
}

function jsonResponse(data, { status = 200 } = {}) {
  const body = JSON.stringify(data);
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: async () => JSON.parse(body),
    text: async () => body,
  };
}

/**
 * A fetch that serves the lesson artifacts from disk and everything else from
 * `routes`, keyed `"<METHOD> <path>"` with `*` as a trailing wildcard.
 *
 * A route may be a value, or a function of the request. Anything unrouted is a
 * 404, so a test never passes because a call quietly succeeded.
 */
export function createFetch(routes = {}) {
  const calls = [];
  const table = new Map(Object.entries(routes));
  const lookup = (method, path) => {
    const exact = table.get(`${method} ${path}`);
    if (exact !== undefined) return exact;
    for (const [key, value] of table) {
      const [routeMethod, routePath] = key.split(" ");
      if (routeMethod !== method || !routePath.endsWith("*")) continue;
      if (path.startsWith(routePath.slice(0, -1))) return value;
    }
    return undefined;
  };
  const fetchImpl = async (url, init = {}) => {
    const method = (init.method || "GET").toUpperCase();
    const path = String(url);
    const body = init.body ? JSON.parse(init.body) : null;
    calls.push({ method, path, body });
    const route = lookup(method, path);
    // Lesson artifacts, score projections and anchors come off disk exactly as
    // served, so the page loads the repository's own lessons. A route wins over
    // disk, which is how a test serves the same lesson at another revision.
    if (route === undefined && !path.startsWith("/")) {
      try {
        return jsonResponse(JSON.parse(repoFile(`../${path.replace(/^\.\//, "")}`)));
      } catch {
        return jsonResponse({ error: `no such artifact ${path}` }, { status: 404 });
      }
    }
    if (route === undefined) {
      return jsonResponse({ error: `unrouted ${method} ${path}` }, { status: 404 });
    }
    const resolved = typeof route === "function" ? await route({ method, path, body }) : route;
    if (resolved && resolved.__status) {
      return jsonResponse(resolved.body, { status: resolved.__status });
    }
    return jsonResponse(resolved);
  };
  return {
    fetch: fetchImpl,
    calls,
    /** Calls narrowed to one method and path prefix. */
    to: (method, prefix) =>
      calls.filter((call) => call.method === method && call.path.startsWith(prefix)),
    route: (key, value) => table.set(key, value),
    unroute: (key) => table.delete(key),
  };
}

export const failWith = (status, error) => ({ __status: status, body: { error } });

/** Install the browser globals `app.js` reads at module scope. */
export function installBrowserGlobals({ search = "", fetchImpl } = {}) {
  const elements = new Map();
  const previous = {
    window: globalThis.window,
    document: globalThis.document,
    location: globalThis.location,
    fetch: globalThis.fetch,
    requestAnimationFrame: globalThis.requestAnimationFrame,
    cancelAnimationFrame: globalThis.cancelAnimationFrame,
  };
  const document = {
    body: createElement("body"),
    documentElement: createElement("html"),
    visibilityState: "visible",
    hidden: false,
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, createElement("div"));
      return elements.get(id);
    },
    createElement: (tag) => createElement(tag),
    createElementNS: (_ns, tag) => createElement(tag),
    querySelector: (selector) => document.getElementById(selector),
    // The page's collections (workflow steps, rate buttons) are not what these
    // tests drive, and an empty list keeps their listeners out of the way.
    querySelectorAll: () => [],
    addEventListener() {},
    removeEventListener() {},
  };
  const window = {
    location: { search, href: `http://localhost/${search}` },
    devicePixelRatio: 1,
    addEventListener() {},
    removeEventListener() {},
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  };
  globalThis.window = window;
  globalThis.document = document;
  // WebMidiInput reads `globalThis.location`, not `window.location`.
  globalThis.location = window.location;
  globalThis.fetch = fetchImpl;
  globalThis.requestAnimationFrame = () => 0;
  globalThis.cancelAnimationFrame = () => {};
  return {
    window,
    document,
    element: (id) => document.getElementById(id),
    restore() {
      for (const [key, value] of Object.entries(previous)) {
        if (value === undefined) delete globalThis[key];
        else globalThis[key] = value;
      }
    },
  };
}

/** Poll until `predicate` holds, so a test can wait on the page's own async. */
export async function waitFor(predicate, { timeoutMs = 4000, label = "condition" } = {}) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const value = predicate();
    if (value) return value;
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${label}`);
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}
