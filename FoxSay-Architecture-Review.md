# FoxSay 项目架构深度评估

> 评估日期：2026-06
> 评估范围：全项目（backend / frontend / infra / docs）
> 视角：使用者 + 架构师双视角
> 基线文档：`AGENTS.md` / `docs/architecture.md` / `docs/gap-analysis.md` / `docs/refactor-plan-2026-06.md`

---

## 目录

1. [使用者视角](#一从一个使用者的角度看)
2. [架构师视角](#二从一个架构师的角度看)
3. [关键架构指标](#三关键架构指标总结)
4. [后续方向与优先级](#四如果要继续做应该往哪些方向加强)
5. [附录：模块清单](#附录模块清单)

---

## 一、从一个使用者的角度看

### 1.1 目前能做什么（已完成且可用）

| 功能 | 体验 |
|------|------|
| 创建课程（手动 + CSV/Excel 导入） | ✅ 完整可用，有考试倒计时 |
| 上传材料（PDF/PPT/TXT）并异步处理 | ✅ 有流水线步骤可视化 |
| 课程内问答（带引用、边界控制） | ✅ CRAG 三档阈值工作正常 |
| 复习计划生成 | ✅ LLM 生成 + 权重 fallback |
| /btw 插话（备考模式下） | ✅ 可中断并返回主线 |
| 聊天会话管理 | ✅ 多会话、历史持久化 |
| 骨架图查看 | ⚠️ 静态列表，非交互式导图 |
| 日常/备考模式切换 | ✅ tab 排布随模式变化 |

### 1.2 用户会感到缺失/不满的地方

**1. 第一印象约等于零。** 打开应用就是一个空书架和一只 🦊 emoji。没有分步引导，没有人设对话，没有所谓"贱贱的小狐狸"。对比 PRD 描述的"你来了。期末了？"第一屏，当前体验是 **0%**。

**2. "第一个惊喜"不存在。** PRD 的灵魂——材料处理后狐狸主动跳出来说"我大概看完了。这门课你最薄的地方好像是第三章"——没有实现。用户需要自己手动点到骨架 tab 看一个静态文本列表。主动推送（`push_event`）后端已发出 SSE 事件，但前端没有消费这些事件。

**3. 骨架图不可交互。** 点击章节只展开/折叠。虽然骨架 tab 有 `onConceptClick` 回调可以跳转到问答，但概念节点本身不可点击——只能看到概念名称列表。

**4. 备考模式是"一张纸"而非"陪伴"。** PRD 描述的逐日陪伴复习（"今天该复习第三章了，准备好了吗？"）、进度跟踪、主动提醒——这些都没有。当前就是生成一份计划给你看，然后你自己对着复习。

**5. 没有闪念胶囊（零摩擦捕获）。** PRD 要求的"先扔进来，系统异步归位"完全没有。

**6. 错误体验差。** 上传失败、LLM 错误、网络断开时，用户看到的都是通用错误信息，没有狐狸性格化的文案。

**7. 不支持图片上传、不支持拖拽上传、没有 OCR。** 对理工科同学来说，手写笔记拍照上传是基本需求——当前不支持。

### 1.3 用户视角评分

| 维度 | 得分 | 说明 |
|------|------|------|
| 核心问答质量 | ⭐⭐⭐⭐ | CRAG + 引用做得扎实 |
| 材料处理能力 | ⭐⭐⭐ | PDF/PPT/TXT 可处理，但无层级、无公式、无图片 |
| 学习体验设计 | ⭐⭐ | 功能骨架在，但缺少引导、惊喜、陪伴感 |
| 人格表达 | ⭐ | 几个 emoji，文案偏通用 |
| 备考体验 | ⭐⭐ | 计划能生成，但没有陪伴执行 |

---

## 二、从一个架构师的角度看

### 2.1 架构全景

```
Frontend (Vite + React + TS + Tailwind)
    │  SSE (chat streaming) + REST (CRUD)
    ▼
FastAPI Backend
    ├── api/         路由层（8 个 router）
    ├── services/    业务逻辑（16 个模块）
    ├── schemas/     Pydantic 模型
    ├── db/          SQLite 存储
    └── core/        配置

Infra 层:
    ├── Qdrant       向量存储（仅被 crag.py 使用）
    ├── SQLite       关系数据 + Wiki 结构
    └── Docker Compose 部署
```

### 2.2 做得好的地方

**1. HEC 工程约束体系是真正的资产。** 7 条硬约束（错误必须可见、改动必须 commit、spec 不自吹、不许过度工程、不许杜撰、schema 显式、依赖必用）是从一次失败的 agent 狂奔中提炼的教训，每条都有明确的可验证性。这在个人项目中非常罕见。

**2. DMAP + Merkle Tree 增量架构设计优雅。**

- `dmap.py` 把 Docling 的结构化解析结果变成文档结构图，支持章节/小节层级、跨节引用提取（中文章序 `第一章` / `第3章` / `第十一章` 等）
- `merkle.py` 用 Merkle Tree 对 DMAP 做内容哈希，`diff_merkle_trees` 精确识别变化的节点
- 增量构建时先 invalidate 旧 KC 再 save 新的——顺序逻辑正确

**3. Wiki Builder 四阶段 Pipeline 设计合理。**

- Supervisor → Workers（LangGraph Send 并发派发）→ Reducer（去重合并）→ Reviewer（质量审查 + 最多 1 次打回）
- LangGraph 真正在代码中被使用（`StateGraph` + `Send`），不是依赖僵尸
- KC ID 使用 `uuid5` 确定性生成，天然去重

**4. Agent + 7 工具集设计清晰。**

- ReAct 循环 max 3 轮，有 DSML 防御层（处理 DeepSeek 模型输出非法 tool-call 语法的问题）
- 工具职责明确：`search_wiki`（三层混合检索）、`get_concept`、`get_chapter_outline`、`follow_prerequisite`、`get_source_content`、`get_course_map`、`get_review_plan`
- 错误时 SSE 推 `{type: "error", message: "..."}`，符合 HEC-1

**5. 测试覆盖有针对性。** CRAG 三档阈值 6 个 test case 覆盖完整；拒答路径、空 embedding、0 结果都有覆盖；`course_id` 隔离有验证。

**6. Schema 显式隔离。** 每个模型都带 `course_id`，杜绝跨课程数据污染。`get_concept` 和 `get_chapter_outline` 工具函数会校验 `kc.course_id != course_id`。

### 2.3 架构层面的关键问题

#### 🔴 问题 1：Wiki 检索没有向量索引——性能天花板

这是当前架构最大的性能隐患。`search_wiki_layer` 在 `retrieval.py` 中每次查询都会：

```python
for cw in chapter_wikis:           # 对每个章节
    emb = embed_texts([text])[0]    # 调一次 embedding API
    score = _cosine_similarity(...)
for kc in kcs:                      # 对每个 KC
    emb = embed_texts([text])[0]    # 又调一次 embedding API
    score = _cosine_similarity(...)
```

这意味着：一门有 15 个章节、200 个 KC 的课程，每次用户提问会调用 **215 次 embedding API**（加上 Qdrant 那层），然后做 Python 循环内的 cosine similarity。Qdrant 被完全绕过——它只被老 `crag.py` 路径使用。

**正确的做法**：Wiki 构建完成后，把 KC 和 ChapterWiki 文本批量 embedding 存入 Qdrant（与原始材料 chunks 同 collection 或独立 collection），检索时一次向量搜索覆盖所有层。

**影响面**：`backend/app/services/retrieval.py:search_wiki_layer`、`backend/app/services/wiki_builder.py:_persist_to_store`

#### 🔴 问题 2：双重 RAG 路径并存，互不通信

```
路径 A: POST /chat (crag.py)           → Qdrant 向量检索 → LLM 回答
路径 B: POST /chat/stream (agent.py)   → Wiki 三层检索  → ReAct Agent → LLM 回答
```

- 路径 A 是完全基于 Qdrant 的老 RAG，不知道 Wiki/KC 的存在
- 路径 B 是 Wiki-First 的新 Agent，但 Wiki 数据没有向量索引
- 前端只用路径 B（`/chat/stream`），路径 A 是遗留代码但没有被清理
- 两条路径的检索结果互不增强——Qdrant 里的 chunks 和 Wiki 里的 KCs 是两个平行宇宙

**影响面**：`backend/app/api/chat.py`（两个 endpoint）、`backend/app/services/crag.py`、`backend/app/services/agent.py`

#### 🟡 问题 3：骨架生成双路径，Wiki 路径未被主流程使用

```python
# pipeline.py 主流程实际调用的：
asyncio.create_task(_generate_and_store_skeleton(course_id, store))
    └── generate_skeleton(course_id, title, combined_text)
         └── _llm_generate(...)           # LLM 从 raw text[:8000] 生成

# skeleton.py 中存在但从未被调用的：
generate_skeleton_from_wiki(course_id, store)  # 从 Wiki 数据本地派生
```

`generate_skeleton_from_wiki` 是 Wiki 构建完成后最合理的骨架来源（纯本地，不调 LLM，数据来自结构化的 `CourseIndex + ChapterWiki`），但它**从未被调用**。Pipeline 仍走老路径：LLM 看 8000 字符 raw text 生成骨架。

**影响面**：`backend/app/services/pipeline.py:_generate_and_store_skeleton`、`backend/app/services/skeleton.py:generate_skeleton_from_wiki`

#### 🟡 问题 4：Pipeline 单体函数承载过多职责

`process_material` 函数（`pipeline.py:33-170`）负责 7 个步骤的编排，混杂了解析、DMAP、Wiki、chunking、embedding、Qdrant、骨架生成，加上多层 try/except 和 degraded fallback 逻辑。任何一步的修改都需要理解整个 150 行的函数。

**建议**：拆成独立的 stage runner 函数，每个 stage 独立可测、独立可重试。

#### 🟡 问题 5：前端没有消费异步事件

后端 `push_event(course_id, "material_processed", ...)` 和 `push_event(course_id, "skeleton_ready", ...)` 已经在发 SSE 事件，但前端 `useMaterials` 和 `useSkeleton` 是纯轮询/手动刷新模式。用户上传材料后看不到处理进度，也不知道何时骨架可用——除非手动切换 tab。

**影响面**：`backend/app/api/events.py`、`frontend/src/features/course/useMaterials.ts`、`frontend/src/features/course/useSkeleton.ts`

#### 🟡 问题 6：测试覆盖严重不均

```
test_crag.py          ✅ 6 个 test case，覆盖完整
test_retrieval        ✅ (在 test_crag.py 中)
test_courses.py       需验证
test_materials.py     需验证
test_skeleton.py      需验证
test_agent_loop.py    需验证
test_query_tools.py   需验证
test_dmap.py          需验证
test_merkle.py        需验证
test_wiki_builder.py  需验证
test_review.py        需验证
```

Wiki Builder（最复杂的组件，约 400 行的 `wiki_builder.py` + `dmap.py` + `merkle.py`）的测试覆盖情况不明。如果这些测试文件只是占位/stub，风险很高。

#### 🟡 问题 7：Docling 集成脆弱

`parsing_docling.py` 中的 `parse_pdf_docling` 在 `except Exception` 时返回空列表 → pipeline 退化为一章一段的平面 DMAP → Wiki Builder 在一段文本上运行 4 阶段 pipeline → 低质量输出。应该有明确的日志告警和用户提示。

---

## 三、关键架构指标总结

| 指标 | 评分 | 说明 |
|------|------|------|
| 模块边界 | ⭐⭐⭐⭐ | api/schemas/services/db/core 清晰 |
| 数据隔离 | ⭐⭐⭐⭐⭐ | 严格 course_id 分区，HEC-6 守护 |
| 增量更新 | ⭐⭐⭐⭐ | DMAP + Merkle diff 设计优雅，顺序正确 |
| 检索性能 | ⭐⭐ | Wiki 无向量索引，O(N) embedding per query |
| 错误可见性 | ⭐⭐⭐⭐ | HEC-1 驱动，SSE 推送 error 事件 |
| 测试覆盖 | ⭐⭐⭐ | CRAG 覆盖好，Wiki/Agent 情况不明 |
| 代码一致性 | ⭐⭐⭐ | 双重 RAG 路径并存，有遗留代码 |
| 前端-后端对齐 | ⭐⭐⭐ | API 对齐但缺少实时事件消费 |
| 产品完成度 | ⭐⭐ | 约 46%（引用 gap-analysis 自评） |

---

## 四、如果要继续做，应该往哪些方向加强？

### 🔴 P0 — 架构健康（现在就该修）

**1. 给 Wiki 数据建向量索引。**

把 KC 和 ChapterWiki 的文本在 Wiki 构建完成时批量 embedding 存入 Qdrant。`search_wiki_layer` 改为一次向量搜索覆盖三层，消除逐条 embedding 的性能问题。这是影响每个用户每次提问的性能瓶颈。

- 涉及文件：`backend/app/services/wiki_builder.py:_persist_to_store`（添加 embedding + Qdrant 写入步骤）、`backend/app/services/retrieval.py:search_wiki_layer`（改为单次 Qdrant 搜索 + layer 过滤）
- 预估改动量：约 80-120 行

**2. 统一检索路径。**

删除或归档 `crag.py` 遗留路径（`POST /chat`），将 CRAG 门控逻辑（三档阈值 0.72/0.55）整合进 agent 工具的 `search_wiki` 中。确保只存在一套检索体系。

- 涉及文件：`backend/app/api/chat.py`、`backend/app/services/crag.py`、`backend/app/services/agent.py:_execute_tool`
- 预估改动量：约 50 行删除 + 30 行整合

**3. 用 `generate_skeleton_from_wiki` 替换 LLM 骨架生成。**

Wiki 构建完成后，`CourseIndex + ChapterWiki` 已经有足够结构化的数据来派生骨架——不需要再调一次 LLM 看 raw text。`_generate_and_store_skeleton` 应该优先走 Wiki 路径。

- 涉及文件：`backend/app/services/pipeline.py:_generate_and_store_skeleton`
- 预估改动量：约 20 行

**4. 补充 Wiki/Agent/DMAP 的核心测试。**

至少要覆盖：DMAP 构建正确性、Merkle diff 正确性、Wiki Builder 四阶段的 mock LLM 测试、agent 工具路由测试。参考 `test_crag.py` 的 mock 模式。

- 涉及文件：`backend/tests/test_dmap.py`、`backend/tests/test_merkle.py`、`backend/tests/test_wiki_builder.py`、`backend/tests/test_agent_loop.py`、`backend/tests/test_query_tools.py`
- 预估改动量：每个 test 文件约 50-100 行

---

### 🟡 P1 — 产品体验闭环

**5. 前端消费 SSE 事件做实时推送。**

材料处理完成 / 骨架就绪时，狐狸主动弹出消息（"我读完了！来看看我发现了什么 👀"）。这是 PRD "第一个惊喜"的最小可行版本。

- 涉及文件：`frontend/src/features/course/useMaterials.ts`（订阅 `material_processed` 事件）、`frontend/src/features/course/useSkeleton.ts`（订阅 `skeleton_ready` 事件）、新增 `useCourseEvents` hook
- 预估改动量：约 100-150 行

**6. 骨架图交互化。**

概念节点可点击跳转问答（`onConceptClick` 已存在但需要视觉可点击提示），章节节点显示完成度/重要性颜色（importance badge 已有但不够醒目）。

- 涉及文件：`frontend/src/features/course/SkeletonTree.tsx`
- 预估改动量：约 30-50 行

**7. 备考模式执行引擎。**

不是生成计划就结束——需要状态机跟踪每日进度、当前复习到哪个步骤、支持"继续复习"和"跳过"操作。`review_session` 表已经建好，`review_session.py` API 也已存在，但前端 `ReviewTab` 没有使用这些能力。

- 涉及文件：`frontend/src/features/course/ReviewTab.tsx`、`frontend/src/features/course/ReviewPlanView.tsx`
- 预估改动量：约 100-200 行

**8. 错误文案人格化。**

`fox-copy.ts` 已有框架，补全所有错误场景的狐狸语气文案（上传失败、LLM 超时、网络断开、材料格式不支持、超出课程范围等）。

- 涉及文件：`frontend/src/shared/fox-copy.ts`
- 预估改动量：约 40 行

---

### 🟢 P2 — 能力增强

**9. 图片上传 + OCR。** 理工科同学需要拍照上传手写笔记。可以用 DeepSeek 的视觉能力或 Tesseract。需要新增 `kind: "image"` 的解析路径。

**10. 闪念胶囊。** 一个始终可见的输入条，用户可以随时扔文字进去，系统异步归位到对应课程。MVP 版可以先是全局输入框 + 自动选择最近活跃课程。

**11. 拖拽上传 + 粘贴上传。** 降低材料上传的摩擦。`MaterialUpload.tsx` 添加拖拽区域和 paste 事件监听。

**12. 考试倒计时主动提醒。** 后端定时检查，考前 7 天/3 天/1 天触发狐狸提醒（可通过 `push_event` 机制扩展）。

---

### 一张图总结：从现状到目标的路径

```
当前状态                              目标状态
┌──────────────┐                    ┌──────────────────┐
│ 功能骨架      │  ──P0 架构健康──▶  │ 稳定高效的引擎    │
│ 双重 RAG      │   · Wiki 向量索引  │ 单一检索体系      │
│ 无向量索引    │   · 统一检索路径   │ 骨架从 Wiki 派生  │
│ 遗留代码      │   · 补测试        │ 核心路径有测试    │
└──────────────┘                    └──────────────────┘
       │                                     │
       └────── P1 体验闭环 ─────────▶  ┌──────────────────┐
              · SSE 实时推送           │ 有性格的产品      │
              · 骨架可交互             │ 主动推送惊喜      │
              · 备考执行引擎           │ 交互式骨架        │
              · 人格化错误文案         │ 陪伴式备考        │
                                       └──────────────────┘
                                              │
                                              └── P2 能力增强 ──▶
                                                  图片OCR / 闪念胶囊
                                                  拖拽上传 / 考前提醒
```

**核心判断**：当前项目的架构基础（DMAP、Wiki Builder、Agent、Merkle）打得不错，工程纪律（HEC）相当好。最大的短板不在"缺少什么新功能"，而在于 **Wiki 检索的性能路径根本没走通**——架构设计是对的，但实现上 Wiki 数据没有向量索引，导致每次查询都是 O(N) embedding 调用。修好这个，然后让前端消费后端已经发出的 SSE 事件实现"第一个惊喜"，产品就能从 46% 跳到 65%+。

---

## 附录：模块清单

### Backend 模块

| 模块 | 路径 | 行数（近似） | 职责 |
|------|------|-------------|------|
| `main.py` | `backend/app/main.py` | ~40 | FastAPI app 组装、lifespan、CORS |
| `chat.py` (api) | `backend/app/api/chat.py` | ~140 | 两个 chat endpoint（legacy + stream）、会话管理、历史 |
| `courses.py` (api) | `backend/app/api/courses.py` | - | 课程 CRUD、课程表导入 |
| `materials.py` (api) | `backend/app/api/materials.py` | - | 材料上传、状态查询 |
| `skeleton.py` (api) | `backend/app/api/skeleton.py` | - | 骨架查询 |
| `review.py` (api) | `backend/app/api/review.py` | - | 复习计划生成 |
| `review_session.py` (api) | `backend/app/api/review_session.py` | - | 复习会话状态机 |
| `events.py` (api) | `backend/app/api/events.py` | - | SSE 事件推送（material_processed / skeleton_ready） |
| `settings.py` (api) | `backend/app/api/settings.py` | - | 用户设置 |
| `config.py` (core) | `backend/app/core/config.py` | - | 环境变量读取 |
| `sqlite_store.py` (db) | `backend/app/db/sqlite_store.py` | ~660 | SQLite 数据访问层（12+ 表） |
| `deps.py` (db) | `backend/app/db/deps.py` | - | FastAPI Depends |
| `foxsay.py` (schemas) | `backend/app/schemas/foxsay.py` | ~230 | Pydantic 模型全集 |
| `agent.py` | `backend/app/services/agent.py` | ~320 | Agent ReAct 主循环 + 7 工具定义 + DSML 防御 |
| `wiki_builder.py` | `backend/app/services/wiki_builder.py` | ~400 | 4 阶段 Wiki 构建（LangGraph） |
| `dmap.py` | `backend/app/services/dmap.py` | ~220 | DMAP 构建 + 跨节引用提取 + ID 查找 |
| `merkle.py` | `backend/app/services/merkle.py` | ~80 | Merkle Tree 计算 + diff |
| `crag.py` | `backend/app/services/crag.py` | ~120 | 老 RAG 问答（CRAG 门控） |
| `retrieval.py` | `backend/app/services/retrieval.py` | ~160 | Qdrant 向量检索 + search_wiki_layer |
| `skeleton.py` | `backend/app/services/skeleton.py` | ~180 | 骨架生成（LLM + fallback + from_wiki） |
| `query_tools.py` | `backend/app/services/query_tools.py` | ~130 | 6 个 Wiki 查询工具实现 |
| `review.py` | `backend/app/services/review.py` | ~140 | 复习计划生成 |
| `pipeline.py` | `backend/app/services/pipeline.py` | ~180 | 材料处理主流水线 |
| `parsing.py` | `backend/app/services/parsing.py` | ~70 | PDF（pdfplumber）/ PPTX / TXT 解析 |
| `parsing_docling.py` | `backend/app/services/parsing_docling.py` | ~90 | Docling 结构化 PDF 解析 |
| `chunking.py` | `backend/app/services/chunking.py` | - | 文本分块 |
| `embedding.py` | `backend/app/services/embedding.py` | - | embedding API 调用 |
| `vectorstore.py` | `backend/app/services/vectorstore.py` | - | Qdrant 客户端封装 |
| `guard.py` | `backend/app/services/guard.py` | - | 内容安全守卫 |
| `timetable.py` | `backend/app/services/timetable.py` | - | CSV/Excel 课程表解析 |

### Frontend 模块

| 模块 | 路径 | 职责 |
|------|------|------|
| `BookshelfPage.tsx` | `frontend/src/features/bookshelf/` | 书架首页 |
| `CourseCard.tsx` | `frontend/src/features/bookshelf/` | 课程卡片（含倒计时） |
| `CreateCourseModal.tsx` | `frontend/src/features/bookshelf/` | 创建课程弹窗 |
| `ImportTimetableModal.tsx` | `frontend/src/features/bookshelf/` | 导入课程表弹窗 |
| `useCourses.ts` | `frontend/src/features/bookshelf/` | 课程列表 hook |
| `CourseDetailPage.tsx` | `frontend/src/features/course/` | 课程详情页（tab 路由） |
| `ChatTab.tsx` / `useChat.ts` | `frontend/src/features/course/` | 问答 tab + SSE 流式处理 |
| `MaterialsTab.tsx` / `useMaterials.ts` | `frontend/src/features/course/` | 材料管理 |
| `SkeletonTab.tsx` / `SkeletonTree.tsx` / `useSkeleton.ts` | `frontend/src/features/course/` | 骨架图 |
| `ReviewTab.tsx` / `ReviewPlanView.tsx` / `useReview.ts` | `frontend/src/features/course/` | 备考模式 |
| `BtwInput.tsx` | `frontend/src/features/course/` | /btw 插话 |
| `ToolCallIndicator.tsx` | `frontend/src/features/course/` | 工具调用状态指示 |
| `CitationCard.tsx` | `frontend/src/features/course/` | 引用卡片 |
| `MarkdownRenderer.tsx` | `frontend/src/features/course/` | Markdown 渲染 + DSML 清理 |
| `OnboardingPage.tsx` | `frontend/src/features/onboarding/` | 引导页（骨架） |
| `api.ts` | `frontend/src/shared/` | HTTP 请求封装 |
| `fox-copy.ts` | `frontend/src/shared/` | 狐狸语气文案 |
| `types.ts` | `frontend/src/shared/` | 共享类型定义 |

### 基础设施

| 组件 | 路径 | 说明 |
|------|------|------|
| Docker Compose | `infra/docker-compose.yml` | Qdrant + Backend + Frontend 三服务 |
| Qdrant | `infra/qdrant/` | 向量数据库，端口 6333 |
| Backend Dockerfile | `backend/Dockerfile` | FastAPI 容器化 |
| Frontend Dockerfile | `frontend/Dockerfile` + `nginx.conf` | React SPA + Nginx 反向代理 |

### 文档

| 文档 | 路径 | 说明 |
|------|------|------|
| `AGENTS.md` | 根目录 | 项目最高优先级工程约束（含 7 条 HEC） |
| `architecture.md` | `docs/architecture.md` | 架构总览 |
| `refactor-plan-2026-06.md` | `docs/refactor-plan-2026-06.md` | 5 阶段重构计划 + 禁止模式清单 |
| `gap-analysis.md` | `docs/gap-analysis.md` | 当前与 PRD 差距评估（约 46% 完成度） |
| `crag-policy.md` | `docs/crag-policy.md` | CRAG 门控策略 |
| `product-boundaries.md` | `docs/product-boundaries.md` | 产品边界定义 |
| `roadmap-to-prd.md` | `docs/roadmap-to-prd.md` | PRD 路线图 |
| `wiki-first-rampage.md` | `docs/postmortem/` | Wiki-First 重构复盘 |
