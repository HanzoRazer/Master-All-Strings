/**
 * Purpose-built DOM stub for browser-module tests.
 *
 * Deliberately not jsdom: these modules touch a handful of element properties,
 * and a stub keeps the repository's zero-dependency posture while making the
 * commands they issue directly observable.
 *
 * It models what a real element always has -- `dataset`, `disabled`, `classList`
 * -- so tests do not pass against a double that is more forgiving than a
 * browser.
 */

export function stubElement(overrides = {}) {
  const classes = new Set();
  return {
    textContent: "",
    hidden: false,
    disabled: false,
    value: "1",
    checked: false,
    paused: true,
    currentTime: 0,
    playbackRate: 1,
    readyState: 4,
    duration: 3,
    dataset: {},
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
    appendChild(node) {
      this.children.push(node);
      return node;
    },
    append(...nodes) {
      this.children.push(...nodes);
    },
    addEventListener(type, handler) {
      (this.listeners[type] ||= []).push(handler);
    },
    /** Invoke registered handlers, as a real event dispatch would. */
    fire(type, event = {}) {
      (this.listeners[type] || []).forEach((handler) => handler(event));
    },
    setAttribute(name, value) {
      this[name] = value;
    },
    removeAttribute(name) {
      delete this[name];
    },
    pause() {
      this.paused = true;
      this.pauseCalls = (this.pauseCalls || 0) + 1;
    },
    play() {
      this.paused = false;
      this.playCalls = (this.playCalls || 0) + 1;
      return Promise.resolve();
    },
    load() {},
    ...overrides,
  };
}

/** A root whose querySelector lazily mints (and remembers) stub elements. */
export function stubRoot() {
  const store = new Map();
  const root = {
    hidden: true,
    querySelector(selector) {
      if (!store.has(selector)) store.set(selector, stubElement());
      return store.get(selector);
    },
  };
  return { root, store, get: (selector) => root.querySelector(selector) };
}

/**
 * Install a minimal global `document` for modules that build elements.
 * Returns a restore function; call it in a finally block.
 */
export function withStubDocument() {
  const previous = globalThis.document;
  globalThis.document = {
    createElement: () => stubElement(),
  };
  return () => {
    if (previous === undefined) delete globalThis.document;
    else globalThis.document = previous;
  };
}
