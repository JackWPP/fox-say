# FoxSay — HANDOFF 文档

> **已过时（2026-07-11）**：本文记录的是 2026-07-10 的 legacy Wiki/Agent 链路，不能描述当前证据优先 V2 的实际边界。继续开发前请以 [docs/architecture.md](docs/architecture.md)、[V2 实施蓝图](docs/knowledge-system-v2-implementation-plan.md) 与 [V2 任务台账](docs/knowledge-system-v2-task-registry.md) 为准。

> **写这份文档的人**:上一任 Claude(当前 session 的 main agent,已完成三线并行集成 + 全部验收)
> **文档目的**:用户换电脑后,新 agent 无任何上下文,通过这份文档 **+ 仓库自身** 即可继续开发
> **目标读者**:下一任 Claude agent(可能不同的模型/版本)
> **最后更新**:2026-07-10 (文档管线重构 + CRAG 策略放宽 + Office MinerU 集成)

---

## 0. 30 秒速览(TL;DR)

```yaml
项目:       FoxSay — 课程级 AI 学习 Copilot
核心承诺:   严格课程边界内回答 + 强制引用 + 越界拒答
人设:       贱贱的小狐狸
技术栈:     FastAPI + React/Vite + SQLite + Qdrant + LangGraph + DeepSeek/Qwen
当前分支:   feature/pr0-schema-contracts
当前 HEAD:  e437ab3
工作树:     干净
测试:       168 / 168 通过
远端:       origin/main 已是 PR0 后(b83ebbe..9fae15e),本地领先 60 个 commit
标杆课:     线性代数(中国本科生,期末抱佛脚)
```

**如果你只能做 1 件事**:读 `AGENTS.md` + `docs/contracts-v1-pr0.md` + 这份文档的 §3-4(决策)+ §13-15(踩坑),然后问用户接下来做什么。

---

## 1. 这份仓库在搞什么(人话版)

**FoxSay = 期末抱佛脚场景下,帮中国本科生啃一门课的 AI 狐狸。**

学生场景:
- 期末前一周,把《线性代数》整学期 PPT/作业讲解 PDF 全部塞进来
- 小狐狸啃完,主动说"这门课你最薄的是第五章,我们先攻这里"
- 学生在浏览器看到一张图谱:节点 = 知识点(特征值、特征向量...),边 = 先修关系,红/绿/灰 = 薄弱/掌握/未学
- 点节点弹抽屉:解释 + 出题 + 判对错 + 错题溯源到先修概念
- 问超范围的问题 → 小狐狸:**"这超出了线性代数的范围,不知道。"**

这不是通用聊天框 — 这是**有结构的学习体验**,后端有 DMAP/KC/ChapterWiki/Merkle/Agent 等复杂架构支撑。

**架构故事** (从 v0 → v1):
```
v0 (mvp 初版):  PDF → 文本分块 → embedding → 向量库 → 聊天框
                          ↓ 调研发现
                  这是"另一个 RAG 问答",没差异化
                          ↓ 决策改路线
v1 (当前):      PDF → MinerU V4/V1 primary (路由+归一化)
                          → DMAP (文档结构图)
                          → LangGraph 4 阶段 Wiki 构建 (Supervisor→Workers→Reducer→Reviewer)
                          → KC (Knowledge Component) 抽取 + Merkle 增量合并
                          → LangChain 语义切块 (MarkdownHeaderTextSplitter + 表格保护)
                          → 11 工具 Agent (7静态+4动态Skill) + 三层检索 (全 embedding cosine)
                          → CRAG 透明门控 (score<0.55 补充回答+强制披露)
                          → 知识图谱可视化
```

**当前进度**:从 PRD 46% → **~65%**。MVP 6 项功能代码层面全部实现且部分超规格(NotebookLM 三栏布局、4 动态 Skill、超级备考状态机),工程纪律已修复(HEC-1/5/7/8),但尚未在真实《线代》材料上端到端跑通。

---

## 2. 接手前必读(5 份文档,按顺序)

| 序 | 文档 | 路径 | 你要从中拿到的 |
|---|---|---|---|
| 1 | Agent Operating Contract | `AGENTS.md` | HEC-1~7 工程纪律,产品边界,MVP scope |
| 2 | PR0 Contracts | `docs/contracts-v1-pr0.md` | KCPrerequisite / EvalCase / KGNode 等锁定 schema |
| 3 | 架构总览 | `docs/architecture.md` | MVP 架构图 + 数据流 |
| 4 | CRAG 策略 | `docs/crag-policy.md` | 检索置信度阈值 (0.72/0.55) |
| 5 | 现状与 PRD 差距 | `docs/gap-analysis.md` | 各功能完成度(约 46% 的旧评估,部分已超) |
| 5.5 | (可选) Refactor plan | `docs/refactor-plan-2026-06.md` | 当前禁止模式清单 |
| 5.6 | (可选) Product Boundaries | `docs/product-boundaries.md` | MVP 后哪些功能**不能**做 |
| 5.7 | (可选) PRD 路线图 | `docs/roadmap-to-prd.md` | **已过时**,实际架构已偏离 |

**重要**:`roadmap-to-prd.md` 描述的是"三元组 + Neo4j + LightRAG 双层检索",但**实际代码已经走"DMAP + KC + ChapterWiki"路线**。别照它做。

---

## 3. 决策已锁清单(不可改,除非用户开新决策会)

> 这一节是**最高优先级**。任何"我以为应该改"的冲动,先来这一节对照。

### 决策 1:产品 = 小狐狸吃完一门课带你过期末

- 单课聚焦,书架页保留但不强化
- **不做**:家长侧、老师侧、移动端、账号体系、SaaS 计费

### 决策 2:用户 = 中国本科生

- UI 复杂度按 PC web 设计
- 不需要家长 / 老师侧
- mobile 是 P2,本地存 localStorage 足够

### 决策 3:场景 = 期末抱佛脚(一期),贯穿学期(后)

| 一期不做 | 一期留接口 |
|---|---|
| FSRS / SM-2 算法 | `last_practiced_at` (KC 字段) |
| 推送提醒 (cron / FCM) | `mastery_score` (KC 字段) |
| 遗忘曲线建模 | `srs_state: dict` (KC 字段) |
| BKT / DKT 知识追踪 | |
| 跨课程"今天学哪门"推荐 | |
| 错题本 SRS | (留 `wrong_answers` 表但前端不暴露) |

### 决策 4:学科 = 理文都要,但**一期标杆 = 某门理工科公共课**

一期:**线性代数**(已选定,详见决策 6)。
KC schema 理工偏字段先重(`formula` / `conditions` / `derivation_steps`)。
文科分支字段(schema 留位置不实现):`viewpoints` / `counter_arguments` / `classical_quotes`。

### 决策 5:模型分工(Qwen3 部署在 LM Studio @ 192.168.1.40:1234)

| 角色 | 模型 | 用途 | 配置字段 |
|---|---|---|---|
| **生成端** | DeepSeek V4 Flash | KC 抽取 / ChapterWiki / 出题 / Agent 回答 | `DEEPSEEK_*` |
| **主 Judge** | qwen/qwen3.5-9b (reasoning) | Faithfulness / 教学规约判定 | `JUDGE_MODEL_NAME` |
| **批量轻活** | qwen/qwen3-4b-2507 (非 reasoning) | cognitive_dim 5 选 1 / JSON 格式校验 / 题库自检 | `JUDGE_FAST_MODEL_NAME` |
| **NLI 蕴含** | qwen3-reranker-0.6b | 评测 v2 ALiiCE 引文细粒度判定 | `RERANKER_MODEL_NAME` |
| **Embedding** | BAAI/bge-m3 (SiliconFlow 远端) | 检索 + prereq fuzzy | `EMBEDDING_*` |

**红线**:**DeepSeek 不能当 Judge** — self-preference bias (调研结论,见 `research_result/FoxSay RAG 评测设计.md`)。

**Qwen3.5 9B 重要特性**:是 reasoning 模型,LM Studio 关不掉 thinking,每次调用预算 **~2000 token**,timeout ≥ 60s。
**qwen3-4b-2507**:非 reasoning,6 token 出答案,**大批量轻活用这个**。

### 决策 6:一期标杆课 = 线性代数

理由(已选):
1. 公式密度高但短,Marker 接入压力小
2. KC 之间先修结构**最清晰**(向量空间 → 线性变换 → 特征值...),图谱可视化 demo 杀伤力最大
3. 题型固定,对错明确,评测客观
4. 200 页规模,跑一遍 wiki_build pipeline 不至于太烧 token

冷启动期 KC 库是 0,所有 30 题 EvalCase 大部分 `answerability=False`(拒答)以避免幻觉。
当用户**首次喂真实《线代》材料**时,这套脚手架才真正被激活。

---

## 4. HEC 工程纪律(7 条,从不妥协)

> 完整原文在 `AGENTS.md`。这是精简版,每条下都有"这一条发生过什么惨痛教训"。

| # | 规则 | 经典反例 |
|---|---|---|
| **HEC-1** | 错误必须可见,不许 `try/except: return ""` | LLM 调用失败必须抛异常或返回带 error 字段的结构 |
| **HEC-2** | 改动必须 commit,不许活在 working tree | wip 也必须 commit 带 `wip:` 前缀,在 feature 分支 |
| **HEC-3** | spec 不许自吹,checklist 必须对应真实测试 | 任何勾掉的项必须有可验证产出 |
| **HEC-4** | 不许过度工程 | "未来可能用到"不是引入理由 |
| **HEC-5** | 不许杜撰 | 模型名 / API endpoint / 配置 key 必须真存在,引入前写 `docs/postmortem/verified.md` |
| **HEC-6** | schema 显式带 `course_id`,禁止反推 | 禁止 `chapter_id.split("_")[0]` 那种丑陋补丁 |
| **HEC-7** | 依赖里出现的库必须真用上 | pyproject.toml 写了 langgraph 但 0 处 import 不允许 |

**违反任一条的代码不允许进 main 分支。**

---

## 5. 当前 Git 状态(精确)

### 5.1 分支 / HEAD

```
当前分支:   feature/pr0-schema-contracts
HEAD:       e437ab3
远端:       origin  → https://github.com/JackWPP/fox-say.git
origin/main: 9fae15e (PR0 + 之后 HEAD 60 个 commit 未 push)
working tree: 干净(git status 无输出)
```

### 5.2 最近 commit 历史(最近 10 个)

```
e437ab3 (HEAD) fix: 工程纪律修复(HEC-1/5/8) + Agent稳定性提升 + 前端错误体验优化
13dc17b fix(course-summary): 修复课程概述为空问题，添加AI重新生成API和结构化fallback
fe19565 fix: 422 error when starting review mode without exam date
3bf1194 fix: UI polish - KaTeX rendering, UUID filenames, session title, React Flow warnings
37c94b9 fix: vite proxy端口从8080改为8000
0e3ef94 fix: 浏览器实际测试发现的bug修复
30c2594 feat: 课程概述自动生成 + Agent工具调用加固 + 备考入口统一
c58849c docs: 更新spec任务和checklist状态 - 所有任务已完成
3487c57 docs: NotebookLM UI升级spec文档
4cc5391 feat: NotebookLM风格UI升级 - 三栏布局+白底AI消息
```

更早的 commit 历史可运行 `git log --oneline` 查看。

### 5.3 Worktree(每个 agent 跑过的隔离 worktree,**当前都已停止**)

```
.worktree-agent-abc3567b1f382b5c6 (Line A, base=9fae15e, commit=59242ca)
.worktree-agent-ac3c76e9083790d41  (Line B, base=9fae15e, commit=c7d5b0a)
.worktree-agent-ad1b8a6b00a56b442 (Line C, base=9fae15e, commit=d69a0f2)
```

可以 `git worktree prune` 清理。**重要**:下次启新 agent 时,worktree 默认 base 是 `origin/main` 而不是 HEAD — 见 §14 踩坑档案。

---

## 6. 项目文件清单(13k 行)

### 6.1 Backend (`backend/`)

```
app/
├── main.py                          FastAPI app + lifespan + CORS
├── api/                             路由层 (8 router)
│   ├── chat.py                      /chat (legacy CRAG) + /chat/stream (Agent SSE)
│   ├── courses.py                   课程 CRUD + 课程表导入
│   ├── events.py                    SSE 推送 (material_processed / skeleton_ready)
│   ├── knowledge_graph.py           ★ Line C 新增 /knowledge-graph endpoint
│   ├── materials.py                 上传 + 状态查询
│   ├── review.py                    复习计划生成
│   ├── review_session.py            复习会话状态机
│   ├── settings.py                  用户设置
│   └── skeleton.py                  骨架图查询
├── core/
│   ├── config.py                    ★ PR0 加 judge_* + deepseek_*
│   └── settings.py                  旧 Settings (deprecated?)
├── db/
│   └── sqlite_store.py              SQLite 数据访问 (12+ 表)
├── schemas/
│   └── foxsay.py                    ★ PR0 433 行,核心 schema
└── services/                        业务逻辑
    ├── agent.py                     ★ 11 工具 Agent ReAct 主循环 (7静态+4动态Skill, max 8轮)
    ├── chunking.py                  ★ LangChain 语义切块 (MarkdownHeaderTextSplitter + 表格保护)
    ├── crag.py                      老 RAG (legacy, 待清理)
    ├── dmap.py                      文档结构图构建
    ├── embedding.py                 BGE-M3 调用
    ├── guard.py                     内容安全守卫
    ├── merkle.py                    Merkle Tree diff
    ├── mineru.py                    ★ MinerU V4/V1 hybrid API (PRIMARY 解析器, 1000 pages/day quota)
    ├── normalizer.py                ★★ 新增: Markdown 归一化引擎 (页面锚定 + 表格保护 + 公式对齐)
    ├── parser_interface.py          ★★ 新增: 解析器抽象基类 + UnifiedParserOutput schema
    ├── parsing.py                   ★★ 路由器: 文件类型分发 → MinerU primary → fallback 链
    ├── parsing_docling.py           Docling 集成 (电子版 PDF fallback)
    ├── pdf_detector.py              ★★ 新增: PyMuPDF 快速探测 PDF 电子/扫描件
    ├── pipeline.py                  ★ 7 步处理流水线 (解析含路由+归一化子步)
    ├── query_tools.py               ★ 8 个查询函数实现 (dispatch 合并为 7 个工具)
    ├── retrieval.py                 ★ 三层混合检索 (全 embedding cosine, 已移除 Jaccard)
    ├── review.py                    复习计划 LLM 生成
    ├── skeleton.py                  骨架图 LLM 生成 (legacy, 待清理)
    ├── timetable.py                 课程表解析
    ├── vectorstore.py               Qdrant 客户端
    ├── vlm_parser.py                ★★ 新增: VLM 多模态图片解析分支
    └── wiki_builder.py              ★★ LangGraph 4 阶段 Wiki 构建
eval/                                ★ Line B 新增
├── __init__.py
├── schemas.py                       EvalReport / EvalMetrics 内部 schema
├── generator.py                     DeepSeek 生成 EvalCase 列表
├── validator.py                     Qwen3-4b 7 规则自检
├── judge.py                         Qwen3.5-9b Faithfulness Judge
└── runner.py                        串起来
scripts/                             ★ Line A + 转发层
├── __init__.py
└── align_prerequisites.py           ★ Line A 主脚本(415 行)
tests/                               ★ 157 测试
├── conftest.py                      共享 fixture
├── test_agent_loop.py               Agent 11 工具测试
├── test_align_prerequisites.py      ★ 9 测试
├── test_courses.py / test_materials.py / test_merkle.py
├── test_crag.py                     CRAG 三档阈值
├── test_dmap.py                     DMAP 构建
├── test_eval_*.py                   ★ 48 测试 (4 文件)
├── test_knowledge_graph.py          ★ 4 测试
├── test_pr0_contracts.py            ★ 18 测试
├── test_query_tools.py              query_tools 测试
├── test_review.py / test_skeleton.py / test_skeleton_wiki.py
└── test_wiki_builder.py             Wiki Builder 4 阶段
```

### 6.2 Frontend (`frontend/src/`)

```
app/
├── App.tsx                          路由 + OnboardingGuard
└── Layout.tsx                       全局布局

features/
├── bookshelf/                       书架 (首页)
│   ├── BookshelfPage.tsx
│   ├── CourseCard.tsx
│   ├── CreateCourseModal.tsx
│   ├── ImportTimetableModal.tsx
│   └── useCourses.ts
├── course/                          课程详情
│   ├── ChatTab.tsx                  ★ Agent SSE 流式对话
│   ├── CitationCard.tsx             引用卡片
│   ├── CourseDetailPage.tsx         ★ Line C 改了 5 行
│   ├── KnowledgeGraphTab.tsx        ★ Line C 新增 (reactflow)
│   ├── MarkdownRenderer.tsx         Markdown + DSML strip
│   ├── MaterialList / MaterialUpload / MaterialsTab
│   ├── ReviewTab / ReviewPlanView
│   ├── SkeletonTab / SkeletonTree
│   ├── BtwInput.tsx                 /btw 插话
│   ├── ChatInput / ChatMessage / ToolCallIndicator
│   └── useChat / useKnowledgeGraph / useMaterials / useReview / useSkeleton
├── onboarding/
│   └── OnboardingPage.tsx           3 步引导(本地存 localStorage)

shared/
├── api.ts                           HTTP 客户端
├── fox-copy.ts                      狐狸语气文案
└── types.ts                         共享类型

types/
└── foxsay.ts                        旧类型定义(可能被 shared/ 替代)
```

### 6.3 文档与调研

```
AGENTS.md                            ← 必读
FoxSay-Architecture-Review.md        上次会话初期的架构评审
FoxSay-Review-Conclusion.md          对应结论(5 分钟可读版)
HANDOFF.md                           ← 本文档
docs/
├── architecture.md                  MVP 架构图
├── contracts-v1-pr0.md              ★ PR0 schema 锁定
├── crag-policy.md                   检索阈值
├── gap-analysis.md                  完成度评估(46%,部分已超)
├── product-boundaries.md            MVP 后哪些不能做
├── refactor-plan-2026-06.md         禁止模式清单
├── roadmap-to-prd.md                ★ 已过时,别照做
└── postmortem/
    └── wiki-first-rampage.md        Wiki-First 重构复盘
research_result/                     ★ 三份调研(可重读)
├── FoxSay KC Schema Optimization.md
├── FoxSay RAG 评测设计.md
└── 课程知识图谱可视化调研.md
```

---

## 7. 架构深度(接手后改东西必看)

### 7.1 数据模型核心(PR0 后)

```
Course (id, title, status, exam_date)
   └── Material (id, course_id, filename, kind)
       └── DMAP (course_id, root → chapters → elements + cross_refs)
           ├── KC (id, course_id, chapter_id, name, bloom_level,
           │      layer, definition, formula, derivation_steps,
           │      cognitive_dimension, common_mistakes_v2,
           │      prerequisites_raw, prerequisites: list[KCPrerequisite],
           │      mastery_score, srs_state, ...)
           ├── ChapterWiki (course_id, chapter_id, title, overview, ...)
           └── CourseIndex (course_id, chapters, ...)
   └── ChatSession → ChatMessage
   └── ReviewSession → DailyPlan
```

**Prerequisite 路径**:
- 新 `prerequisites: list[KCPrerequisite]` ← `Line A` ETL 填充
- 旧 `prerequisites_raw: list[str]` ← 旧 LLM 抽取结果,fallback 用
- 自动迁移:KC 反序列化时若 `prerequisites` 是 list[str],自动搬到 `prerequisites_raw`

### 7.2 Pipeline 7 步(用户上传材料后触发)

```
parsing[路由+归一化] → build_dmap → wiki_build → chunking[语义切块] → embedding → storing → skeleton_generating
```

Parsing 子步:
1. 文件类型路由 (PDF/Office/XLSX/图片/文本)
2. PDF: PyMuPDF 探测电子/扫描件 → MinerU V4 primary → Docling/pdfplumber fallback
3. Office: MinerU V4 (native) → MarkItDown/python-pptx fallback
4. 归一化: NormalizationEngine (页面锚定 + 表格保护 + 公式对齐 + 全局编号)
5. extracted_assets 写入 SQLite

每个 step 写到 `tasks` 表,SSE 通过 `push_event` 推前端。
Wiki build 是 4 阶段 LangGraph(Supervisor→Workers[Send 并发]→Reducer→Reviewer)。
Chunking 使用 LangChain MarkdownHeaderTextSplitter + 表格不可分割 + 上下文标题 prepend。

### 7.3 Agent 11 工具 ReAct(8 轮 max, round 5 软性强制)

```
# 7 静态工具
search_wiki          三层混合检索 (macro=章节, micro=KC, all=合并, 全 embedding cosine)
get_course_map       拿课程索引全文
get_concept          按 concept_id 或 concept_name 拿完整 KC 卡
get_chapter_outline  按 chapter_id 或 chapter_title 拿章节摘要
follow_prerequisite  沿 prerequisites 链向上回溯
get_source_content   按 dmap_id 拿原始材料片段
get_review_plan      拿复习计划

# 4 动态 Skill (skills.py 注册)
generate_lecture     生成章节讲义 (Markdown)
generate_quiz        生成章节练习题 (含答案解析)
generate_flashcards  生成章节闪卡 (front/back)
show_concept_graph   显示概念先修图谱
```

**DSML 防御**:DeepSeek V4 Flash 有时会输出 `<|DSML|...|>` 假装是 tool_call,需要 strip。
**max_rounds=8**(原 5→3→8, round 5 软性强制回答, streak≥2 强制回答)。
**CRAG 透明门控**:score < 0.55 时不再硬拒答,允许基于通用知识补充回答,但强制标注 `answer_source: "supplementary"` + 声明课程材料未覆盖。

### 7.4 API 端点

```
GET    /health
POST   /courses                          创建课程
GET    /courses                          列表
GET    /courses/{id}                     详情
POST   /courses/{id}/chat                老 CRAG
POST   /courses/{id}/chat/stream         Agent SSE
GET    /courses/{id}/chat/sessions       会话列表
POST   /courses/{id}/chat/sessions       创建会话
DELETE /courses/{id}/chat/sessions/{sid}
GET    /courses/{id}/chat/history        消息历史(分页)
POST   /courses/{id}/materials           上传
GET    /courses/{id}/materials           列表
GET    /courses/{id}/materials/{mid}/status
POST   /courses/{id}/skeleton/generate
GET    /courses/{id}/skeleton
POST   /courses/{id}/review-plan
GET    /courses/{id}/review-plan
POST   /courses/{id}/review/start
POST   /courses/{id}/review/advance
GET    /courses/{id}/review/progress
POST   /courses/{id}/review/btw
GET    /courses/{id}/knowledge-graph     ★ Line C 新增
GET    /events                           SSE 事件流
GET    /docs                             OpenAPI
```

---

## 8. 怎么启动 / 开发 / 测试

### 8.1 环境准备

```bash
# Backend
cd D:/fox-say/backend
uv sync                                    # 装依赖
uv run uvicorn app.main:app --reload       # 起服务(http://localhost:8000)

# Frontend (另一个 shell)
cd D:/fox-say/frontend
npm install
npm run dev                                # 起 Vite(http://localhost:5173)

# 浏览器访问 http://localhost:5173
```

### 8.2 跑测试

```bash
# 后端全套
cd D:/fox-say/backend
uv run pytest tests/ -v --no-header

# 只跑某模块
uv run pytest tests/test_eval_*.py -v

# 前端
cd D:/fox-say/frontend
npm run build
```

**预期**:157 个后端测试全过。`test_align_prerequisites.py` (9) + `test_eval_*.py` (48) + `test_knowledge_graph.py` (4) + `test_pr0_contracts.py` (18) + 既有 78 个。

### 8.3 跑评测 pilot(可选)

```bash
cd D:/fox-say/backend
uv run python -m scripts.run_eval --help
# 真跑 mock mode:
uv run python -m scripts.run_eval --course-id <some-id> --pilot --mock-foxsay
```

### 8.4 加新功能的标准流程

1. 读 `AGENTS.md` 7 条 HEC
2. **确认产品定位**是否还在范围(参考 §3 决策)
3. **确认 schema** 是否需要新字段(参考 `docs/contracts-v1-pr0.md`,新字段需 PR review)
4. **写测试**(mock 优于真调,见 `test_query_tools.py::_MockStore`)
5. 写代码
6. `git commit` 到当前 feature 分支(严禁 untracked 长期存在)
7. 跑全套 pytest 验证不退步

### 8.5 创建 Agent 时用 worktree 的正确姿势

```bash
# 第一步(每次开始新任务前):**确保 origin/main 含你的 commit**
# 否则 sub-agent 会在老 base 上跑(详见 §14)

git fetch origin
# 看 origin/main 跟你当前 HEAD 差几个 commit
git log origin/main..HEAD --oneline

# 如果有未 push 的 commit,先 push:
git push origin feature/pr0-schema-contracts    # 不破坏 origin/main

# 然后再启 agent
```

---

## 9. 模型配置详情

### 9.1 配置位置

`.env`(根目录,gitignore,手动维护):
```bash
# 生成端
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

# Embedding (远端)
EMBEDDING_API_KEY=sk-...
EMBEDDING_API_BASE=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3

# Judge 端 (LM Studio 本地 @ 192.168.1.40:1234)
JUDGE_API_KEY=lm-studio
JUDGE_API_BASE=http://192.168.1.40:1234/v1
JUDGE_MODEL_NAME=qwen/qwen3.5-9b
JUDGE_FAST_MODEL_NAME=qwen/qwen3-4b-2507
RERANKER_MODEL_NAME=qwen3-reranker-0.6b
```

**LM Studio 关键 endpoint**:
- `GET /v1/models` 列出可用模型
- `POST /v1/chat/completions` OpenAI 兼容
- `POST /v1/embeddings`(如果换成 LM Studio embed)

### 9.2 模型 ID 在 LM Studio 里(用户实测)

```
qwen/qwen3.5-9b                          reasoning, ~2000 token/次
qwen/qwen3-4b-2507                       非 reasoning, 快, 6 token 出答案
qwen3-reranker-0.6b                      NLI reranker
text-embedding-nomic-embed-text-v1.5     备选 embedding
qwen/qwen3-4b-2507 / qwen3-vl-8b         (用户机器上也有,但暂未用)
```

### 9.3 调用 Judge 代码模式

```python
from openai import OpenAI
from app.core.config import settings

client = OpenAI(
    api_key=settings.judge_api_key,
    base_url=settings.judge_api_base,  # LM Studio 兼容
)

# Reasoning 模型:
response = client.chat.completions.create(
    model=settings.judge_model_name,        # qwen/qwen3.5-9b
    messages=[...],
    max_tokens=2500,                        # 给 reasoning 留空间
    timeout=60,                             # reasoning 慢
)

# 非 reasoning 模型:
response = client.chat.completions.create(
    model=settings.judge_fast_model_name,    # qwen/qwen3-4b-2507
    messages=[...],
    max_tokens=200,
    timeout=15,
)
```

---

## 10. PR0 schema 详情(必读 `docs/contracts-v1-pr0.md`)

### 新增 schema (5 个)

| Schema | 行数(大致) | 谁产 | 谁消费 |
|---|---|---|---|
| `KCPrerequisite` | ~10 | Line A ETL | Line B/C |
| `CommonMistake` | ~15 | LLM 抽 KC | 前端 / 评测溯源 |
| `EvalCase` | ~25 | Line B 评测 | Line B 自测 |
| `KGNode / KGEdge / KnowledgeGraphResponse` | ~20 | Line C 后端 | Line C 前端 |

### KC schema 升级

| 字段 | 状态 | 用途 |
|---|---|---|
| `prerequisites: list[str]` | **deprecate** | 旧字段保留作 fallback |
| `prerequisites_raw: list[str]` | **新增** | 旧字符串保留 |
| `prerequisites: list[KCPrerequisite]` | **新增 (覆盖同名)** | 结构化,Line A 填 |
| `common_mistakes: list[str]` | **保留** | 旧字段不破坏 |
| `common_mistakes_v2: list[CommonMistake]` | **新增** | 带 bug_rule_id |
| `cognitive_dimension` | **新增** | KLI 5 分类 |
| `derivation_steps` | **新增** | 理工偏 |
| `last_practiced_at / mastery_score / srs_state` | **新增(留接口)** | 一期不更新 |
| `viewpoints / counter_arguments / classical_quotes` | **新增(文科留位)** | 一期不写 |

### Migration 策略(零数据搬迁)

`wiki_kcs` 表用 `data_json TEXT` 整存,无需 ALTER TABLE。
`KC.model_validator(mode="before")` 在反序列化时自动检测老 `prerequisites: list[str]`,搬到 `prerequisites_raw`。
下次 `save_kc` 写回时自然完成迁移。

---

## 11. 三线产物详解

### Line A: prereq ETL (commit 59242ca)

**入口**:
```bash
cd D:/fox-say/backend
uv run python -m scripts.align_prerequisites --help
```

**算法** (对每个 KC.prerequisites_raw 字符串):
1. embed prereq_name (BGE-M3)
2. embed 同 course 内每个 KC.name
3. cosine 找 max
4. 分流:
   - sim ≥ 0.85 → 自动接受 `source="etl_auto"`
   - 0.60 ≤ sim < 0.85 → qwen3-4b 仲裁 "YES/NO"
   - sim < 0.60 → 标 unaligned

**输出**:
- `data/alignment_reports/<course>_<iso>.json` 统计
- `data/alignment_reports/<course>_needs_review.jsonl` 待人工审核
- 非 dry-run 写回 `KC.prerequisites: list[KCPrerequisite]`

**为什么 dry-run 是默认推荐**:首次跑大概率大量 unaligned,需要人工看 needs_review 文件确认后再写库。

### Line B: 评测脚手架 + 30 题 pilot (commit c7d5b0a)

**入口**:
```bash
cd D:/fox-say/backend
uv run python -m scripts.run_eval --help
# 或
uv run python -m scripts.run_eval --course-id <id> --pilot --mock-foxsay
```

**4 个模块**:
- `generator.py`:DeepSeek 按 8 def / 10 derivation / 5 cross / 4 refusal / 3 ambiguous 分布生成 30 题
- `validator.py`:qwen3-4b 跑 7 条规则自检 (格式/拒答/字数/类型匹配/bloom/citations 数量)
- `judge.py`:qwen3.5-9b Faithfulness 0-3 打分
- `runner.py`:串起来,生成 markdown 报告到 `eval_reports/<course>_<iso>.md`

**性能预估**:
- 单次 qwen3-4b 调用 ~3s
- 单次 qwen3.5-9b 调用 ~10-15s (reasoning)
- 200 题完整 baseline ≈ 30-60 min

**已知 warning**:`eval/schemas.py:75,84` 用了 `datetime.utcnow()`,Python 3.12 deprecation,**非阻塞**,可改 `datetime.now(datetime.UTC)`。

### Line C: 知识图谱可视化 (commit d69a0f2)

**入口**:
- 后端 endpoint: `GET /courses/{course_id}/knowledge-graph` → `KnowledgeGraphResponse`
- 前端 tab: 课程详情页 → "知识图谱" tab

**渲染**:
- React Flow 节点 + @dagrejs/dagre LR 布局
- 颜色:high=#ef4444 / medium=#f59e0b (foxAmber) / low=#94a3b8
- 节点点击 → console.log + alert (占位,Drawer 待 P2)

**边生成逻辑**(两条路径,新结构优先):
```python
# 路径 1: 优先读 KC.prerequisites (KCPrerequisite 对象列表)
for prereq in kc.prerequisites:
    edge = KGEdge(source=prereq.prerequisite_kc_id, target=kc.id, ...)
    
# 路径 2: fallback KC.prerequisites_raw (字符串,模糊搜索)
for prereq_name in kc.prerequisites_raw:
    candidate = store.search_kcs_by_name(course_id, prereq_name)
    if candidate: edge = KGEdge(..., strength=0.5)
```

---

## 12. 已知 Bug / Tech Debt / 未完成项

### 12.1 真的 Bug(运行时影响)

- **CRAG 阈值失效** (commit 1bb4dba 已修复前):当 `KC.prerequisites` 全是空(冷启动期),`follow_prerequisite` 静默返回空列表。已加 prereq_raw fallback。
- **DSML 防御**:DeepSeek V4 Flash 会输出 `<|DSML|...|>` 假装 tool_call,前后端 strip 一次(详见 `backend/app/services/agent.py`)。

### 12.2 Tech Debt(非阻塞但建议清理)

| 项 | 严重度 | 怎么修 |
|---|---|---|
| `datetime.utcnow()` deprecation | 🟡 低 | 改 `datetime.now(datetime.UTC)`,2 处 |
| 旧 `crag.py` 老 RAG 路径仍存在 | 🟡 中 | agent.py 已替代,删 `crag.py` + `app/api/chat.py` 的非 stream endpoint |
| 旧 `skeleton.py` LLM 生成路径 | ✅ 已修复 | `generate_skeleton_from_wiki` 已被 pipeline.py 调用,旧 LLM 路径仅作 fallback |
| `search_wiki_layer` 实时 embed 所有 KC | 🟠 高 | 改成 batch embed 预存,每次只算 query(性能瓶颈) |
| `ChapterWiki.overview` 是空字符串 | ✅ 已修复 | wiki_builder 新增 CourseSummarizer + summary/regenerate API |
| `requirements` / CourseIndex `concept_totals` 是占位 | 🟢 低 | 数据真起来后填 |
| 前端 `CitationCard` 不跳原文 | ✅ 已修复 | source-preview endpoint + CitationCard 浮动预览已实现 |
| 前端 KG tab `nodes` 颜色不接 mastery | 🟡 中 | 需学情数据接入 |
| `networkx` 在 pyproject.toml 但 0 处 import | 🟡 中 | 违反 HEC-7,应从依赖中移除 |
| `mineru.py` 静默吞错 | ✅ 已修复 | 改为返回 (content, error) tuple,pipeline.py 检查 error 字段 |

### 12.3 Pre-existing untracked 文件

`scripts/qa_visual_check.py` — playwright 真实交互验证脚本(已 commit)。
`scripts/inspect_db.py` / `scripts/inspect_wiki.py` / `scripts/check_chapter_wikis.py` — 调试用脚本(未 commit)。
如果有新的 pre-existing untracked 出现,**用 git status -s 检查,审慎处理**(stash pop 时容易冲突)。

---

## 13. 已知未完成项 / 下阶段 Roadmap

### 13.1 必须做(让脚手架真正活起来)

1. **找一份《线性代数》PPT/PDF** — 上传 → 触发 7 步 pipeline → 看 KC 是否真被抽出来
2. **跑 prereq ETL dry-run** → 看 alignment 报告 → 决定 threshold 是否要调
3. **跑 30 题 pilot(真调 FoxSay)** → 拿到第一份真实 baseline 分数
4. ~~**修 `ChapterWiki.overview` 空字符串**~~ ✅ 已修复

### 13.2 该做但优先级低

5. Wiki 数据建向量索引(性能优化) — `search_wiki_layer` 实时 embed 所有 KC 是性能瓶颈
6. ~~CitationCard 跳原文~~ ✅ 已修复
7. 补齐 6 阶 Bloom + cognitive_dimension 主流程使用
8. Junyi Academy 数据集冷启动复用(调研建议)
9. 从 `pyproject.toml` 移除未使用的 `networkx` 依赖(违反 HEC-7)
10. 真实材料端到端验证(当前所有"完成"都建立在 mock 测试上)

### 13.3 明确不做(产品边界 §3 决策 1)

- ❌ 诊断 15 题 / 出卷功能
- ❌ 多用户 / 权限 / 协作
- ❌ 课程胶囊分享 / 社区广场
- ❌ 全局日程智能体 / 学生版 Cowork
- ❌ 移动端一期(决策 2)

---

## 14. **踩坑档案 — 必读(防止重蹈覆辙)**

### 14.1 Worktree Base Trap(最痛的坑)

**症状**: `isolation: "worktree"` 启的 sub-agent 报告 "schema 是 89 行" / "找不到 docs/contracts-v1-pr0.md"。

**根因**: Claude Code 的 `Agent + isolation: worktree` 创建 worktree 时**用的是 `refs/remotes/origin/main`,不是当前 HEAD 所在的分支**。

**完整的 5 步踩坑历史** (新 agent 必读,不要再栽):

| 轮次 | 误以为 base 是 | 实际 base 是 | 修复 |
|---|---|---|---|
| 1 | 当前 HEAD | feature-LLM-wiki | 错误归因,误杀 A/B |
| 2 | feature-LLM-wiki | main | update-ref 错对象 |
| 3 | local main | origin/main | worktree 用 remote 不是 local |
| 4 | update-ref origin/main 后 | 真实远端 main(回滚了) | fetch 会还原 update-ref |
| 5 | 推送 PR0 commit 到 origin/main | 远端 = PR0 ✅ | **唯一稳定解** |

**正确做法**:
```bash
# 任何 commit 后,要启 worktree agent 之前:
git fetch origin
git log origin/main..HEAD --oneline  # 看是否有未 push 的 commit
# 如果有:
git push origin <your-branch>:<your-branch>  # 不破坏 origin/main
# 然后再启 agent
```

**预防**:在 sub-agent prompt 里强制加 **STEP 0 base 验证**:
```bash
wc -l <expected_new_schema.py>    # 行数必须 ≥ 预期
ls docs/contracts-v1-pr0.md      # 必须存在
grep -c "<new_class_name>" <file>  # 类必须存在
```
**base 错 → 立即停下报告,绝不自己重做新 schema**(这是大忌,会重复造轮子浪费 30 分钟)。

### 14.2 DeepSeek DSML Bug

DeepSeek V4 Flash 会输出 `<|DSML|...|>` 假装 tool_call,内容是 markup 不是真 tool_calls。处理:
- 后端: strip + 引导 LLM 重答
- 前端: `MarkdownRenderer.tsx` 再 strip 一次
- 已写测试覆盖

### 14.3 Cross-platform 脚本问题

- `bash` shell,Windows
- 路径用 forward slash (`D:/fox-say`)
- Python venv 在 `.venv/` (gitignored)
- `git worktree prune` 偶尔需要手动
- CRLF/LF 警告无害(`warning: in the working copy of '...', LF will be replaced by CRLF`)

### 14.4 Stash Pop 陷阱

stash pop 时如果冲突,git 会把 entry 保留为 "kept" 状态(没真的 pop)。需要:
1. 看冲突标记在哪
2. 手动解
3. `git add <file>` 让 git 认为已解
4. `git stash drop` 才会真的丢掉 entry

---

## 15. 与用户的对话风格(接手后第一件事要掌握)

### 用户画像
- **会编码**(亲自动手 commit)
- **讨厌学术黑话**:"用 demo / 真实场景替代术语"
- **偏好 hardcode / 扎实**:调研给硬核的,实现也追求稳健
- **要 detail**:问 1 个问题得到 7 个细节更开心
- **决策直接**:不喜欢 "看你",给 4 个选项,他会选

### 习惯用的表达
- "我们继续"
- "给我说点人话"
- "你看是要 x 还是 y"
- "如果有什么需要我弄的告诉我"

### 关键默契
- **不让人参与**:用户说过"不需要有人参与,所有人工环节都用 LLM 替代"。所有原本 "人 review" 的环节都改成了 "LLM self-validate"。
- **要有验收标准**:每次 ask 前先想清楚成功条件
- **commit 前自检**:HEC-7 条每个 agent 都要过
- **失败立即报告**:不硬猜,不停下来掩饰

---

## 16. 接手 Agent 第一天建议做的事

按优先级:

1. **读这 5 个文件**(2 小时):
   - `AGENTS.md`
   - `docs/contracts-v1-pr0.md`
   - `docs/architecture.md`
   - 这份 HANDOFF.md 的 §3, §14
   - `memory/claude-worktree-base-trap.md`

2. **跑测试确认环境**(5 分钟):
   ```bash
   cd D:/fox-say/backend && uv run pytest tests/ -v
   ```

3. **起本地服务感受一下**(10 分钟):
   ```bash
   cd D:/fox-say/backend && uv run uvicorn app.main:app --reload
   cd D:/fox-say/frontend && npm run dev
   # 浏览器:http://localhost:5173
   ```

4. **询问用户"接下来做什么"**(0 分钟):
   - 优先级最高:**找真实《线性代数》材料喂 pipeline**
   - 次优先:**修 `ChapterWiki.overview` 空字符串**
   - 三选一,等用户拍板

---

## 17. 紧急联系

如果遇到"我想改 schema 但发现三线下游会断",读:
- `docs/contracts-v1-pr0.md` 字段语义 + 修改流程
- §10 PR0 详情
- 询问用户,因为 contract 改动需要 PR review

如果遇到"为什么我的 agent 报 schema 是 89 行",读:
- §14.1 Worktree Base Trap
- 立即 `git push` 把新 commit 推上去再启 agent

如果遇到"评测分数莫名其妙",读:
- §9 模型配置
- §11 Line B 章节
- 可能:DeepSeek 自我偏好 / Qwen judge 不一致 / threshold 没调

如果遇到"图谱节点是空的",读:
- §12.2 Tech Debt `ChapterWiki.overview` 空字符串 + `search_wiki_layer` 实时 embed
- 冷启动期 KC 为空是预期,需要先上传真实材料

---

## 18. 用户级 Memory(跨 session 保留)

在 `C:/Users/WPP_JKW/.claude/projects/D--fox-say/memory/`:

- `MEMORY.md` — 索引
- `debugging-sop.md` — explore→plan→ask→implement→verify→diagnose→summarize 流程
- `claude-worktree-base-trap.md` — Worktree base trap 完整描述 + 修复方法

**新学到的踩坑应该写进去**,这是项目级知识资产。

---

## 附录 A: 跑一个最简任务的完整命令清单

**场景**:用户上传一份《线性代数》第 1 章 PDF,你想看 wiki 是否真的建出来。

```bash
# 1. 起后端
cd D:/fox-say/backend
uv run uvicorn app.main:app --reload

# 2. 另一个 shell,起前端
cd D:/fox-say/frontend
npm run dev

# 3. 浏览器 http://localhost:5173
# 4. 创建课程"线性代数"(手动)
# 5. 上传 PDF,等 SSE 推 skeleton_ready 事件
# 6. 查看浏览器 Network tab,看 /courses/<id>/knowledge-graph 返回
# 7. 切换到"知识图谱" tab 看 reactflow 渲染
```

如果第 6 步返回空 nodes: `KC` 还没生成,可能是 pipeline 失败。看后端 log。

---

## 附录 B: 加新 LLM 模型的 checklist

如果用户想加第 6 个模型(比如 GPT-5 当 Judge):

1. `app/core/config.py` 加新字段 `xxx_model_name`
2. `.env` 跟 `examples/env.example` 加默认值
3. `backend/tests/test_pr0_contracts.py` 加默认值断言
4. (可选) `docs/contracts-v1-pr0.md` 更新"模型分工"表
5. **不写**:不要改 `app/services/agent.py` 默认走这个模型 — 那是另一件事

---

**这份文档到此为止。接手后有任何歧义,先看 §16 "第一天建议做的事",再问用户。**
