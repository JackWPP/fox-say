export type CourseStatus = "empty" | "processing" | "ready" | "failed";
export type MaterialKind = "pdf" | "ppt" | "image" | "text_note";
export type Importance = "high" | "medium" | "low";
export type ConfidenceStatus = "grounded" | "ambiguous" | "out_of_scope";

export interface Course {
  id: string;
  title: string;
  teacher?: string;
  exam_date?: string;
  status: CourseStatus;
  summary?: string;
  material_count?: number;
  icon?: string;
}

export interface Material {
  id: string;
  course_id: string;
  filename: string;
  kind: MaterialKind;
  status: CourseStatus;
  degraded?: boolean;
  revision: number;
  content_hash: string;
}

export interface CourseSkeletonChapter {
  id: string;
  title: string;
  key_concepts: string[];
  importance: Importance;
  exam_weight: number;
}

export interface CourseSkeleton {
  course_id: string;
  chapters: CourseSkeletonChapter[];
  core_concepts: string[];
  difficulty_areas: string[];
  prerequisite_chain: Array<[string, string]>;
}

export interface Citation {
  file_name: string;
  locator: string;
}

export interface CragAnswer {
  course_id: string;
  answer: string;
  citations: Citation[];
  confidence_status: ConfidenceStatus;
  relevance_score: number;
  refusal_reason?: string;
}

export interface ReviewPlanDay {
  day_index: number;
  focus: string;
  suggested_minutes: number;
  priority: Importance;
}

export interface ReviewPlan {
  course_id: string;
  remaining_days: number;
  daily_plan: ReviewPlanDay[];
  likely_exam_points: string[];
  weak_areas: string[];
}

export interface BtwInterjection {
  course_id: string;
  question: string;
  answer: CragAnswer;
  returns_to_review_step_id: string;
}

// Agent streaming types
export interface ToolCallState {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  status: "running" | "done";
}

export interface TermHit {
  name: string;
  definition: string;
  score: number;
}

export interface StreamEvent {
  type: "tool_call" | "token" | "done" | "error";
  tool?: string;
  args?: Record<string, unknown>;
  token?: string;
  answer?: string;
  citations?: Citation[];
  term_hits?: TermHit[];
  in_scope?: boolean;
  guard_warning?: string | null;
  message?: string;
}

// KC (Knowledge Component) type
export interface KCPrerequisite {
  prerequisite_kc_id: string;
  dependency_strength: number;
  source: string;
}

export interface KC {
  id: string;
  course_id: string;
  chapter_id: string;
  name: string;
  bloom_level: string;
  layer: string;
  definition: string;
  formula: string;
  intuition: string;
  conditions: string[];
  key_properties: Array<{ name: string; formula: string }>;
  examples: string[];
  common_mistakes: string[];
  prerequisites: KCPrerequisite[];
  related: string[];
  exam_frequency: string;
  exam_patterns: string[];
}

export interface Note {
  id: string;
  course_id: string;
  title: string;
  content: string;
  source_citations?: Citation[];
  created_at?: string;
  updated_at?: string;
}

export interface ChapterWiki {
  chapter_id: string;
  title: string;
  overview: string;
}

export interface SourcePreview {
  text: string;
  page?: number;
  locator: string;
}

// ---------------------------------------------------------------------------
// Evidence-first knowledge system (V2)
//
// These contracts intentionally sit alongside, rather than reinterpret, the
// legacy CourseStatus / Citation / CragAnswer types above.  A V2 material
// claim is identified by a current source fragment, never by a display
// locator or filename.
// ---------------------------------------------------------------------------

export type KnowledgeLifecycleStatus =
  | "empty"
  | "processing"
  | "partial"
  | "ready"
  | "stale"
  | "failed";

export type SourceEvidenceStatus =
  | "empty"
  | "processing"
  | "partial"
  | "ready"
  | "failed";

export type ProjectionStatus =
  | "not_started"
  | "processing"
  | "ready"
  | "stale"
  | "failed";

export type MaterialEvidenceState =
  | "processing"
  | "ready"
  | "retryable"
  | "failed"
  | "missing_evidence";

export type PersistedKnowledgeJobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "retryable"
  | "failed";

export interface KnowledgeCoverage {
  total_materials: number;
  ready_materials: number;
  processing_materials: number;
  retryable_materials: number;
  failed_materials: number;
  fragment_count: number;
}

export interface MaterialEvidenceStatus {
  material_id: string;
  filename: string;
  material_revision: number;
  status: MaterialEvidenceState;
  fragment_count: number;
  job_status: PersistedKnowledgeJobStatus | null;
  error_code: string | null;
  error_detail: string | null;
}

export type ModelBudgetAvailability = "available" | "exhausted";

/** Current-source V2 audited model budget; legacy model calls are excluded. */
export interface CourseModelBudget {
  course_id: string;
  source_revision: string;
  token_budget: number;
  accounted_tokens: number;
  available_tokens: number;
  status: ModelBudgetAvailability;
  last_error_code: string | null;
  last_error_detail: string | null;
  updated_at: string;
}

/** Durable V2 evidence/projection snapshot, fetched from the API. */
export interface KnowledgeStatus {
  course_id: string;
  status: KnowledgeLifecycleStatus;
  source_status: SourceEvidenceStatus;
  projection_status: ProjectionStatus;
  source_revision: string | null;
  knowledge_revision: string | null;
  compiled_from_source_revision: string | null;
  semantic_status: ProjectionStatus;
  semantic_atom_count: number;
  semantic_error_code: string | null;
  semantic_error_detail: string | null;
  model_budget: CourseModelBudget | null;
  coverage: KnowledgeCoverage;
  materials: MaterialEvidenceStatus[];
}

export type SourceFragmentKind =
  | "paragraph"
  | "formula"
  | "table"
  | "figure_context"
  | "visual_derived";

export type EvidenceSourceType =
  | "material"
  | "source_fragment"
  | "semantic_atom"
  | "visual_atom";

/**
 * The opaque fragment_id is the only client lookup key for V2 source text.
 * locator remains display-only and must never be parsed back into an ID.
 */
export interface EvidenceRef {
  course_id: string;
  material_id: string;
  fragment_id: string;
  material_revision: number;
  locator: string;
  quote: string | null;
  source_type: EvidenceSourceType;
  source_id: string;
}

/** Current-revision response when a V2 citation is opened. */
export interface SourceFragmentPreview {
  course_id: string;
  material_id: string;
  material_revision: number;
  fragment_id: string;
  file_name: string;
  text: string;
  locator: string;
  heading_path: string[];
  page_start: number | null;
  page_end: number | null;
  slide_start: number | null;
  slide_end: number | null;
  char_start: number;
  char_end: number;
  kind: SourceFragmentKind;
}

export type RetrievalChannel = "exact" | "vector" | "heading_neighborhood";
export type RetrievalAvailability = "available" | "unavailable";
export type AnswerSource = "material" | "supplementary";

export interface RetrievalError {
  error_code: string;
  error_detail: string;
  retriable: boolean;
}

export interface RetrievalWarning {
  warning_code: string;
  warning_detail: string;
}

export interface AnswerAssemblyWarning {
  warning_code:
    | "duplicate_citation_selection"
    | "unknown_citation_selection"
    | "fallback_to_allowed_evidence";
  fragment_id: string | null;
  warning_detail: string;
}

/** A server-assembled citation copied from canonical current evidence. */
export interface AnswerCitation {
  evidence: EvidenceRef;
  file_name: string;
  canonical_text: string;
  score: number;
  channels: RetrievalChannel[];
}

interface AnswerEnvelopeBase {
  course_id: string;
  source_revision: string | null;
  knowledge_revision: string | null;
  answer: string;
  relevance: number;
  coverage: number;
  retrieval_warnings: RetrievalWarning[];
  warnings: AnswerAssemblyWarning[];
}

/** Material answers require grounded/ambiguous evidence and a real citation. */
export interface MaterialAnswerEnvelope extends AnswerEnvelopeBase {
  retrieval_availability: "available";
  confidence_status: Exclude<ConfidenceStatus, "out_of_scope">;
  answer_source: "material";
  citations: [AnswerCitation, ...AnswerCitation[]];
  error: null;
}

/**
 * A valid available answer may deliberately be supplementary, but it cannot
 * carry a material citation. This includes the out_of_scope CRAG boundary.
 */
export interface SupplementaryAnswerEnvelope extends AnswerEnvelopeBase {
  retrieval_availability: "available";
  confidence_status: ConfidenceStatus;
  answer_source: "supplementary";
  citations: [];
  error: null;
}

export type AvailableAnswerEnvelope =
  | MaterialAnswerEnvelope
  | SupplementaryAnswerEnvelope;

/**
 * An unavailable retriever is operationally different from a valid
 * out_of_scope result: it has no confidence value and exposes the error.
 */
export interface UnavailableAnswerEnvelope extends AnswerEnvelopeBase {
  retrieval_availability: "unavailable";
  confidence_status: null;
  answer_source: "supplementary";
  citations: [];
  error: RetrievalError;
}

export type AnswerEnvelope = AvailableAnswerEnvelope | UnavailableAnswerEnvelope;

