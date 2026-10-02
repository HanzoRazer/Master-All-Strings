/** Shared documents for Stage 6 browser tests. Not a product module. */

const ART = `sha256:${"ab".repeat(32)}`;
const BEH = `sha256:${"cd".repeat(32)}`;
const PLAYBACK_DIGEST = `sha256:${"ef".repeat(32)}`;

export function previewBody(id = "delivery-001") {
  return {
    schema_id: "master_all_strings.lesson_delivery_preview",
    schema_version: "1.0.0",
    preview_status: "READY",
    delivery_id: id,
    assignment_id: "asg-1",
    content_id: "content-1",
    assignment_artifact_digest: ART,
    assignment_behavior_digest: BEH,
    title: "Blues Turnaround",
    canonical_event_count: 2,
    canonical_event_ids: ["ev-1", "ev-2"],
    playback_policy: { tempo_bpm: null },
    spatial_policy: { instrument_profile_id: "guitar-standard-6", fingering_policy_id: "default" },
    meter_change_count: 0,
    instruction_objective: "Play it cleanly",
    teacher_note: null,
  };
}

export function choiceBody(id = "delivery-001") {
  return {
    schema_id: "master_all_strings.local_practice_choice",
    schema_version: "1.0.0",
    choice_status: "CHOSEN_FOR_PRACTICE",
    delivery_id: id,
    assignment_id: "asg-1",
    content_id: "content-1",
    assignment_artifact_digest: ART,
    assignment_behavior_digest: BEH,
  };
}

export function practiceNote(id, onset) {
  return {
    event_id: id,
    status: "selected",
    onset_seconds: onset,
    release_seconds: onset + 0.5,
    string_id: "string-1",
    pitch_label: "E",
    fret_number: 1,
    normalized_position: 0.2,
    is_open_string: false,
    selection_origin: "automatic",
    unresolved_reason: null,
  };
}

export function preparationBody(id = "delivery-001") {
  const revisionId = "rev-received";
  return {
    schema_id: "master_all_strings.local_practice_preparation",
    schema_version: "1.0.0",
    preparation_status: "PREPARED",
    delivery_id: id,
    assignment_id: "asg-1",
    content_id: "content-1",
    assignment_artifact_digest: ART,
    assignment_behavior_digest: BEH,
    projection: {
      status: "ready",
      demo_id: null,
      summary_title: "Blues Turnaround",
      instrument_id: "guitar-standard-6",
      behavior_digest: BEH,
      warnings: ["Watch the third"],
      unsupported_features: ["bend"],
      teaching_aids: { one_string: [] },
      projection: {
        schema_version: "1.0.0",
        projection_version: "1.0.0",
        assignment_id: "asg-1",
        content_id: "content-1",
        instrument: {
          instrument_id: "guitar-standard-6",
          display_name: "Standard Guitar",
          lanes: [
            { string_id: "string-1", display_label: "E", display_order: 0 },
          ],
        },
        timeline: { play_line_fraction: 0.22 },
        notes: [practiceNote("ev-1", 0), practiceNote("ev-2", 0.5)],
      },
      timeline_anchors_schema_version: "1.0.0",
      timeline_anchors: [
        { tick: 0, seconds: 0 },
        { tick: 480, seconds: 1 },
      ],
    },
    playback: {
      schema_version: "1.0.0",
      assignment_id: "asg-1",
      content_id: "content-1",
      canonical_revision_id: revisionId,
      timeline: { tempo_changes: [{ tick: 0, microseconds_per_quarter: 500000 }] },
      events: [
        { event_id: "ev-1", midi_note: 64, velocity: 80, onset_seconds: 0, release_seconds: 0.5 },
        { event_id: "ev-2", midi_note: 67, velocity: 80, onset_seconds: 0.5, release_seconds: 1 },
      ],
      total_seconds: 2,
      warnings: [],
      unsupported_features: [],
      playback_digest: PLAYBACK_DIGEST,
    },
    practice: {
      policy: {
        schema_version: "1.0.0",
        assignment_id: "asg-1",
        content_id: "content-1",
        count_in_bars: 99,
        loop: { enabled: true, start_tick: 0, end_tick: 480, target_repetitions: 2 },
      },
      runtime: { loop_start_seconds: 0, loop_end_seconds: 1 },
    },
    score: {
      canonical_revision: {
        schema_version: "1.0.0",
        revision_id: revisionId,
        events: [
          { event_id: "ev-1" },
          { event_id: "ev-2" },
        ],
      },
      tab: {
        schema_version: "1.0.0",
        projection_kind: "tab",
        canonical_revision_id: revisionId,
        payload: {
          schema_version: "1.0.0",
          canonical_revision_id: revisionId,
          events: [
            { canonical_event_id: "ev-2", start_tick: 480 },
            { canonical_event_id: "ev-1", start_tick: 0 },
          ],
        },
      },
      notation: {
        schema_version: "1.0.0",
        projection_kind: "notation",
        canonical_revision_id: revisionId,
        payload: {
          schema_version: "1.0.0",
          canonical_revision_id: revisionId,
          measures: [
            {
              events: [
                { event_kind: "note", canonical_event_id: "ev-1" },
                { event_kind: "rest", canonical_event_id: null },
                { event_kind: "note", canonical_event_id: "ev-2" },
              ],
            },
          ],
        },
      },
    },
  };
}

