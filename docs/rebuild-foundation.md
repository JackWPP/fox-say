# FoxSay 重构基础文档

> 起草时间：2026-07-10
> 状态：v1.0 — 系统传承文档，重构起点
> 目的：把当前系统好的部分、核心思想、spec 整理成一份文档，作为从头重构的基础参考
> 重构顺序：先做文档解析 → 再做 chunking → 再做下游链路

---

## §1. 产品定位与核心思想

### 一句话定位
**FoxSay 是第一个真正理解课程结构的 AI 学习助手**，不是通用问答工具。

### 三个核心承诺
1. **课程边界内回答**：AI 只能基于当前课程已上传或已记录的材料回答，不得用模型常识补齐课程外内容
2. **强制来源引用**：每条非拒答回答必须包含能定位到来源材料和位置的引用，格式如 `来自 [文件名] · 第X部分`
3. **超范围诚实拒答**：当问题超出课程范围时，必须诚实拒答，不得编造、泛化或转向通用百科回答

### 课程为原子单位
- 每门课程完全隔离：材料、向量检索、骨架图、对话历史、复习计划都必须显式绑定 `course_id`
- 禁止跨课程检索
- 所有后端契约都必须包含 `course_id`

### 狐狸人设
- 文案简洁、自信、像狐狸
- 拒答要诚实，不要充满歉意的废话
- 聪明、有点皮的小狐狸，像学长/学姐在给你讲题
- 不要让 UI 看起来像通用企业聊天机器人

### 目标用户与场景
- **用户**：中国在校本科生
- **标杆课**：线性代数（公式密度高、先修结构清晰、题型固定、200 页规模适中）
- **场景**：期末前一周，把整学期 PPT/作业讲解 PDF 全部塞进来，狐狸啃完带复习

---

## §2. CRAG 边界控制策略

CRAG 是 FoxSay 的核心差异化机制：仅当检索到的课程材料足以支撑回答时，助手才给出回答。

### 三档阈值

| 检索分数 | 行为 | 要求 |
|---------|------|------|
| `score >= 0.72` | 正常回答 | 必须包含来自课程材料的引用 |
| `0.55 <= score < 0.72` | 谨慎回答 | 扩大检索，把置信状态标为 `ambiguous`，避免无支撑的论断 |
| `score < 0.55` | 拒答 | 不回答，返回课程范围内的拒答消息 |

### 拒答文案形态

```text
这个问题超出了[课程名]的范围,我不知道。
```

UI 文案可以随狐狸人设变化，但语义必须保留：超出课程范围，不予回答。

### 引用要求

```text
来自 [文件名] · 第X部分
```

如果来源位置尚未可知，系统应暴露最佳的可用定位信息，并把回答标记为不完整以供调试，而不是编造一个定位。

### 调试元数据
后端响应应保留：
- `course_id`
- `relevance_score`（相关性分数）
- `confidence_status`（置信状态：grounded / ambiguous / out_of_scope）
- `refusal_reason`（拒答时的拒答原因）
- retrieval source identifiers（检索来源标识）

生产 UI 可以隐藏调试字段，但测试必须断言这些元数据存在。

---

## §3. MVP 范围与边界

### MVP 内
- 课程表导入：从 CSV/Excel 课程表建立书架和考试倒计时
- 手动创建课程：作为课程表导入失败或缺失时的兜底
- 材料上传与处理：PDF、PPT、图片、文本备注进入课程材料库
- 课程骨架图：材料首次处理完成后生成章节、核心概念、难点和先修链路
- 课程内问答：使用 CRAG 边界控制，回答必须带来源引用
- 超级备考模式：生成复习计划，支持陪伴复习和 `/btw` 插话

### MVP 后（默认不做）
- 诊断 15 题
- 出卷功能
- 多用户、权限、团队协作或账号体系
- 课程胶囊分享、社区广场、社交传播
- 全局日程智能体或学生版 Cowork

### 技术约束
- Frontend: Vite + React + TypeScript + Tailwind
- Backend: FastAPI + Python，由 `uv` 和 `pyproject.toml` 管理
- Vector store: Qdrant（可通过 Docker Compose 或独立容器运行，也支持 local mode 无需 Docker）
- Knowledge graph: MVP 阶段不引入图数据库，骨架从材料直接生成
- RAG direction: 单层 RAG + CRAG 门控（多层混合检索是 post-MVP）
- Deployment: Docker Compose

---

## §4. 工程纪律（HEC 精简版）

> 完整原文在 `AGENTS.md`。这是从过去惨痛教训中固化的硬约束，违反任一条的代码不允许进入 main 分支。

| # | 规则 | 经典反例 |
|---|------|---------|
| **HEC-1** | 错误必须可见，不许静默吞错 | 禁止 `try/except Exception: return ""`；LLM 调用失败必须抛异常或返回带 error 字段的结构 |
| **HEC-2** | 改动必须 commit | 不允许 spec 文档写"已完成"但代码还在 untracked 状态 |
| **HEC-3** | spec 不许自吹 | 任何勾掉的 checklist 项必须有对应的测试或可观察的产出 |
| **HEC-4** | 不许过度工程 | "未来可能用到"不是引入理由；优先删除和复用，而不是新增层 |
| **HEC-5** | 不许杜撰 | 模型名、API endpoint、配置 key 必须真实存在且能跑通；引入前先在 `docs/postmortem/verified.md` 写"已验证"记录 |
| **HEC-6** | schema 显式，不靠反推 | 任何需要 course_id / chapter_id 的对象，字段必须显式声明；禁止 `chapter_id.split("_")[0]` 这种反推补丁 |
| **HEC-7** | 依赖里出现的库必须在代码里被用上 | 装了不用（如声明了 langgraph 但 0 处 import）不允许 |
| **HEC-8** | 文档必须与代码对齐 | `docs/architecture.md` 必须反映实际代码架构；架构变更后必须同步更新 |

### 历史教训
2026-05 曾发生过一次"无人值守 agent 按 自定 spec 跑了一轮 Wiki-First 重构"的工程纪律全面失守事件：5 个新服务文件 + 14 个老文件改动未 commit、测试为 0、venv 坏掉、错误黑洞、依赖装了不用、模型名未验证就硬编码。详见 `docs/postmortem/wiki-first-rampage.md`。HEC 就是这次事件的固化产物。

---

## §5. 核心架构设计（保留部分）

### DMAP（文档结构图）
- 树形结构：course → chapter → section → element（paragraph / formula / figure）
- 从解析后的 chunks 构建（当前输入格式：`[{text, heading, level, page}]`）
- heading 1-2 视为 chapter，heading 3+ 视为 section，无 heading 视为根目录的 paragraph
- 跨节引用靠"第X章"正则匹配
- 是后续 Wiki Build 和骨架图的基础

### LangGraph 4 阶段 Wiki Build
- **Stage 1 Supervisor**：从 DMAP 生成 Worker 任务清单 + 初步 course_index
- **Stage 2 Workers**：并发调 LLM 提取 KC（用 LangGraph `Send()` 派发）
- **Stage 3 Reducer**：合并 KCs（去重 / 交叉引用）
- **Stage 4 Reviewer**：LLM 检查质量，失败打回 Worker 重做（最多 1 次）
- LLM 失败必须抛异常，绝不静默 fallback
- 增量更新顺序：先 invalidate 再 save

### KC（Knowledge Component）
- 课程内最小的知识单元
- 带：先修关系（KCPrerequisite）、认知维度（KLI 5 分类）、常见错误（CommonMistake）、推导步骤
- KC ID 用 `uuid5(NAMESPACE, course_id+chapter_id+name)`，确定性
- 支持理工偏字段（formula / conditions / derivation_steps）和文科留位字段

### ChapterWiki
- 章节摘要：overview / key_concepts / exam_weight / difficulty / prerequisite_chapters
- 由 Wiki Pipeline 自动产出

### Merkle Tree
- 增量更新 diff：新材料上传时只更新受影响的节点
- 每个 DMAP 节点有 content_hash，组合成树形 hash

### 三层混合检索
- **macro**：章节级，文本匹配（不调 embedding API）
- **micro**：KC 级，文本匹配
- **chunk**：向量检索（BGE-M3 embedding）
- 最终由 CRAG 门控决定是否回答

### Agent ReAct 循环
- 7 静态工具 + 4 动态 Skill（共 11 个），max 8 轮
- 静态工具：search_wiki / get_course_map / get_concept / get_chapter_outline / follow_prerequisite / get_source_content / get_review_plan
- 动态 Skill：generate_lecture / generate_quiz / generate_flashcards / show_concept_graph
- 错误必须可见：LLM 失败时 SSE 推 `{type: "error", message: "..."}`
- 5 层防护机制防止工具调用死循环

### SSE 流式推送
- `material_processed`：单个材料处理完成
- `skeleton_ready`：骨架图生成完成
- `course_ready`：所有材料就绪 + 骨架 + 薄弱诊断（"第一个惊喜"）

---

## §6. 核心数据模型（schema 摘要）

> 完整定义在 `backend/app/schemas/foxsay.py`。这里只列字段名+类型+一句话说明。

### Course
- `id: str` / `title: str` / `status: CourseStatus`（empty/processing/ready/failed）
- `teacher: str | None` / `exam_date: str | None` / `summary: str` / `material_count: int` / `icon: str`

### Material
- `id: str` / `course_id: str` / `filename: str` / `kind: MaterialKind`（pdf/ppt/image/text_note）
- `status: CourseStatus` / `degraded: bool`

### CourseSkeleton
- `course_id: str` / `chapters: list[CourseSkeletonChapter]`（id/title/key_concepts/importance/exam_weight）
- `core_concepts: list[str]` / `difficulty_areas: list[str]` / `prerequisite_chain: list[list[str]]`

### KC（Knowledge Component）
- `id: str` / `course_id: str`（显式）/ `chapter_id: str` / `name: str`
- `bloom_level: str` / `layer: str`（micro/meso/macro）/ `cognitive_dimension: CognitiveDimension`
- `definition: str` / `formula: str` / `intuition: str` / `derivation_steps: list[str]`
- `prerequisites: list[KCPrerequisite]`（结构化先修）/ `prerequisites_raw: list[str]`（旧格式 fallback）
- `common_mistakes_v2: list[CommonMistake]`（结构化）/ `common_mistakes: list[str]`（旧格式）
- `source_refs: list[KCSourceRef]`（file/slide/page_ref）
- 学情留位：`last_practiced_at` / `mastery_score` / `srs_state`
- 文科留位：`viewpoints` / `counter_arguments` / `classical_quotes`

### KCPrerequisite
- `prerequisite_kc_id: str`（真实存在的 KC.id）/ `dependency_strength: float` / `source: PrereqSource`

### ChapterWiki
- `id: str` / `course_id: str` / `chapter_id: str` / `title: str`
- `overview: str` / `key_concepts: list[str]` / `exam_weight: float` / `difficulty: str`
- `prerequisite_chapters: list[str]` / `unlocks_chapters: list[str]`

### DMAP / DMAPNode / DMAPElement
- `DMAP`：`course_id: str` / `root: DMAPNode`
- `DMAPNode`：`type`（course/chapter/section）/ `id` / `title` / `children: list[DMAPNode]` / `elements: list[DMAPElement]`
- `DMAPElement`：`type`（paragraph/formula/figure）/ `id` / `text_preview` / `latex` / `page_ref`

### CragAnswer / Citation
- `CragAnswer`：`course_id` / `answer` / `citations: list[Citation]` / `confidence_status` / `relevance_score` / `refusal_reason`
- `Citation`：`file_name: str` / `locator: str`

### MerkleTree
- `course_id: str` / `root_hash: str` / `nodes: list[MerkleTreeNode]`
- `MerkleTreeNode`：`node_id` / `content_hash` / `children_hashes`

### EvalCase（评测）
- `case_id: str` / `course_id: str` / `question: str` / `question_type: QuestionType`
- `gold_answer: str` / `gold_citations: list[Citation]` / `answerability: bool`（false = 应拒答）

### KGNode / KGEdge（知识图谱 API）
- `KGNode`：`id`（KC.id）/ `label` / `chapter_id` / `mastery` / `importance`
- `KGEdge`：`source`（KC.id）/ `target`（KC.id）/ `strength` / `edge_type`

---

## §7. 模型分工

| 角色 | 模型 | 用途 | 配置字段 |
|------|------|------|---------|
| **生成端** | DeepSeek V4 Flash | KC 抽取 / ChapterWiki / Agent 回答 | `DEEPSEEK_*` |
| **Judge** | qwen/qwen3.5-9b（LM Studio 本地） | Faithfulness / 教学规约判定 | `JUDGE_MODEL_NAME` |
| **轻活** | qwen/qwen3-4b-2507（非 reasoning） | cognitive_dim 分类 / JSON 校验 | `JUDGE_FAST_MODEL_NAME` |
| **Embedding** | BAAI/bge-m3（SiliconFlow 远端） | 检索 + prereq fuzzy | `EMBEDDING_*` |

### 已验证可用模型（2026-06）
- `deepseek-v4-flash` / `deepseek-v4-pro`（2026 V4）
- `deepseek-chat` / `deepseek-reasoner`（兼容到 2026/07/24）
- `https://api.deepseek.com`（OpenAI 兼容）
- `BAAI/bge-m3` @ `https://api.siliconflow.cn/v1`
- `qwen/qwen3.5-9b` / `qwen/qwen3-4b-2507` @ `http://localhost:1234/v1`（LM Studio）

### 红线
**DeepSeek 不能当 Judge** — self-preference bias（调研结论）。Judge 必须用不同家族的模型。

### Qwen3.5 9B 特性
- 是 reasoning 模型，LM Studio 关不掉 thinking
- 每次调用预算 ~2000 token，timeout ≥ 60s

---

## §8. 技术栈

### Frontend
- Vite + React 18 + TypeScript + Tailwind
- MarkdownRenderer：react-markdown + remark-gfm + remark-math + rehype-katex（已有）
- 知识图谱：reactflow + dagre 布局（非 Neo4j）
- 三栏布局（NotebookLM 风格）：SourcesPanel | ChatWorkspace | StudioPanel

### Backend
- FastAPI + Python 3.12，由 `uv` 和 `pyproject.toml` 管理
- 39 个 API 端点
- SQLite 持久化（materials.parsed_text 等，进程重启不丢失）

### Vector store
- Qdrant（course-scoped collection，按 course_id 隔离）
- 支持两种模式：
  - `qdrant_url` 为空 → 进程内 local mode（文件持久化，无需 Docker，默认）
  - `qdrant_url = "http://host:port"` → 远程模式（Qdrant 单独容器）
- Embedding 维度：1024（BGE-M3）

### 部署
- Docker Compose（Qdrant container）
- 所有模型、向量存储、运行时设置必须走环境变量，不得硬编码

---

## §9. 文档解析现状与重构方向

### 现状
三层 fallback 解析链（`backend/app/services/parsing.py`）：

```
Layer 1: markitdown（统一入口，输出 Markdown 文本）
Layer 2: pdfplumber / python-pptx / utf-8 open（原生解析器，输出纯文本）
Layer 3: MinerU 云端 OCR（仅 PDF/图片，输出 Markdown，作为最后兜底）
```

另有 `parsing_docling.py` 用 Docling 提取 heading/level/page 结构化 chunks，但几乎没被真正使用。

### 痛点（按严重程度排序）

1. **结构信息全部丢失**：`parse_document()` 最终返回 flat string。Docling 提取的 heading/level/page 在 pipeline 中被重置为单元素列表，章节层级、页面定位、标题树全部塌缩。

2. **没有统一的文档中间表示**：markitdown 输出 Markdown 字符串，Docling 输出结构化 chunks，MinerU 输出 Markdown，pdfplumber 输出纯文本。四种输出格式没有统一到一个标准文档模型上。

3. **chunking 极度简陋**：`chunking.py` 按 500 字符 + 50 overlap 硬切，完全不考虑标题边界、段落语义、页面边界。切分后的 chunk 不保留 heading/level/page/source 等 metadata。

4. **来源引用无法精确定位**：当前 chunk metadata 只有 `course_id / material_id / file_name`，没有 chapter/section/page 信息，导致"来自 [文件名] · 第X部分"这种引用只能靠 LLM 猜。

5. **图片/表格/公式的语义丢失**：PPT 只抽了文字；PDF 中的表格被压成乱序文本；公式没有被结构化保留；图片内容没有描述性 alt text。

6. **Pipeline 耦合严重**：`pipeline.py` 把 parsing → chunking → embedding → storing → dmap → wiki → skeleton 全串在一起，解析结果直接被 chunking 消费，没有中间层。

### 重构目标
以 **Markdown 为统一中间表示**，搭建一条可扩展的文档解析 Pipeline，作为后续所有操作（DMAP/wiki/chunking/RAG/引用追溯/前端渲染）的坚实基座。

核心诉求两点：
1. **任意输入 → 结构化 Markdown**：PDF / PPT / Word / 图片 / HTML / 文本都输出高质量结构化 Markdown，保留标题层级、表格、公式、页码
2. **图片提取与保存**：PDF/PPT/Word 中的图片被提取保存为独立文件，在 Markdown 中以 `![描述](路径)` 引用，作为后续多模态处理的输入

### 调研报告参考
`FoxSay Document Parsing Research.md` 提出了 4 分支路由方案：
- Word/Excel → MarkItDown
- 数字 PDF → Docling（本地，结构化大纲 + TableFormer）
- 扫描 PDF → MinerU 云端 API
- 图片/零散文本 → VLM

并定义了统一 Markdown 输出规范、图片物理存储结构、`BaseDocumentParser` 抽象接口。

### 调研报告与现状的差异修正

| 维度 | 调研报告方案 | 项目现状 | 修正方向 |
|------|------------|---------|---------|
| 数据库 | PostgreSQL `document_extracted_assets` 表 | SQLite | 改用 SQLite，新增 `extracted_assets` 表 |
| MinerU API | V4 `extract/task`，需 JWT Bearer token | V1 `agent/parse`，无需 token，IP 限频（已验证） | 继续用 V1，V4 需 token 未验证 |
| PPT 分支 | 挂起，抛 NotImplementedError | 现有 `parse_pptx` 用 python-pptx 跑着 | 保留 python-pptx 兜底，不挂起 |
| VLM 分支 | DeepSeek VLM API | DeepSeek 是纯文本 LLM，没有视觉模型 | 图片 alt text 需另选 VLM（SiliconFlow 上的 Qwen-VL 等），需先验证 |
| 图片存储路径 | `backend/data/storage/images/{doc_id}/` | 现有 `uploads/{course_id}/` 存原始文件 | 新增 `data/extracted_images/{course_id}/{material_id}/` |

### 重构顺序
1. **先做文档解析入口**：定义统一接口 + 输出模型 + 路由入口 + 图片提取
2. **再做 chunking**：基于统一文档模型设计结构感知切分
3. **再做下游**：DMAP / wiki / retrieval / 引用追溯

---

## §10. 重构推进原则

1. **从入口做起，每步可验证再推进**：不一次性重写整个 pipeline
2. **保留 §1-8 的核心设计，不推翻重来**：产品定位、CRAG、HEC、架构设计、数据模型都是好的，保留
3. **新增依赖前先写 `docs/postmortem/verified.md`**：模型名、API endpoint、配置 key 必须真实存在且能跑通
4. **错误必须可见，不许静默吞错**：解析失败要抛异常或返回错误信息，不能返回空字符串
5. **优先复用现有依赖**：markitdown / docling / pdfplumber / python-pptx 已在 pyproject.toml，新增依赖需充分论证
6. **schema 显式带 course_id**：所有新数据结构（如 ExtractedAssetMeta）必须显式声明 course_id + material_id
7. **文档与代码对齐**：架构变更后同步更新 `docs/architecture.md`

---

## 附：关键文件索引

| 文件 | 内容 |
|------|------|
| `AGENTS.md` | 工程约束 + 产品边界 + MVP scope（最高优先级） |
| `docs/project-charter.md` | 项目定位 + 技术路线 + 决策记录 |
| `docs/product-boundaries.md` | MVP 范围 + 产品语气 |
| `docs/crag-policy.md` | CRAG 阈值 + 引用要求 |
| `docs/architecture.md` | MVP 架构图 + 数据流 |
| `docs/contracts-v1-pr0.md` | 三线并行 schema 锁定 |
| `docs/postmortem/verified.md` | 已验证外部依赖记录 |
| `docs/postmortem/wiki-first-rampage.md` | 工程纪律失守复盘 |
| `backend/app/schemas/foxsay.py` | 核心数据模型（450 行） |
| `backend/app/services/parsing.py` | 当前解析入口（待重构） |
| `backend/app/services/pipeline.py` | 7 步处理流水线 |
| `backend/app/services/chunking.py` | 字符切分（待重构） |
| `backend/app/services/dmap.py` | 文档结构图构建 |
| `backend/app/services/wiki_builder.py` | 4 阶段 Wiki 构建 |
| `backend/app/services/agent.py` | Agent 主循环 + 7 工具 |
| `backend/app/services/retrieval.py` | CRAG 检索 |
| `FoxSay Document Parsing Research.md` | 文档解析调研报告 |
