/** Closed-document checks for the local lesson inbox and practice page.

Preview and choice rules are the ones the inbox already applied. Preparation
checks only the fields a practice runtime has to consume. Policy tempo
contents stay opaque, and no digest is recomputed here: pin equality is a
consistency check against the fresh preview and the stored choice.
*/

import { TeachingTimeline } from "./teaching-timeline.js";

const DIGEST = /^sha256:[0-9a-f]{64}$/;

export const PREVIEW_FIELDS = [
  "schema_id", "schema_version", "preview_status", "delivery_id", "assignment_id", "content_id",
  "assignment_artifact_digest", "assignment_behavior_digest", "title", "canonical_event_count",
  "canonical_event_ids", "playback_policy", "spatial_policy", "meter_change_count",
  "instruction_objective", "teacher_note",
];

export const CHOICE_FIELDS = [
  "schema_id", "schema_version", "choice_status", "delivery_id", "assignment_id", "content_id",
  "assignment_artifact_digest", "assignment_behavior_digest",
];

export const PREPARATION_FIELDS = [
  "schema_id", "schema_version", "preparation_status", "delivery_id", "assignment_id", "content_id",
  "assignment_artifact_digest", "assignment_behavior_digest", "projection", "playback", "practice",
  "score",
];

const PROJECTION_FIELDS = [
  "status", "demo_id", "summary_title", "instrument_id", "behavior_digest", "warnings",
  "unsupported_features", "teaching_aids", "projection", "timeline_anchors_schema_version",
  "timeline_anchors",
];

const PLAYBACK_REQUIRED = [
  "schema_version", "assignment_id", "content_id", "timeline", "events", "total_seconds",
  "warnings", "unsupported_features", "playback_digest",
];

const PLAYBACK_OPTIONAL = ["canonical_revision_id"];

const IDENTITY_FIELDS = [
  "delivery_id",
  "assignment_id",
  "content_id",
  "assignment_artifact_digest",
  "assignment_behavior_digest",
];

export const INVALID_RESPONSE = "The response is invalid. Playback stays off.";

export const RECEIVED_SCORE_KEY = "received";

/**
 * @param {string} deliveryId
 */
export function practicePageHref(deliveryId) {
  const params = new URLSearchParams();
  params.set("delivery_id", deliveryId);
  return `lesson-practice.html?${params.toString()}`;
}

/**
 * Exactly one nonblank `delivery_id`. A fragment is not part of `search`.
 *
 * @param {string} search
 * @returns {{ ok: true, deliveryId: string } | { ok: false, reason: string }}
 */
export function parsePracticeSearch(search) {
  const query = typeof search === "string" ? search : "";
  const bare = query.startsWith("?") ? query.slice(1) : query;
  if (bare.length === 0) return { ok: false, reason: "missing" };
  if (bare.split("&").length !== 1) return { ok: false, reason: "repeated-or-extra" };
  const params = new URLSearchParams(query.startsWith("?") ? query : `?${query}`);
  const keys = [...params.keys()];
  if (keys.length !== 1 || keys[0] !== "delivery_id") return { ok: false, reason: "parameter" };
  const values = params.getAll("delivery_id");
  if (values.length !== 1) return { ok: false, reason: "repeated" };
  const deliveryId = values[0];
  if (!nonblank(deliveryId)) return { ok: false, reason: "blank" };
  return { ok: true, deliveryId };
}

/**
 * @param {{ status?: number, error?: string|null }} failure
 */
export function failureMessage(failure) {
  const status =
    failure && Number.isInteger(failure.status) && failure.status > 0
      ? String(failure.status)
      : "unavailable";
  const code =
    failure && typeof failure.error === "string" && failure.error.length > 0
      ? failure.error
      : "unavailable";
  let text = `Request failed (${status}, ${code}).`;
  if (failure && failure.error === "stale_preview") {
    text += " Refresh the selected delivery before choosing again.";
  }
  return text;
}

/**
 * @param {{ status?: number, error?: string|null }} failure
 * @param {boolean} [invalid]
 */
export function practiceFailureMessage(failure, invalid = false) {
  if (invalid) return INVALID_RESPONSE;
  return failureMessage(failure);
}

/**
 * @param {{ ok?: boolean, status?: number, body?: { deliveries?: unknown } }} result
 */
export function isDeliveryList(result) {
  return Boolean(result?.ok && result.status === 200 && Array.isArray(result.body?.deliveries));
}

/**
 * @param {{ ok?: boolean, status?: number, body?: object }} result
 * @param {string} deliveryId
 */
export function isReadyPreview(result, deliveryId) {
  if (!result?.ok || result.status !== 200) return false;
  const body = result.body;
  if (!hasFields(body, PREVIEW_FIELDS)) return false;
  if (body.schema_id !== "master_all_strings.lesson_delivery_preview") return false;
  if (body.schema_version !== "1.0.0") return false;
  if (body.preview_status !== "READY") return false;
  if (body.delivery_id !== deliveryId) return false;
  if (!nonblank(body.assignment_id) || !nonblank(body.content_id)) return false;
  if (!isDigest(body.assignment_artifact_digest) || !isDigest(body.assignment_behavior_digest)) {
    return false;
  }
  if (!nonblank(body.title)) return false;
  if (!Number.isInteger(body.canonical_event_count) || body.canonical_event_count < 1) {
    return false;
  }
  if (!Array.isArray(body.canonical_event_ids) || body.canonical_event_ids.length === 0) {
    return false;
  }
  if (body.canonical_event_count !== body.canonical_event_ids.length) return false;
  if (new Set(body.canonical_event_ids).size !== body.canonical_event_count) return false;
  if (!body.canonical_event_ids.every(nonblank)) return false;
  if (!isRecord(body.playback_policy) || !isRecord(body.spatial_policy)) return false;
  if (!Number.isInteger(body.meter_change_count) || body.meter_change_count < 0) return false;
  if (body.instruction_objective !== null && !nonblank(body.instruction_objective)) return false;
  if (body.teacher_note !== null && !nonblank(body.teacher_note)) return false;
  return true;
}

/**
 * @param {{ status?: number, error?: string|null }} result
 */
export function isAvailable(result) {
  return result?.status === 404 && result?.error === "unknown_practice_choice";
}

/**
 * @param {{ ok?: boolean, status?: number, body?: object }} result
 * @param {object|null} preview
 * @param {boolean} [allowCreated]
 */
export function isChosen(result, preview, allowCreated = false) {
  if (!preview || !result?.ok) return false;
  if (result.status !== 200 && !(allowCreated && result.status === 201)) return false;
  const body = result.body;
  if (!hasFields(body, CHOICE_FIELDS)) return false;
  if (body.schema_id !== "master_all_strings.local_practice_choice") return false;
  if (body.schema_version !== "1.0.0") return false;
  if (body.choice_status !== "CHOSEN_FOR_PRACTICE") return false;
  for (const field of IDENTITY_FIELDS) {
    if (body[field] !== preview[field]) return false;
  }
  return true;
}

/**
 * @param {{ ok?: boolean, status?: number, body?: object }} result
 * @param {object} preview
 * @param {object} choice
 * @returns {{ ok: true, body: object } | { ok: false, invalid: boolean }}
 */
export function acceptPreparation(result, preview, choice) {
  if (!result?.ok || result.status !== 200 || !result.body) return { ok: false, invalid: false };
  if (!preparationMatches(result.body, preview, choice)) return { ok: false, invalid: true };
  return { ok: true, body: result.body };
}

/**
 * @param {object} body
 * @param {object} preview
 * @param {object} choice
 */
export function preparationMatches(body, preview, choice) {
  if (!hasFields(body, PREPARATION_FIELDS)) return false;
  if (body.schema_id !== "master_all_strings.local_practice_preparation") return false;
  if (body.schema_version !== "1.0.0") return false;
  if (body.preparation_status !== "PREPARED") return false;
  if (!preview || !choice) return false;
  for (const field of IDENTITY_FIELDS) {
    if (body[field] !== preview[field] || body[field] !== choice[field]) return false;
  }
  if (!projectionAccepted(body.projection, preview)) return false;
  if (!playbackAccepted(body.playback, preview)) return false;
  if (!practiceAccepted(body.practice, preview, body.playback.total_seconds)) return false;
  if (!scoreAccepted(body.score, preview)) return false;
  return true;
}

function projectionAccepted(wrapper, preview) {
  if (!hasFields(wrapper, PROJECTION_FIELDS)) return false;
  if (wrapper.status !== "ready" || wrapper.demo_id !== null) return false;
  if (!nonblank(wrapper.summary_title)) return false;
  if (wrapper.behavior_digest !== preview.assignment_behavior_digest) return false;
  if (!Array.isArray(wrapper.warnings) || !wrapper.warnings.every((item) => typeof item === "string")) {
    return false;
  }
  if (
    !Array.isArray(wrapper.unsupported_features) ||
    !wrapper.unsupported_features.every((item) => typeof item === "string")
  ) {
    return false;
  }
  if (!isRecord(wrapper.teaching_aids)) return false;
  if (wrapper.timeline_anchors_schema_version !== "1.0.0") return false;
  if (!anchorsAccepted(wrapper.timeline_anchors)) return false;
  const declared = preview.spatial_policy?.instrument_profile_id;
  if (!nonblank(declared) || wrapper.instrument_id !== declared) return false;
  const inner = wrapper.projection;
  if (!isRecord(inner)) return false;
  if (inner.schema_version !== "1.0.0" || inner.projection_version !== "1.0.0") return false;
  if (inner.assignment_id !== preview.assignment_id || inner.content_id !== preview.content_id) {
    return false;
  }
  if (!isRecord(inner.instrument) || inner.instrument.instrument_id !== declared) return false;
  if (!Array.isArray(inner.instrument.lanes) || inner.instrument.lanes.length === 0) return false;
  if (!inner.instrument.lanes.every((lane) => isRecord(lane) && nonblank(lane.string_id))) return false;
  if (!isRecord(inner.timeline)) return false;
  const noteIds = eventIds(inner.notes, "event_id");
  if (!sameIds(noteIds, preview.canonical_event_ids)) return false;
  return inner.notes.every((note) => {
    if (note.status !== "selected") return true;
    return Number.isFinite(note.onset_seconds) &&
      Number.isFinite(note.release_seconds) &&
      note.release_seconds > note.onset_seconds;
  });
}

function playbackAccepted(playback, preview) {
  if (!allowsFields(playback, PLAYBACK_REQUIRED, PLAYBACK_OPTIONAL)) return false;
  if (playback.schema_version !== "1.0.0") return false;
  if (playback.assignment_id !== preview.assignment_id || playback.content_id !== preview.content_id) {
    return false;
  }
  if (!isRecord(playback.timeline)) return false;
  if (!Number.isFinite(playback.total_seconds) || playback.total_seconds <= 0) return false;
  if (!isDigest(playback.playback_digest)) return false;
  if (!Array.isArray(playback.warnings) || !Array.isArray(playback.unsupported_features)) return false;
  const ids = eventIds(playback.events, "event_id");
  if (!sameIds(ids, preview.canonical_event_ids)) return false;
  let previous = [-1, -1, ""];
  for (const event of playback.events) {
    if (
      !Number.isFinite(event.onset_seconds) ||
      !Number.isFinite(event.release_seconds) ||
      event.release_seconds <= event.onset_seconds
    ) {
      return false;
    }
    const current = [event.onset_seconds, event.release_seconds, event.event_id];
    if (compareOrder(current, previous) < 0) return false;
    previous = current;
  }
  return true;
}

function practiceAccepted(practice, preview, totalSeconds) {
  if (!hasFields(practice, ["policy", "runtime"])) return false;
  if (!hasFields(practice.runtime, ["loop_start_seconds", "loop_end_seconds"])) return false;
  const policy = practice.policy;
  if (!isRecord(policy) || policy.schema_version !== "1.0.0") return false;
  if (policy.assignment_id !== preview.assignment_id || policy.content_id !== preview.content_id) {
    return false;
  }
  const loop = policy.loop;
  if (!isRecord(loop) || typeof loop.enabled !== "boolean") return false;
  const repetitions = loop.target_repetitions;
  if (!(repetitions === null || (Number.isInteger(repetitions) && repetitions >= 1))) return false;
  const start = practice.runtime.loop_start_seconds;
  const end = practice.runtime.loop_end_seconds;
  return Number.isFinite(start) &&
    Number.isFinite(end) &&
    start >= 0 &&
    end > start &&
    end <= totalSeconds;
}

function scoreAccepted(score, preview) {
  if (!hasFields(score, ["canonical_revision", "tab", "notation"])) return false;
  const revision = score.canonical_revision;
  if (!isRecord(revision) || revision.schema_version !== "1.0.0" || !nonblank(revision.revision_id)) {
    return false;
  }
  const revisionIds = eventIds(revision.events, "event_id");
  if (!sameIds(revisionIds, preview.canonical_event_ids)) return false;
  if (!artifactAccepted(score.tab, "tab", revision.revision_id)) return false;
  if (!artifactAccepted(score.notation, "notation", revision.revision_id)) return false;
  const tabIds = eventIds(score.tab.payload.events, "canonical_event_id");
  if (!sameIds(tabIds, preview.canonical_event_ids)) return false;
  const notationIds = notationNoteIds(score.notation);
  return sameIds(notationIds, preview.canonical_event_ids);
}

function artifactAccepted(artifact, kind, revisionId) {
  if (!isRecord(artifact) || !isRecord(artifact.payload)) return false;
  if (artifact.schema_version !== "1.0.0" || artifact.payload.schema_version !== "1.0.0") return false;
  if (artifact.projection_kind !== kind) return false;
  return artifact.canonical_revision_id === revisionId &&
    artifact.payload.canonical_revision_id === revisionId;
}

function notationNoteIds(notation) {
  const measures = notation.payload.measures;
  if (!Array.isArray(measures)) return null;
  const ids = [];
  for (const measure of measures) {
    if (!isRecord(measure) || !Array.isArray(measure.events)) return null;
    for (const event of measure.events) {
      if (!isRecord(event)) return null;
      const cited = event.canonical_event_id;
      if (cited == null) {
        if (event.event_kind !== "rest") return null;
        continue;
      }
      if (!nonblank(cited)) return null;
      ids.push(cited);
    }
  }
  if (new Set(ids).size !== ids.length) return null;
  return ids;
}

function eventIds(items, key) {
  if (!Array.isArray(items) || items.length === 0) return null;
  const ids = [];
  for (const item of items) {
    if (!isRecord(item) || !nonblank(item[key])) return null;
    ids.push(item[key]);
  }
  if (new Set(ids).size !== ids.length) return null;
  return ids;
}

function sameIds(actual, expected) {
  if (!actual || !Array.isArray(expected)) return false;
  if (actual.length !== expected.length) return false;
  const wanted = new Set(expected);
  return actual.every((id) => wanted.has(id));
}

function anchorsAccepted(anchors) {
  const transport = {
    snapshot() {
      return {
        playing: false,
        positionSeconds: 0,
        playbackRate: 1,
        durationSeconds: 0,
        loop: null,
        repetitionCount: 0,
      };
    },
    subscribe() {
      return () => {};
    },
  };
  const timeline = new TeachingTimeline({ transport });
  try {
    timeline.setLesson({ lessonId: RECEIVED_SCORE_KEY, anchors });
    return true;
  } catch {
    return false;
  } finally {
    timeline.dispose();
  }
}

function compareOrder(left, right) {
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] < right[index]) return -1;
    if (left[index] > right[index]) return 1;
  }
  return 0;
}

/**
 * @param {object} body
 * @param {string[]} fields
 */
export function hasFields(body, fields) {
  return Boolean(
    body && typeof body === "object" && !Array.isArray(body) &&
    Object.keys(body).length === fields.length &&
    fields.every((field) => Object.hasOwn(body, field)),
  );
}

function allowsFields(body, required, optional) {
  if (!isRecord(body)) return false;
  const keys = Object.keys(body);
  if (!required.every((field) => Object.hasOwn(body, field))) return false;
  const allowed = new Set([...required, ...optional]);
  return keys.every((key) => allowed.has(key));
}

function nonblank(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function isDigest(value) {
  return typeof value === "string" && DIGEST.test(value);
}

function isRecord(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
