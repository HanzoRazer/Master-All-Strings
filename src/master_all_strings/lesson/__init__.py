"""LessonAssignmentV1 — Educational Engine portable lesson-entry contracts."""

from .enums import (
    AssessmentMode,
    LessonContentFormat,
    LessonSourceType,
    OpenStringPreference,
    TeacherOverrideStatus,
)
from .errors import (
    LessonAssignmentError,
    LessonSchemaError,
    LessonValidationError,
    TeacherOverrideError,
)
from .importers import MidiLessonImporter, MidiLessonImportResultV1, build_assignment_from_midi
from .models import (
    LESSON_ASSIGNMENT_SCHEMA_ID,
    LESSON_ASSIGNMENT_SCHEMA_VERSION,
    LessonAssessmentV1,
    LessonAssignmentV1,
    LessonIdentityV1,
    LessonInstructionV1,
    LessonMusicalContentV1,
    LessonPlaybackPolicyV1,
    LessonProvenanceV1,
    LessonRoutingV1,
    LessonSpatialGuidanceV1,
    SerializedCanonicalEventV1,
    TeacherOverrideV1,
)
from .pipeline import MvpLessonPipelineResultV1, run_mvp_lesson_pipeline
from .resolver import LessonAssignmentResolver, ResolvedLessonV1, resolve_lesson_assignment
from .serialization import (
    compute_assignment_artifact_digest,
    compute_lesson_behavior_digest,
    deserialize_lesson_assignment,
    serialize_lesson_assignment,
)
from .validation import validate_assignment

__all__ = [
    "AssessmentMode",
    "LESSON_ASSIGNMENT_SCHEMA_ID",
    "LESSON_ASSIGNMENT_SCHEMA_VERSION",
    "LessonAssessmentV1",
    "LessonAssignmentError",
    "LessonAssignmentResolver",
    "LessonAssignmentV1",
    "LessonContentFormat",
    "LessonIdentityV1",
    "LessonInstructionV1",
    "LessonMusicalContentV1",
    "LessonPlaybackPolicyV1",
    "LessonProvenanceV1",
    "LessonRoutingV1",
    "LessonSchemaError",
    "LessonSourceType",
    "LessonSpatialGuidanceV1",
    "LessonValidationError",
    "MidiLessonImportResultV1",
    "MidiLessonImporter",
    "MvpLessonPipelineResultV1",
    "OpenStringPreference",
    "ResolvedLessonV1",
    "SerializedCanonicalEventV1",
    "TeacherOverrideError",
    "TeacherOverrideStatus",
    "TeacherOverrideV1",
    "build_assignment_from_midi",
    "compute_assignment_artifact_digest",
    "compute_lesson_behavior_digest",
    "deserialize_lesson_assignment",
    "resolve_lesson_assignment",
    "run_mvp_lesson_pipeline",
    "serialize_lesson_assignment",
    "validate_assignment",
]
