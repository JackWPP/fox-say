# FoxSay PRD 达标路线图

> ⚠️ **已过时 (2026-06)**: 本文档描述的"三元组 + Neo4j + LightRAG 双层检索"路线已被实际架构"DMAP + KC + ChapterWiki + LangGraph + Qdrant 三层检索"替代。保留作为历史参考，不要照做。见 `docs/architecture.md` 获取当前架构。

> 基准日期：2026-05-10
> 基准状态：综合完成度约 46%，详见 `docs/gap-analysis.md`

---

## 当前基线

已能运行的功能：课程 CRUD、材料上传（PDF/PPT/文本）、异步处理 pipeline、Qdrant 向量检索、CRAG 三档问答、骨架图生成、复习计划生成、/btw 插话、Docker Compose 部署。

核心缺口：知识图谱空转、产品体验无人设、材料处理缺深度、陪伴复习无状态。

---

## Phase 0：基础正确性收口 — 已完成

审查报告发现的 3 个 HIGH + 3 个 MEDIUM 问题已全部修复。

| 问题 | 修复内容 | 验证 |
|------|---------|------|
| 上传目录定位错误 + 数据泄露 | `upload_root` 移入 Settings，`.gitignore` 补 `uploads/`，Docker 环境变量，`git rm --cached` | ✅ pytest 40/40 |
| Qdrant point ID 覆盖 | UUID 替代顺序整数，`delete_by_material` 先删旧点再 upsert | ✅ |
| PPT/图片错误降级 | 不支持类型直接 415，移除二进制 UTF-8 降级，课程"全 failed"不标 ready | ✅ |
| 知识图谱/聊天不持久化 | 新增 `knowledge_graphs`/`chat_messages` 表，`kg.save(store)`，chat history API，前端加载历史 | ✅ |
| Citation 不强制 | `_ensure_citations` 后处理兜底 | ✅ |
| 无 Excel 导入 | openpyxl + `parse_excel`，按扩展名路由 | ✅ |

---

## Phase 1：知识图谱重建

> 这是 PRD 架构的核心差异化层，也是从"RAG 问答工具"升级到"知识网络驱动 Copilot"的关键。

### 目标

让知识图谱真正从材料中构建出来，并在问答和复习中被利用。

### 1.1 独立知识抽取 pipeline

**现状**：骨架图生成时顺手塞几个概念名进图，不是知识抽取。

**目标**：每个 chunk 经过 LLM 抽取结构化三元组 `(主体, 关系, 客体)`，独立于骨架图 pipeline。

**工作项**：

1. 新建 `backend/app/services/knowledge_extraction.py`
   - 设计三元组 Schema prompt（参考 PRD "Schema-based Prompting + CoT"）
   - 关系类型至少覆盖：`contains`（章节包含概念）、`depends_on`（概念依赖）、`has_prerequisite`（先修关系）、`relates_to`（概念相关）、`has_application`（应用场景）
   - 每个三元组携带来源信息：`material_id`、`chunk_index`、源文本片段
   - LLM 调用 + JSON 解析 + 校验

2. 集成到 `backend/app/services/pipeline.py`
   - 在 embedding/storing 步骤之后新增 `knowledge_extraction` 步骤
   - 对每个 chunk 调用抽取，结果写入 `KnowledgeGraph`
   - 抽取完成后触发图谱持久化

3. 修改 `PIPELINE_STEPS` 添加 `"knowledge_extraction"` 步骤

**涉及文件**：
- 新建 `backend/app/services/knowledge_extraction.py`
- 修改 `backend/app/services/pipeline.py`
- 修改 `backend/app/db/sqlite_store.py`（三元组存储或通过图谱 JSON 间接存储）

**验收标准**：
- 上传一份 PDF，`knowledge_graphs` 表中包含从材料中抽取的三元组数据
- 三元组有来源 chunk 引用
- 抽取失败不阻塞主 pipeline（向量检索仍可用）

### 1.2 图谱检索能力

**现状**：`KnowledgeGraph` 类没有查询方法，问答完全不走图。

**目标**：图谱可被问答和复习消费。

**工作项**：

1. 在 `backend/app/services/knowledge_graph.py` 添加检索方法：
   - `get_neighbors(concept_id, depth=1)` — 获取概念邻居
   - `get_path(from_concept, to_concept)` — 两概念间路径
   - `get_subgraph(concept_ids)` — 按概念集合取子图
   - `search_concepts(query)` — 按关键词搜索概念节点
   - `to_context(subgraph)` — 将子图三元组序列化为 LLM 可理解的文本

2. 在 `backend/app/services/retrieval.py` 集成图检索：
   - 向量检索后，取 top-k chunks 中涉及的 concept_id
   - 用 `get_neighbors` 扩展相关概念
   - 将图上下文（三元组文本）追加到检索结果中
   - 返回结构中增加 `graph_context` 字段

3. 在 `backend/app/services/crag.py` 消费图上下文：
   - `ask()` 中拼接上下文时，将 `graph_context` 追加到 `context_parts`
   - 调整 SYSTEM_PROMPT 说明图上下文的使用方式

**涉及文件**：
- 修改 `backend/app/services/knowledge_graph.py`
- 修改 `backend/app/services/retrieval.py`
- 修改 `backend/app/services/crag.py`

**验收标准**：
- 问答时，如果问题涉及某概念，回答中能引用该概念的关联知识（不只是向量检索的 chunk）
- 图上下文中包含三元组，可溯源到材料

### 1.3 增量合并

**现状**：新材料上传后图谱不更新。

**目标**：新材料上传后，增量抽取三元组并合并到已有图谱。

**工作项**：

1. `pipeline.py` 中，材料处理完成后不只做向量存储，还做知识抽取
2. 抽取结果与已有图谱做去重：相同 (subject, relation, object) 不重复添加
3. 新概念/关系合并后 `kg.save(store)` 持久化
4. 考虑是否需要重新生成骨架图（当图谱发生重大变化时）

**涉及文件**：
- 修改 `backend/app/services/pipeline.py`
- 修改 `backend/app/services/knowledge_graph.py`（添加 `merge` 方法）

**验收标准**：
- 课程先上传材料 A，再上传材料 B，图谱包含两份材料的三元组
- 重新上传同一份材料，不产生重复三元组
- 第二份材料后，骨架图可选择性更新

### 1.4 骨架图从图谱生成

**现状**：骨架图是 LLM 一次性生成的 JSON，图谱是骨架图的副产品。

**目标**：骨架图从图谱结构中派生，而不是反过来。

**工作项**：

1. 修改 `skeleton.py` 的 `_llm_generate`：
   - 不再让 LLM 直接输出 chapters + core_concepts
   - 改为：从图谱取 `core_concepts`（入度最高的节点）、`difficulty_areas`（入度 > 阈值的节点）、`prerequisite_chain`（边列表）
   - LLM 只负责组织这些概念为章节结构，而不是从零生成
2. fallback 路径也改为从图谱派生而非文本分块

**涉及文件**：
- 修改 `backend/app/services/skeleton.py`

**验收标准**：
- 骨架图的 core_concepts 与图谱节点一致
- 多份材料的骨架图反映所有材料的知识结构

---

## Phase 2：产品体验补全

> 让产品从"功能骨架"变成"有灵魂的产品"。

### 2.1 首次引导流程

**目标**：用户第一次打开看到狐狸登场，选择模式，建立第一门课。

**工作项**：

1. 新建 `frontend/src/features/onboarding/OnboardingPage.tsx`
   - 第一屏：狐狸人设台词 + "我要备考" / "日常学习" 选择
   - 第二屏：导入课程表 / 手动创建
   - 第三屏：上传材料 + "没有文件？先告诉我老师讲了什么"文字输入
2. App.tsx 增加路由守卫：首次用户（localStorage 标记）→ OnboardingPage
3. 后端无改动

**涉及文件**：
- 新建 `frontend/src/features/onboarding/OnboardingPage.tsx`
- 修改 `frontend/src/App.tsx`

**验收标准**：
- 首次打开显示引导流程
- 完成引导后跳转到书架页
- 再次打开直接进书架页

### 2.2 人设语气注入

**目标**：所有面向用户的文案替换为"贱贱的小狐狸"语气。

**工作项**：

1. 新建 `frontend/src/shared/fox-copy.ts` — 集中管理人设文案
   - 空书架："你来了。还没有课程？先建一个再说。"
   - 处理中："好，我去消化一下，你先等等。"
   - 骨架图完成："我大概看完了。这门课你最薄的地方好像是第三章，要先从这里开始吗？"
   - 拒答："这个问题超出了[课程名]的范围，我不知道。别想骗我乱说。"
   - 复习模式："期末了？还是还没死心想好好学？"
   - 错误："哎呀，出了点问题……不是我干的。再试一次吧。"
2. 替换各组件中的硬编码文案为 `fox-copy` 引用
3. 后端 CRAG 拒答文案也统一（`crag.py` 的 out_of_scope 回复）

**涉及文件**：
- 新建 `frontend/src/shared/fox-copy.ts`
- 修改各前端组件中的硬编码文案
- 修改 `backend/app/services/crag.py`

**验收标准**：
- 全局文案风格统一，不再有通用助手式文案
- 新增文案位置：空状态、处理中、完成、拒答、错误

### 2.3 骨架图交互化

**目标**：骨架图从静态列表变为可交互的思维导图，点击概念进入问答。

**工作项**：

1. 替换 `SkeletonTree.tsx` 为思维导图组件
   - 评估方案：D3.js force layout / react-flow / vis.js
   - 节点颜色按 importance 区分（high=橙，medium=黄，low=灰）
   - 点击节点：将该概念作为预填问题跳转到 ChatTab
2. 添加"第一个惊喜"推送机制
   - 后端 WebSocket 或 SSE 推送骨架图完成事件
   - 前端接收后弹出狐狸台词 + 骨架图预览

**涉及文件**：
- 重写 `frontend/src/features/course/SkeletonTab.tsx`
- 重写 `frontend/src/features/course/SkeletonTree.tsx`
- 新建 `backend/app/api/events.py`（SSE 端点）
- 修改 `frontend/src/features/course/CourseDetailPage.tsx`

**验收标准**：
- 骨架图以思维导图形式展示
- 点击概念节点跳转到问答，问题预填该概念
- 材料处理完成后前端收到主动推送

### 2.4 模式切换

**目标**：日常学习 / 超级备考两种模式，行为差异可见。

**工作项**：

1. 课程详情页增加模式切换开关
2. 日常模式：默认显示 ChatTab + MaterialsTab
3. 备考模式：默认显示 ReviewTab + 骨架图，ChatTab 样式变化（狐狸语气更紧迫）
4. 考试倒计时 ≤ 7 天时自动建议切换到备考模式

**涉及文件**：
- 修改 `frontend/src/features/course/CourseDetailPage.tsx`
- 修改 `frontend/src/features/course/ChatTab.tsx`
- 修改 `frontend/src/features/bookshelf/CourseCard.tsx`

**验收标准**：
- 用户可手动切换模式
- 考试临近时书架卡片有切换建议
- 两种模式下 tab 默认顺序和狐狸语气不同

---

## Phase 3：材料处理增强

> 让理工科材料也能被正确处理。

### 3.1 Docling 接入

**工作项**：

1. 添加 `docling` 依赖到 `pyproject.toml`
2. 新建 `backend/app/services/parsing_docling.py`：用 Docling 替代 pdfplumber 做结构化解析
3. `parsing.py` 中按配置选择 Docling 或 pdfplumber
4. Docling 输出的层级结构保留到 chunk metadata 中

**涉及文件**：
- 修改 `backend/pyproject.toml`
- 新建 `backend/app/services/parsing_docling.py`
- 修改 `backend/app/services/parsing.py`
- 修改 `backend/app/core/config.py`（添加解析器选择配置）

**验收标准**：
- PDF 解析后 chunk 包含层级信息（章节标题、层级深度）
- Docling 解析失败时 fallback 到 pdfplumber

### 3.2 Marker 接入（LaTeX 公式）

**工作项**：

1. 添加 `marker-pdf` 依赖
2. 新建 `backend/app/services/parsing_marker.py`：用 Marker 做公式还原文档解析
3. 在 pipeline 中检测材料类型或配置，选择 Docling 或 Marker

**涉及文件**：
- 修改 `backend/pyproject.toml`
- 新建 `backend/app/services/parsing_marker.py`
- 修改 `backend/app/services/pipeline.py`

**验收标准**：
- 含 LaTeX 公式的 PDF 解析后公式被保留为文本
- 公式还原准确率需人工验收

### 3.3 图片 OCR（可选）

**工作项**：

1. 添加 OCR 库依赖（PaddleOCR 或 Tesseract + 中文模型）
2. 新建 `backend/app/services/parsing_ocr.py`
3. `parsing.py` 支持 `image` 类型
4. `materials.py` 恢复 image 扩展名

**涉及文件**：
- 修改 `backend/pyproject.toml`
- 新建 `backend/app/services/parsing_ocr.py`
- 修改 `backend/app/services/parsing.py`
- 修改 `backend/app/api/materials.py`

**验收标准**：
- 上传图片文件，OCR 提取文本进入知识库
- 中文识别准确率需人工验收

---

## Phase 4：陪伴复习主线

> 让备考从"看一份计划"变成"被狐狸带着走"。

### 4.1 复习状态机

**目标**：复习有进度，有状态，有推进。

**工作项**：

1. 后端新增 `review_sessions` 表：`course_id, current_day, current_step, status, completed_steps_json`
2. 新增 API：`POST /courses/{id}/review/start`、`POST /courses/{id}/review/advance`、`GET /courses/{id}/review/progress`
3. 每完成一个复习步骤，调用 advance 记录进度
4. 再次进入复习时从上次位置继续

**涉及文件**：
- 修改 `backend/app/db/sqlite_store.py`
- 新建 `backend/app/api/review_session.py`
- 修改 `backend/app/main.py`（注册路由）

**验收标准**：
- 开始复习后，进度持久化
- 关闭页面重新打开，从上次位置继续
- 全部完成后标记为 done

### 4.2 逐步推进体验

**目标**：狐狸带着用户按天、按知识点逐步复习。

**工作项**：

1. 前端 `ReviewTab.tsx` 改为单步视图：
   - 当前只显示"今天的复习内容"，而非整个计划列表
   - 底部："准备好了" / "今天先到这" 按钮
   - 完成后自动推进到下一天
2. 每步开始时狐狸台词："今天来搞定第三章的这几个概念，大约 40 分钟。"
3. 每步完成时狐狸台词："不错，明天继续第四章。"
4. 步骤中可随时 /btw 插话

**涉及文件**：
- 重写 `frontend/src/features/course/ReviewTab.tsx`
- 修改 `frontend/src/features/course/ReviewPlanView.tsx`

**验收标准**：
- 复习界面一次只展示一天内容
- 有明确的推进/完成操作
- 进度跨页面持久化

---

## 阶段依赖关系

```
Phase 0 (已完成)
  ↓
Phase 1 (知识图谱) ← 阻塞其他所有阶段的核心差距
  ├── 1.1 知识抽取 pipeline
  ├── 1.2 图谱检索能力 ← 依赖 1.1
  ├── 1.3 增量合并 ← 依赖 1.1
  └── 1.4 骨架图从图谱生成 ← 依赖 1.1 + 1.3
  ↓
Phase 2 (产品体验) ← 与 Phase 1 部分可并行
  ├── 2.1 首次引导 ← 独立
  ├── 2.2 人设语气 ← 独立
  ├── 2.3 骨架图交互 ← 依赖 1.4（图谱数据要到位才有交互意义）
  └── 2.4 模式切换 ← 独立
  ↓
Phase 3 (材料处理) ← 与 Phase 2 可并行，但图谱增强需要更好的解析
  ├── 3.1 Docling ← 独立
  ├── 3.2 Marker ← 独立
  └── 3.3 图片 OCR ← 独立
  ↓
Phase 4 (陪伴复习) ← 依赖 1.2（图检索）+ 2.4（模式切换）
  ├── 4.1 复习状态机
  └── 4.2 逐步推进体验 ← 依赖 4.1
```

**可并行的组合**：
- Phase 1.1 + Phase 2.1/2.2/2.4 可同时推进
- Phase 3 全部可独立于 Phase 2 推进
- Phase 4 需要等 Phase 1.2 和 2.4 就绪

---

## 完成后预期达成度

| Phase | 完成后综合完成度 | 关键变化 |
|-------|----------------|---------|
| Phase 0（已完成） | 46% | 基础正确性收口 |
| Phase 1 | 60% | 从"RAG 工具"升级为"知识网络驱动 Copilot" |
| Phase 2 | 75% | 从"功能骨架"升级为"有灵魂的产品" |
| Phase 3 | 82% | 理工科材料可用，知识库质量大幅提升 |
| Phase 4 | 90% | 备考从"看计划"变成"被带着走" |

剩余 10% 是"课程胶囊"等后置功能、图片 OCR 的精度打磨、以及产品细节的持续迭代。
