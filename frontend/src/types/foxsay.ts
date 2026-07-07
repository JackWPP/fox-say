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

export interface StreamEvent {
  type: "tool_call" | "token" | "done" | "error";
  tool?: string;
  args?: Record<string, unknown>;
  token?: string;
  answer?: string;
  citations?: Citation[];
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

