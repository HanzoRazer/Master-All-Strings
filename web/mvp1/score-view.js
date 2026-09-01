/**
 * Score-view coordination (DO-013C Stage 4).
 *
 * The single browser integration point for score projections. It loads the
 * exported artifacts, refuses to combine ones that disagree about which revision
 * they describe, indexes them by canonical event id, registers exactly one
 * Teaching Timeline follower, and fans that follower's active set out to both
 * renderers.
 *
 * It computes no music. Not pitch, not duration, not fingering, not measures,
 * and above all not which events are active -- that answer arrives from the
 * playhead and is forwarded unchanged.
 *
 * Two indices, deliberately separate:
 *
 *   displayIndex : canonical_event_id -> how each view depicts it
 *   seekIndex    : canonical_event_id -> the tick it begins at
 *
 * They answer different questions, and the seek index must never take part in
 * deciding what is active. Keeping them apart is what stops "where does this
 * event start" from quietly becoming "so it must be playing now".
 */

import {
  applyActiveEventIds as applyTabActive,
  applyGuidedEventIds as applyTabGuidance,
  applySelectedEventId as applyTabSelection,
  mountTabView,
  seekTickForEvent as tabSeekTick,
} from "./tab-view.js";
import {
  applyActiveEventIds as applyNotationActive,
  applyGuidedEventIds as applyNotationGuidance,
  applySelectedEventId as applyNotationSelection,
  mountNotationView,
  seekTickForEvent as notationSeekTick,
} from "./notation-view.js";

/** One follower for both score views; two would be two subscriptions to one clock. */
export const SCORE_VIEW_FOLLOWER_ID = "score-views";

/** Canonical ids cited by event-level guidance items, in projection order. */
export function guidedEventIdsFromProjection(projection) {
  const ids = [];
  const seen = new Set();
  for (const item of projection?.items ?? []) {
    const id = item.canonical_event_id;
    if (typeof id !== "string" || !id || seen.has(id)) continue;
    seen.add(id);
    ids.push(id);
  }
  return ids;
}

export const SCORE_STATUS = Object.freeze({
  idle: "idle",
  ready: "ready",
  unavailable: "unavailable",
});

export const SCORE_ERROR = Object.freeze({
  loadFailed: "score_artifacts_unavailable",
  revisionMismatch: "canonical_revision_mismatch",
  renderFailed: "renderer_failed",
});

/**
 * Check that every artifact describes the same canonical revision.
 *
 * Fails closed. Combining a TAB of one revision with a notation of another would
 * produce a view of music that never existed, and it would look entirely normal
 * -- which is exactly why it is checked before anything is mounted rather than
 * discovered later by a confused reader.
 */
export function assertRevisionAgreement(revision, tabResult, notationResult) {
  const revisionId = revision?.revision_id ?? null;
  if (!revisionId) return { ok: false, reason: "missing_canonical_revision", revisionId: null };

  const cited = [
    ["tab", tabResult?.canonical_revision_id, tabResult?.payload?.canonical_revision_id],
    [
      "notation",
      notationResult?.canonical_revision_id,
      notationResult?.payload?.canonical_revision_id,
    ],
  ];
  for (const [name, envelopeId, payloadId] of cited) {
    if (envelopeId !== revisionId || payloadId !== revisionId) {
      return { ok: false, reason: SCORE_ERROR.revisionMismatch, revisionId, disagreed: name };
    }
  }
  return { ok: true, reason: null, revisionId };
}

/**
 * canonical_event_id -> how each view depicts it.
 *
 * Supports highlighting and cross-view lookup. Carries no timing: an entry here
 * says what an event looks like, never when it happens.
 */
export function buildDisplayIndex(tabPayload, notationPayload) {
  const index = new Map();
  const ensure = (id) => {
    if (!index.has(id)) index.set(id, { canonicalEventId: id, tab: null, notation: null });
    return index.get(id);
  };

  for (const event of tabPayload?.events ?? []) {
    if (!event.canonical_event_id) continue;
    ensure(event.canonical_event_id).tab = {
      status: event.status,
      stringId: event.string_id,
      fret: event.fret,
    };
  }
  for (const measure of notationPayload?.measures ?? []) {
    for (const event of measure.events ?? []) {
      // Rests carry no canonical id. They are genuinely not events, so they are
      // absent from an index keyed by event identity.
      if (!event.canonical_event_id) continue;
      ensure(event.canonical_event_id).notation = {
        displayPitch: event.display_pitch,
        displayDuration: event.display_duration,
        measureIndex: measure.measure_index,
      };
    }
  }
  return index;
}

/**
 * canonical_event_id -> the authored tick it begins at.
 *
 * Navigation only. Nothing in the active-state path reads this map, and the
 * tests assert that separation directly.
 */
export function buildSeekIndex(tabPayload, notationPayload) {
  const index = new Map();
  for (const event of tabPayload?.events ?? []) {
    if (event.canonical_event_id) index.set(event.canonical_event_id, event.start_tick);
  }
  for (const measure of notationPayload?.measures ?? []) {
    for (const event of measure.events ?? []) {
      if (event.canonical_event_id && !index.has(event.canonical_event_id)) {
        index.set(event.canonical_event_id, event.start_tick);
      }
    }
  }
  return index;
}

const DEFAULT_RENDERERS = Object.freeze({
  tab: {
    mount: mountTabView,
    applyActive: applyTabActive,
    applySelection: applyTabSelection,
    applyGuidance: applyTabGuidance,
    seekTick: tabSeekTick,
  },
  notation: {
    mount: mountNotationView,
    applyActive: applyNotationActive,
    applySelection: applyNotationSelection,
    applyGuidance: applyNotationGuidance,
    seekTick: notationSeekTick,
  },
});

/**
 * Loads, validates, mounts, and synchronizes the two score views.
 *
 * Every collaborator is injected so the coordinator can be tested without a DOM,
 * a network, or a running transport -- and so it holds none of them itself.
 */
export class ScoreViewCoordinator {
  constructor(options = {}) {
    const {
      loadJson,
      renderers = DEFAULT_RENDERERS,
      containers = {},
      onSeek = null,
      onStatus = null,
    } = options;

    this._loadJson = loadJson;
    this._renderers = renderers;
    this._containers = containers;
    this._onSeek = onSeek;
    this._onStatus = onStatus;

    this.status = SCORE_STATUS.idle;
    this.reason = null;
    this.demoId = null;
    this.revisionId = null;
    this.tabPayload = null;
    this.notationPayload = null;
    this.tabDigest = null;
    this.notationDigest = null;
    this.displayIndex = new Map();
    this.seekIndex = new Map();
    this.activeEventIds = [];

    // Presentation state, not musical state. `selectedEventId` is where a reader
    // is pointing and `lastSeekTick` is where the transport was last sent from
    // here; neither is part of the score, and neither survives a lesson change.
    this.selectedEventId = null;
    this.lastSeekEventId = null;
    this.lastSeekTick = null;

    // Educational guidance. Independent of activity and selection. The
    // projection is cited, never recomputed here.
    this.guidance = null;
    this.guidedEventIds = [];
    this.guidanceError = null;

    // What each view actually lit, as opposed to what it was asked to light.
    // A view that is unmounted lights nothing, and diagnostics should say so
    // rather than repeating the requested set back as if it had been drawn.
    this.appliedActive = { tab: [], notation: [] };
    this.appliedGuided = { tab: [], notation: [] };

    // Per-view liveness. A view that failed to render is switched off on its
    // own; nothing about it reaches the other one.
    this.views = {
      tab: { mounted: false, root: null, error: null },
      notation: { mounted: false, root: null, error: null },
    };
  }

  _setStatus(status, reason = null) {
    this.status = status;
    this.reason = reason;
    if (typeof this._onStatus === "function") this._onStatus(status, reason);
  }

  _clearScore() {
    this.revisionId = null;
    this.tabPayload = null;
    this.notationPayload = null;
    this.tabDigest = null;
    this.notationDigest = null;
    this.displayIndex = new Map();
    this.seekIndex = new Map();
    this.activeEventIds = [];
    this.selectedEventId = null;
    this.lastSeekEventId = null;
    this.lastSeekTick = null;
    this.guidance = null;
    this.guidedEventIds = [];
    this.guidanceError = null;
    this.appliedActive = { tab: [], notation: [] };
    this.appliedGuided = { tab: [], notation: [] };
    this.views.tab = { mounted: false, root: null, error: null };
    this.views.notation = { mounted: false, root: null, error: null };
  }

  /**
   * Load one lesson's score bundle.
   *
   * Returns a result rather than throwing: a lesson whose score artifacts are
   * missing or inconsistent must still be a usable lesson everywhere else.
   */
  async load(demoId) {
    this.demoId = demoId;
    this._clearScore();

    let revision;
    let tabResult;
    let notationResult;
    let context = null;
    try {
      [revision, tabResult, notationResult] = await Promise.all([
        this._loadJson(`projections/${demoId}/canonical_revision.json`),
        this._loadJson(`projections/${demoId}/tab.json`),
        this._loadJson(`projections/${demoId}/notation.json`),
      ]);
      // Presentation context: instrument lanes for TAB rows and the Core-authored
      // tempo label for notation. Optional, so its absence degrades the labels
      // rather than the score.
      context = await this._loadJson(`projections/${demoId}.json`).catch(() => null);
    } catch (error) {
      this._setStatus(SCORE_STATUS.unavailable, SCORE_ERROR.loadFailed);
      return { ok: false, reason: SCORE_ERROR.loadFailed, error };
    }

    const agreement = assertRevisionAgreement(revision, tabResult, notationResult);
    if (!agreement.ok) {
      this._setStatus(SCORE_STATUS.unavailable, agreement.reason);
      return { ok: false, reason: agreement.reason, disagreed: agreement.disagreed };
    }

    this.revisionId = agreement.revisionId;
    this.tabPayload = tabResult.payload;
    this.notationPayload = notationResult.payload;
    this.tabDigest = tabResult.digest ?? null;
    this.notationDigest = notationResult.digest ?? null;
    this.displayIndex = buildDisplayIndex(this.tabPayload, this.notationPayload);
    this.seekIndex = buildSeekIndex(this.tabPayload, this.notationPayload);

    // Both views hand clicks back here rather than reaching the transport
    // themselves, so one place resolves a canonical id to a position.
    const onSeek = (canonicalEventId) => this.seekTo(canonicalEventId);
    this._mount("tab", {
      lanes: context?.projection?.instrument?.lanes ?? null,
      onSeek,
    });
    this._mount("notation", {
      tempoContext: context?.projection ?? null,
      onSeek,
    });

    const anyMounted = this.views.tab.mounted || this.views.notation.mounted;
    this._setStatus(
      anyMounted ? SCORE_STATUS.ready : SCORE_STATUS.unavailable,
      anyMounted ? null : SCORE_ERROR.renderFailed,
    );
    return { ok: anyMounted, reason: anyMounted ? null : SCORE_ERROR.renderFailed };
  }

  _payloadFor(name) {
    return name === "tab" ? this.tabPayload : this.notationPayload;
  }

  /** Mount one view, containing any failure to that view alone. */
  /**
   * Re-apply the sticky highlight channels to one freshly mounted view.
   *
   * The active set repairs itself: the playhead republishes many times a second,
   * so a view that missed an update gets the next one. Guidance and selection do
   * not -- each is applied once, when an evaluation lands or a reader clicks --
   * so a view mounting afterwards would stay blank while its sibling showed the
   * marks, and nothing would ever correct it.
   *
   * Today `_mount` only runs inside `load()`, which clears both first, so there
   * is no ordering hazard to fix. This exists so that adding any remount path
   * later cannot silently reintroduce one.
   */
  _replayChannels(name) {
    const view = this.views[name];
    if (!view.mounted) return;
    const renderer = this._renderers[name];
    try {
      if (this.guidedEventIds.length && typeof renderer.applyGuidance === "function") {
        renderer.applyGuidance(view.root, [...this.guidedEventIds]);
      }
      if (this.selectedEventId && typeof renderer.applySelection === "function") {
        renderer.applySelection(view.root, this.selectedEventId);
      }
    } catch (error) {
      // A replay failure costs this view only, exactly as a mount failure does.
      view.mounted = false;
      view.error = String(error?.message ?? error);
    }
  }

  _mount(name, options) {
    const view = this.views[name];
    try {
      const root = this._renderers[name].mount(
        this._containers[name],
        this._payloadFor(name),
        options,
      );
      view.root = root;
      view.mounted = true;
      view.error = null;
      this._replayChannels(name);
    } catch (error) {
      // Deliberately swallowed. A renderer that throws must cost its own view
      // and nothing else -- not the other score view, and not the lesson.
      view.root = null;
      view.mounted = false;
      view.error = String(error?.message ?? error);
    }
  }

  // --- the one timeline follower ---------------------------------------------

  /**
   * The follower registered with the Teaching Timeline.
   *
   * One follower drives both views, so they cannot drift apart: whatever the
   * playhead publishes reaches TAB and notation in the same call.
   */
  follower() {
    return {
      id: SCORE_VIEW_FOLLOWER_ID,
      onPlayhead: (playhead) => this.applyPlayhead(playhead),
      onClear: () => this.clear(),
      onError: () => this.applyActiveEventIds([]),
    };
  }

  /**
   * Take the active set from the playhead and forward it, unchanged.
   *
   * The only reading of the playhead is `active_event_ids`. Position and
   * repetition index are deliberately not consulted: deriving activity from
   * either would make this a second playhead.
   */
  applyPlayhead(playhead) {
    return this.applyActiveEventIds(playhead?.active_event_ids ?? []);
  }

  /** Fan one active set out to both views, isolating a failure in either. */
  applyActiveEventIds(activeEventIds) {
    const ids = Array.isArray(activeEventIds) ? [...activeEventIds] : [];
    this.activeEventIds = ids;
    const applied = { tab: [], notation: [] };
    for (const name of ["tab", "notation"]) {
      const view = this.views[name];
      if (!view.mounted) continue;
      try {
        applied[name] = this._renderers[name].applyActive(view.root, ids) ?? [];
      } catch (error) {
        view.mounted = false;
        view.error = String(error?.message ?? error);
      }
    }
    this.appliedActive = applied;
    return applied;
  }

  clear() {
    this._clearScore();
    this._setStatus(SCORE_STATUS.idle, null);
  }

  // --- navigation ------------------------------------------------------------
  //
  // Reads the seek index and nothing else. No arithmetic: the tick was authored
  // by Core and exported, and recomputing one here would be the browser deciding
  // where a note begins.

  /**
   * Seek to where one canonical event begins.
   *
   * Deliberately does not touch `activeEventIds`. Moving the transport will make
   * the playhead publish a new active set in its own time, and anticipating that
   * here would mean guessing at the answer rather than waiting for it.
   *
   * Returns the tick sought to, or null for an event with no authored position.
   */
  seekTo(canonicalEventId) {
    const tick = this.seekTickFor(canonicalEventId);
    if (tick === null) return null;
    this.lastSeekEventId = canonicalEventId;
    this.lastSeekTick = tick;
    if (typeof this._onSeek === "function") this._onSeek(canonicalEventId, tick);
    return tick;
  }

  /**
   * Mark one canonical event as selected across the score views.
   *
   * The fretboard's selection seam. It changes a highlight channel and nothing
   * else -- not the active set, not the score, not the transport. An id one view
   * cannot depict is simply unmarked there while the other still marks it.
   *
   * Passing null clears the selection.
   */
  selectEvent(canonicalEventId) {
    this.selectedEventId = canonicalEventId ?? null;
    const marked = { tab: null, notation: null };
    for (const name of ["tab", "notation"]) {
      const view = this.views[name];
      if (!view.mounted) continue;
      try {
        marked[name] = this._renderers[name].applySelection(view.root, this.selectedEventId);
      } catch (error) {
        view.mounted = false;
        view.error = String(error?.message ?? error);
      }
    }
    return marked;
  }

  /**
   * Apply a teaching-guidance projection as a third highlight channel.
   *
   * Reads canonical event ids from the projection. Does not write the playhead
   * active set, does not change selection, and does not mutate TAB/notation
   * payloads or their digests.
   */
  applyGuidance(projection) {
    this.guidance = projection ?? null;
    this.guidanceError = null;
    const ids = guidedEventIdsFromProjection(projection);
    return this.applyGuidedEventIds(ids);
  }

  /** Fan one guided set out to both views, isolating a failure in either. */
  applyGuidedEventIds(guidedEventIds) {
    const ids = Array.isArray(guidedEventIds) ? [...guidedEventIds] : [];
    this.guidedEventIds = ids;
    const applied = { tab: [], notation: [] };
    for (const name of ["tab", "notation"]) {
      const view = this.views[name];
      if (!view.mounted) continue;
      const apply = this._renderers[name].applyGuidance;
      if (typeof apply !== "function") continue;
      try {
        applied[name] = apply(view.root, ids) ?? [];
      } catch (error) {
        view.mounted = false;
        view.error = String(error?.message ?? error);
        this.guidanceError = view.error;
      }
    }
    this.appliedGuided = applied;
    return applied;
  }

  // --- lookups ---------------------------------------------------------------

  /** How each view depicts one canonical event. Carries no timing. */
  displayFor(canonicalEventId) {
    return this.displayIndex.get(canonicalEventId) ?? null;
  }

  /** The authored tick one canonical event begins at. Navigation only. */
  seekTickFor(canonicalEventId) {
    return this.seekIndex.has(canonicalEventId)
      ? this.seekIndex.get(canonicalEventId)
      : null;
  }

  /** Canonical ids both views can depict; the cross-view join set. */
  sharedEventIds() {
    return [...this.displayIndex.values()]
      .filter((entry) => entry.tab && entry.notation)
      .map((entry) => entry.canonicalEventId);
  }

  /** Observational only; reports state and changes none of it. */
  diagnostics() {
    return {
      status: this.status,
      reason: this.reason,
      demoId: this.demoId,
      canonicalRevisionId: this.revisionId,
      tabLoaded: this.views.tab.mounted,
      notationLoaded: this.views.notation.mounted,
      tabError: this.views.tab.error,
      notationError: this.views.notation.error,
      tabDigest: this.tabDigest,
      notationDigest: this.notationDigest,
      activeEventIds: [...this.activeEventIds],
      tabActiveEventIds: [...this.appliedActive.tab],
      notationActiveEventIds: [...this.appliedActive.notation],
      selectedEventId: this.selectedEventId,
      lastSeekEventId: this.lastSeekEventId,
      lastSeekTick: this.lastSeekTick,
      indexedEventCount: this.displayIndex.size,
      seekTargetCount: this.seekIndex.size,
      guidanceStatus: this.guidance ? "ready" : "idle",
      guidanceDigest: this.guidance?.guidance_digest ?? null,
      guidedEventIds: [...this.guidedEventIds],
      tabGuidedEventIds: [...this.appliedGuided.tab],
      notationGuidedEventIds: [...this.appliedGuided.notation],
      guidanceAction: this.guidance?.next_action?.action_type ?? null,
      guidanceRange:
        this.guidance?.next_action?.focus_start_tick != null &&
        this.guidance?.next_action?.focus_end_tick != null
          ? {
              startTick: this.guidance.next_action.focus_start_tick,
              endTick: this.guidance.next_action.focus_end_tick,
            }
          : null,
      guidanceError: this.guidanceError,
    };
  }
}
