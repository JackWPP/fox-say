import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

NAMESPACE_DMAP = uuid.UUID("12345678-1234-5678-1234-567812345678")  # 稳定 namespace

CourseStatus = Literal["empty", "processing", "ready", "failed"]
MaterialKind = Literal["pdf", "ppt", "image", "text_note"]
Importance = Literal["high", "medium", "low"]
ConfidenceStatus = Literal["grounded", "ambiguous", "out_of_scope"]
AnswerSource = Literal["material", "supplementary"]

# PR0 新增 (锁三线并行的 contract)
QuestionType = Literal[
    "definition", "derivation", "cross_chapter", "refusal", "ambiguous"
]
CognitiveDimension = Literal[
    "factual", "conceptual",
    "procedural_skill", "procedural_principle",
    "metacognitive",
]
PrereqSource = Literal["expert", "etl_auto", "etl_judge_reviewed", "legacy"]
EdgeType = Literal["prerequisite", "related"]


class Course(BaseModel):
    id: str
    title: str
    status: CourseStatus
    teacher: str | None = None
    exam_date: str | None = None
    summary: str = ""
    material_count: int = 0
    icon: str = "📚"


class Material(BaseModel):
    id: str
    course_id: str
    filename: str
    kind: MaterialKind
    status: CourseStatus
    degraded: bool = False
    # New inputs start at revision 1. Rows that predate this field are
    # migrated with revision 0 so callers can distinguish legacy material.
    revision: int = Field(default=1, ge=0)
    # Empty is retained for legacy rows and inputs whose source hash is not
    # available at material creation time.
    content_hash: str = ""


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


class Note(BaseModel):
    id: str
    course_id: str
    title: str
    content: str
    source_citations: list[Citation] = []
    created_at: str = ""
    updated_at: str = ""


class CreateNoteRequest(BaseModel):
    title: str
    content: str
    source_citations: list[Citation] = []


class UpdateNoteRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    source_citations: list[Citation] | None = None


class SourcePreviewResponse(BaseModel):
    text: str
    page_ref: str
    file_name: str
    locator: str


class CragAnswer(BaseModel):
    course_id: str
    answer: str
    citations: list[Citation]
    confidence_status: ConfidenceStatus
    relevance_score: float
    answer_source: AnswerSource = "material"
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
    icon: str = "📚"


class UpdateCourseRequest(BaseModel):
    title: str | None = None
    teacher: str | None = None
    exam_date: str | None = None
    icon: str | None = None


# =============================================================================
# Wiki-First Pipeline Schemas (阶段 2 新增)
# =============================================================================


class KCSourceRef(BaseModel):
    file: str
    slide: int | None = None
    dmap_id: str = ""
    page_ref: str = ""


# ---------------------------------------------------------------------------
# PR0:三线并行的共享 contract — KCPrerequisite / CommonMistake
# ---------------------------------------------------------------------------


class KCPrerequisite(BaseModel):
    """KC 之间的有向依赖关系。

    取代旧 `KC.prerequisites: list[str]` (字符串列表)。
    旧字符串自动迁移到 `KC.prerequisites_raw` (见 KC.model_validator)。

    HEC-6:prerequisite_kc_id 必须是真实存在的 KC.id (uuid5),
           跨课程引用在调用层 (query_tools / agent) 二次校验。

    line A (prereq ETL) 会基于 prerequisites_raw 生成结构化版本,
    填充 dependency_strength (默认 1.0, 后续由 COMMAND/E-PRISM 等
    算法学出真实概率) 和 source。
    """

    prerequisite_kc_id: str
    dependency_strength: float = 1.0  # [0,1] — 冷启动期都设 1.0
    source: PrereqSource = "etl_auto"


class CommonMistake(BaseModel):
    """KC 上挂的常见错误,带可追溯的 bug_rule_id (评测溯源用)。

    取代旧 `KC.common_mistakes: list[str]` (字符串列表)。
    旧字段以 `common_mistakes` 名字保留 (向后兼容),
    新结构化字段挂到 `common_mistakes_v2`。

    评测线 B 的 gold_answer 判定时,可以引用 associated_bug_rule_id
    精准归因 (例如学生选错 = 触发某个 bug_rule)。
    """

    mistake_id: str
    description: str
    associated_bug_rule_id: str = ""


class KC(BaseModel):
    """Knowledge Component — 知识卡片,课程内最小的知识单元。

    HEC-6:course_id 显式声明,不允许反推。

    PR0 升级:
    - prerequisites: list[str] → list[KCPrerequisite] (结构化先修依赖)
      旧字符串通过 model_validator 自动迁移到 prerequisites_raw。
    - 新增 cognitive_dimension (KLI 理论 5 分类)
    - 新增 derivation_steps (理工偏字段:推导过程)
    - 新增 common_mistakes_v2 (结构化常见错误,旧 common_mistakes 保留)
    - 新增学情字段 (一期不更新, 留接口给"贯穿学期"二期)
    - 新增文科字段 (一期不写, 留位置)
    """

    id: str
    type: str = "knowledge_component"
    course_id: str  # ★ 显式
    chapter_id: str = ""
    name: str
    bloom_level: str = "Understanding"  # Remembering/Understanding/Applying/Analyzing/Evaluating/Creating
    layer: str = "micro"  # micro/meso/macro
    definition: str = ""
    formula: str = ""
    intuition: str = ""
    conditions: list[str] = []
    key_properties: list[dict] = []
    examples: list[str] = []

    # --- 常见错误:旧 list[str] 保留,新结构化版本 ---
    common_mistakes: list[str] = []          # 旧字段 (向后兼容,Agent 优先读 v2)
    common_mistakes_v2: list[CommonMistake] = []  # 新结构化

    # --- 先修依赖:旧 list[str] 迁移到 raw,新结构化版本 ---
    prerequisites_raw: list[str] = []        # 旧字符串 fallback (供 ETL 重新对齐)
    prerequisites: list[KCPrerequisite] = []  # 新结构化 (KC_ID + 强度)

    related: list[str] = []
    exam_frequency: str = "medium"  # high/medium/low
    exam_patterns: list[str] = []
    source_refs: list[KCSourceRef] = []
    valid_at: str = ""
    invalid_at: str | None = None
    version: int = 1
    content_hash: str = ""

    # --- PR0 新增:KLI 认知维度 ---
    cognitive_dimension: CognitiveDimension = "conceptual"

    # --- PR0 新增:理工偏字段 ---
    derivation_steps: list[str] = []

    # --- PR0 新增:学情字段 (一期不更新,二期"贯穿学期"用) ---
    last_practiced_at: str | None = None  # ISO datetime
    mastery_score: float = 0.0            # [0,1]
    srs_state: dict | None = None         # FSRS/SM-2 state blob

    # --- PR0 新增:文科留位 (一期不写) ---
    viewpoints: list[str] = []
    counter_arguments: list[str] = []
    classical_quotes: list[str] = []

    # --- 向量检索预计算 ---
    embedding: list[float] | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_fields(cls, data: Any) -> Any:
        """惰性 migration:把老格式字段搬到新字段名,不破坏既有数据。

        触发场景:从 SQLite wiki_kcs.data_json 反序列化老 KC 时,
        老 JSON 里 prerequisites 是 list[str],新 schema 期望 list[KCPrerequisite]。
        本方法在反序列化最前面把老 list[str] 平移到 prerequisites_raw,
        并把 prerequisites 留空 (等 ETL 线 A 后续填充结构化版本)。
        """
        if not isinstance(data, dict):
            return data

        prereqs = data.get("prerequisites")
        # 检测老格式:非空 list 且第一个元素是字符串
        if isinstance(prereqs, list) and prereqs and isinstance(prereqs[0], str):
            # 不覆盖已有 prerequisites_raw (避免幂等问题)
            if not data.get("prerequisites_raw"):
                data["prerequisites_raw"] = list(prereqs)
            data["prerequisites"] = []

        return data


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
    course_summary: str = ""
    dmap: DMAP | None = None
    merkle_tree: MerkleTree | None = None


# =============================================================================
# PR0 新增:评测集 contract (line B 主导)
# =============================================================================


class EvalCase(BaseModel):
    """评测集单条用例 schema。

    line B 的 200 题黄金集每条都是一个 EvalCase。Judge LLM (Qwen3.5 9B)
    会基于 gold_answer / gold_citations / answerability / pedagogical_constraint
    对 FoxSay 实际输出打分。

    设计依据:research_result/FoxSay RAG 评测设计.md "Ground Truth 字段规范"。
    """

    case_id: str  # 全局唯一 (e.g. "LA-CH04-023")
    course_id: str
    question: str
    question_type: QuestionType
    associated_kc_id: str | None = None  # 关联到具体 KC;跨章题可空
    bloom_level: str = "Understanding"
    gold_answer: str
    gold_citations: list[Citation] = []
    gold_evidence_chunks: list[str] = []  # 期望检索到的物理 Chunk ID
    answerability: bool = True  # false = 应拒答 (拒答类题型)
    pedagogical_constraint: str = ""  # 给 Judge 看的强教学规约


# =============================================================================
# PR0 新增:知识图谱 API contract (line C 主导)
# =============================================================================


class KGNode(BaseModel):
    """知识图谱节点。前端 React Flow 渲染。"""

    id: str  # KC.id
    label: str  # KC.name
    chapter_id: str
    mastery: float = 0.0  # [0,1] 一期固定 0,二期接学情
    importance: Importance = "medium"
    cognitive_dimension: CognitiveDimension = "conceptual"


class KGEdge(BaseModel):
    """知识图谱边 (有向)。"""

    source: str  # KC.id (先修)
    target: str  # KC.id (后继)
    strength: float = 1.0  # [0,1]
    edge_type: EdgeType = "prerequisite"


class KnowledgeGraphResponse(BaseModel):
    """GET /courses/{id}/knowledge-graph 响应体。"""

    course_id: str
    nodes: list[KGNode]
    edges: list[KGEdge]
    layout_hint: str = "dagre"  # 给前端的布局算法提示
