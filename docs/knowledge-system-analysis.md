# FoxSay 知识体系现状分析

> 起草时间：2026-07-10
> 状态：基于代码审查 + 数据库实证分析
> 目的：为知识体系重构提供事实依据

---

## 一、结论先行

**FoxSay 的知识体系从未在生产环境成功构建过。**

5 门课程中，所有课程的 KC（知识卡片）、ChapterWiki（章节摘要）、CourseIndex（课程索引）、DMAP（文档结构图）均为零。代码中存在精心设计的 6 阶段 LangGraph 管线，但从未跑通。

这意味着：知识图谱、概念查询、骨架图、先修链路等功能全部是空壳。

---

## 二、数据库实证

### 2.1 各课程知识体系状态

| 课程 | 材料数 | 解析 | embedding | wiki_build | KC | ChapterWiki | DMAP | CourseIndex |
|------|--------|------|-----------|-----------|-----|-------------|------|-------------|
| 技术经济 | 9 | done | **failed** | skipped | 0 | 0 | 无 | 无 |
| 计算机网络 | 7 | pending | pending | pending | 0 | 0 | 无 | 无 |
| 数据库原理 | 10 | pending | pending | pending | 0 | 0 | 无 | 无 |
| 概率论 | 4 | running | pending | pending | 0 | 0 | 无 | 无 |
| 国际财务管理 | 0 | — | — | — | 0 | 0 | 无 | 无 |

### 2.2 存在的数据

- **course summary**：部分课程有（旧管线 LLM 直接生成的文字摘要）
- **parsed_text**：技术经济的 9 个材料有（MinerU V4 解析结果）
- **Qdrant chunk**：技术经济为 0（embedding 步骤失败，chunk 未入库）

---

## 三、管线故障链分析

### 3.1 技术经济的故障链

```
材料上传 → 解析(MinerU V4) ✅ → 归一化 ✅ → 保存 parsed_text ✅
    → chunking ✅ → embedding ❌ FAILED → storing 跳过 → wiki_build 跳过
```

embedding 失败导致：
1. chunk 没有进入 Qdrant 向量库
2. `_update_course_if_ready` 虽然判断材料全部 ready
3. 但 `wiki_build` 被标记为 `deferred to course-level`，从未被实际调用
4. 知识体系构建从未启动

### 3.2 其他课程的故障链

计算机网络、数据库原理：`parsing` 步骤就卡在 `pending`，后续步骤全部未启动。
概率论：`parsing` 卡在 `running`，同样后续全部 pending。

---

## 四、架构问题深度分析

### 4.1 致命问题（必须修）

#### P0-1: 管线把文档结构全部摧毁

`pipeline.py:222`：
```python
docling_chunks = [{"text": combined_text, "heading": "", "level": 0, "page": 0}]
```

所有材料的文本被拼成一个巨大字符串，包成单个 flat chunk。每个 PDF/PPT 原本的标题层级、章节结构全部丢弃。DMAP 的层级构建逻辑因此永远只产出一个"未分章"节点。

**后果**：Supervisor LLM 只能从 3000 字符预览中猜测章节划分，所有下游产物（KC、ChapterWiki、CourseIndex）的基础都是错的。

#### P0-2: pipeline.py 有未定义变量的死代码

`pipeline.py:132-160` 引用三个未定义变量：`chunks`、`embed_texts`、`_write_lock`。这意味着材料解析完成后的 Qdrant 向量化步骤会崩溃（NameError）。chunk 从未存入向量库。

**后果**：检索层只有 KC 和 ChapterWiki 能工作（如果它们存在的话），chunk 级向量检索从未生效。

#### P0-3: KC 的 source_refs 永远为空

`wiki_builder.py` 中 Worker 生成 KC 时从不填充 `source_refs`。检索时 KC 返回的 `file_name` 和 `locator` 全是空字符串。

**后果**：学生看不到引用来源，违反 agents.md "来源引用"的核心契约。

### 4.2 严重问题（应该修）

#### P1-1: 四套冗余的课程结构表示

| 信息 | CourseIndex | CourseSkeleton | ChapterWiki | DMAP |
|------|:-----------:|:--------------:|:-----------:|:----:|
| 章节 ID/标题 | yes | yes | yes | yes |
| 核心概念 | yes | yes | yes（KC names） | no |
| 重要性 | yes | yes | no | no |
| 先修关系 | yes | yes | yes | yes（cross_refs） |

没有单一数据源。不同 LLM 调用产出的数据可能互相矛盾。

#### P1-2: chunking.py 从未被使用

花精力写的 LangChain 语义切块器在整个管线中零 import。实际用的是 `_markdown_to_chunks()`（简单 regex 按 `\n\n` 分割）或 flat single-chunk blob。

#### P1-3: Skeleton 丢弃 LLM 输出

`generate_skeleton()` 让 LLM 生成 `core_concepts`、`difficulty_areas`、`prerequisite_chain`，然后在返回值中硬编码为空列表直接丢掉。

#### P1-4: retrieval.py 有两个从未被调用的函数

`tool_search_materials()` 和 `retrieve()` 是旧代码遗留。

### 4.3 中等问题（值得修）

#### P2-1: Reviewer 是昂贵的表演

审查条件全是规则可判定的（句子数、集合成员检查），不需要 LLM。LLM 失败时静默返回 `passed=True`，违反 HEC-1。

#### P2-2: KC schema 充满投机性字段

`cognitive_dimension`、`derivation_steps`、`common_mistakes_v2`、学情字段等从未被填充。增加 schema 复杂度但无实际价值。

#### P2-3: ChapterWiki 字段硬编码

`exam_weight=0.0`、`difficulty="medium"`、`prerequisite_chapters=[]` 从未计算。

#### P2-4: Embedding 缓存碰撞

`_chapter_embedding_cache` 用 `text[:200]` 作为 key，Chapter 和 KC 的 on-demand embedding 共享同一 cache，可能返回错误的 embedding。

#### P2-5: Merkle tree diff 算了没人用

`changed_node_ids` 写入 WikiState 但没有任何 LangGraph stage 读取。每次构建都是全量重建。

#### P2-6: CourseSummarizer 违反 HEC-1

`try/except: return ""` 模式静默吞错。

---

## 五、wiki_builder.py 6 阶段管线详解

### 当前设计

```
Stage 1: Supervisor (LLM)
  输入：DMAP chapters（实际只有 1 个"未分章"）
  工作：推断章节边界 + 生成 CourseIndex
  输出：tasks[] (WorkerTask) + course_index

Stage 2: Workers (LLM × N, 并行)
  输入：每个 chapter 的文本（截取 15000 chars）
  工作：提取 KC（name, definition, formula, prerequisites...）
  输出：list[KC] per chapter

Stage 3: Reducer (纯代码)
  工作：按 ID 去重 KC（同名同章 → 保留长定义）
       构建 ChapterWiki（overview = 前5个元素 text_preview 拼接）
  输出：merged_kcs + chapter_wikis

Stage 4: Reviewer (LLM)
  工作：检查 KC 质量（定义长度、bloom_level 有效性、先修引用）
  输出：ReviewResult（passed/failed）
  问题：LLM 失败时静默跳过

Stage 5: ChapterSummarizer (LLM)
  工作：为每个 chapter 生成 2-4 句中文概述
  输出：更新 chapter_wikis[].overview

Stage 6: CourseSummarizer (LLM)
  工作：生成 200-400 字课程总结
  输出：course_summary 字符串
```

### 管线评估

| 阶段 | 是否有价值 | 问题 |
|------|-----------|------|
| Supervisor | **部分有价值** | 章节边界推断依赖 flat DMAP，信息严重不足 |
| Workers | **核心有价值** | KC 提取是知识体系的基础，但 source_refs 缺失 |
| Reducer | **有价值** | 去重逻辑过于简单（同名合并），可能误合并 |
| Reviewer | **价值存疑** | 审查条件可用规则替代，LLM 成本浪费 |
| ChapterSummarizer | **有价值** | 但 overview 质量取决于 Worker 提取的 KC 质量 |
| CourseSummarizer | **价值存疑** | 与 course summary 字段重复 |

### 共 5 次 LLM 调用（Supervisor + N 个 Worker + Reviewer + ChapterSummarizer + CourseSummarizer）

---

## 六、检索层现状

### search_wiki_layer() 三层检索

| 层 | 数据源 | 评分方式 | 当前状态 |
|----|--------|---------|---------|
| macro（章节级） | ChapterWiki | embedding cosine | **数据为空，永远返回 0 结果** |
| micro（KC 级） | KC | embedding cosine + 章节加权 | **数据为空，永远返回 0 结果** |
| chunk（原文级） | Qdrant | cosine similarity | **技术经济 chunk 未入库，返回 0 结果** |

**实际效果**：Agent 调用 `search_wiki` 工具时几乎永远拿到空结果，只能用通用知识回答。

---

## 七、缺失的东西

1. **没有 chunk 级向量检索**：向量化代码是死代码，Qdrant 里没有 chunk 数据
2. **KC 无法溯源到原文**：Worker 从不填充 `source_refs`，学生问"书上怎么说的"只能给定义卡片
3. **没有跨材料去重**：教材和课件覆盖同一概念时，可能重复提取同名 KC
4. **没有反馈循环**：不知道哪些 KC 有用、哪些回答被点赞
5. **没有增量更新**：每次构建都是全量重建，Merkle tree diff 算了但没用

---

## 八、根本原因总结

知识体系无法工作的根本原因不是某一个 bug，而是一系列架构决策的累积效应：

1. **管线把所有材料文本拼成 flat blob** → DMAP 无法构建层级结构 → Supervisor 在信息不足的情况下猜测章节 → Worker 在错误的章节划分下提取 KC → 整个知识体系从根基上就是错的

2. **embedding 步骤崩溃** → chunk 没有进 Qdrant → 即使 KC 和 ChapterWiki 存在，检索也只有结构化的知识卡片，没有原文段落

3. **wiki_build 标记为 deferred 但从未被触发** → 知识体系构建代码从未执行

**一句话总结：知识体系的代码写了，但从来没有成功运行过。即使运行了，由于 flat blob 的问题，产出的知识体系质量也是建立在错误的基础上的。**

---

## 九、重构方向建议

### 必须先做的（地基）

1. **修复管线，保留每个材料的标题层级**：不再拼成 flat blob，用每个材料解析后的 markdown 标题结构来构建 DMAP
2. **接通 chunking.py + Qdrant 存储**：让语义切块和向量化真正工作
3. **修复 embedding 步骤**：排查技术经济 embedding 失败的原因

### 然后做的（知识体系）

4. **给 KC 补上 source_refs**：Worker 提取 KC 时记录来源材料和段落位置
5. **确定单一数据源**：CourseIndex 还是 ChapterWiki 作为章节信息的唯一来源？
6. **简化 Reviewer**：用规则替代 LLM 做质量检查
7. **删除死代码**：pipeline.py 死代码、retrieval.py 未使用函数、KC schema 投机字段

### 长期做的（深水区）

8. **重新设计知识提取流程**：是否真的需要 6 阶段 LangGraph？能否简化？
9. **增量更新**：新材料加入时只提取增量 KC，不全量重建
10. **反馈循环**：根据学生交互优化 KC 质量和检索排序
