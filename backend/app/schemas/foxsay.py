import uuid
from typing import Literal

from pydantic import BaseModel

NAMESPACE_DMAP = uuid.UUID("12345678-1234-5678-1234-567812345678")  # 稳定 namespace

CourseStatus = Literal["empty", "processing", "ready", "failed"]
MaterialKind = Literal["pdf", "ppt", "image", "text_note"]
Importance = Literal["high", "medium", "low"]
ConfidenceStatus = Literal["grounded", "ambiguous", "out_of_scope"]


class Course(BaseModel):
    id: str
    title: str
    status: CourseStatus
    teacher: str | None = None
    exam_date: str | None = None


class Material(BaseModel):
    id: str
    course_id: str
    filename: str
    kind: MaterialKind
    status: CourseStatus
    degraded: bool = False


class CourseSkeletonChapter(BaseModel):
    id: str
    title: str
    key_concepts: list[str]
    importance: Importance
    exam_weight: float


class CourseSkeleton(BaseModel):
    course_id: str
    chapters: list[CourseSkeletonChapter]
    core_concepts: list[str]
    difficulty_areas: list[str]
    prerequisite_chain: list[list[str]]


class Citation(BaseModel):
    file_name: str
    locator: str


class CragAnswer(BaseModel):
    course_id: str
    answer: str
    citations: list[Citation]
    confidence_status: ConfidenceStatus
    relevance_score: float
    refusal_reason: str | None = None


class ReviewPlanDay(BaseModel):
    day_index: int
    focus: str
    suggested_minutes: int
    priority: Importance


class ReviewPlan(BaseModel):
    course_id: str
    remaining_days: int
    daily_plan: list[ReviewPlanDay]
    likely_exam_points: list[str]
    weak_areas: list[str]


class BtwInterjection(BaseModel):
    course_id: str
    question: str
    answer: CragAnswer
    returns_to_review_step_id: str


class ImportTimetableResponse(BaseModel):
    imported: int
    courses: list[Course]


class CreateCourseRequest(BaseModel):
    title: str
    teacher: str | None = None
    exam_date: str | None = None


# =============================================================================
# Wiki-First Pipeline Schemas (阶段 2 新增)
# =============================================================================


class KCSourceRef(BaseModel):
    file: str
    slide: int | None = None
    dmap_id: str = ""
    page_ref: str = ""


class KC(BaseModel):
    """Knowledge Component — 知识卡片,课程内最小的知识单元。

    HEC-6:course_id 显式声明,不允许反推。
    """

    id: str
    type: str = "knowledge_component"
    course_id: str  # ★ 显式
    chapter_id: str = ""
    name: str
    bloom_level: str = "Understanding"  # Remembering/Understanding/Applying/Analyzing
    layer: str = "micro"  # micro/meso/macro
    definition: str = ""
    formula: str = ""
    intuition: str = ""
    conditions: list[str] = []
    key_properties: list[dict] = []
    examples: list[str] = []
    common_mistakes: list[str] = []
    prerequisites: list[str] = []
    related: list[str] = []
    exam_frequency: str = "medium"  # high/medium/low
    exam_patterns: list[str] = []
    source_refs: list[KCSourceRef] = []
    valid_at: str = ""
    invalid_at: str | None = None
    version: int = 1
    content_hash: str = ""


class ChapterWiki(BaseModel):
    """章节摘要。"""

    id: str
    course_id: str  # ★ 显式
    chapter_id: str
    title: str
    overview: str = ""
    key_concepts: list[str] = []
    exam_weight: float = 0.0
    difficulty: str = "medium"  # high/medium/low
    prerequisite_chapters: list[str] = []
    unlocks_chapters: list[str] = []
    common_mistakes: list[str] = []


class CourseIndexChapter(BaseModel):
    id: str
    title: str
    key_concepts: list[str] = []
    importance: str = "medium"
    depends_on: list[str] = []


class CourseIndex(BaseModel):
    """课程索引(全局视图)。"""

    course_id: str  # ★ 显式
    course_name: str = ""
    core_topics: list[str] = []
    chapters: list[CourseIndexChapter] = []
    high_frequency_exam_points: list[str] = []
    concept_totals: str = ""
    prerequisite_chain: list[str] = []


class DMAPElement(BaseModel):
    type: str  # paragraph/formula/figure
    id: str
    text_preview: str = ""
    latex: str = ""
    caption: str = ""
    linked_paragraph: str = ""
    page_ref: str = ""


class DMAPCrossRef(BaseModel):
    target_id: str
    relation: str


class DMAPNode(BaseModel):
    type: str  # course/chapter/section
    id: str
    title: str = ""
    source_file: str = ""
    content_hash: str = ""
    page_ref: str = ""
    children: list["DMAPNode"] = []
    elements: list[DMAPElement] = []
    cross_refs: list[DMAPCrossRef] = []


class DMAP(BaseModel):
    """文档结构图(Document MAP)。"""

    course_id: str
    dmap_version: str = "v1"
    root: DMAPNode


# 解决 DMAPNode 自引用
DMAPNode.model_rebuild()


class MerkleTreeNode(BaseModel):
    node_id: str
    content_hash: str
    children_hashes: list[str] = []


class MerkleTree(BaseModel):
    course_id: str
    root_hash: str = ""
    nodes: list[MerkleTreeNode] = []


class ReviewResult(BaseModel):
    passed: bool
    reasons: list[str] = []
    failed_kc_ids: list[str] = []
    fixes: list[dict] = []


class WikiBuildResult(BaseModel):
    course_id: str
    kcs: list[KC] = []
    chapter_wikis: list[ChapterWiki] = []
    course_index: CourseIndex | None = None
    dmap: DMAP | None = None
    merkle_tree: MerkleTree | None = None
