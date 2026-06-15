# FoxSay Review 综合结论

> 日期：2026-06
> 同伴文档：`FoxSay-Architecture-Review.md`（深度报告 399 行）/ `docs/gap-analysis.md`
> 本文件目标：**5 分钟读完，知道这个项目当前在哪、接下来该往哪走**

---

## 一句话定性

> **FoxSay 已经把一个"下一代教学型 RAG"的工程骨架立住了，但产品价值还没传递到用户那里 — 不是缺新功能，是欠收口。**

---

## 三个核心结论

### 结论 1：工程纪律是这个项目最大的资产，不要弄丢

- `AGENTS.md` 的 **HEC-1~7** 是从一次失败的 agent 狂奔里提炼的硬约束，每条都可验证
- 数据模型层（DMAP / KC / ChapterWiki / CourseIndex / Merkle）是面向教学的 schema，不是通用三元组 — 比 PRD 路线图原构想更聪明
- 真用了 LangGraph 的 Send fanout + Annotated reduce，不是简历驱动开发
- DSML 防御层证明这支团队"先承认模型有 bug 再写代码"

**这一层不要动，要继承。**

### 结论 2：产品价值传递的断层比功能缺口更严重

后端做的最重的一块工程（Wiki 构建 LangGraph 4 阶段 + Merkle 增量 + 7 工具 Agent），用户**完全感知不到**：

| 后端已经做出来 | 用户能看到吗 |
|---|---|
| KC 知识卡（bloom_level/common_mistakes/exam_patterns） | ❌ 没有任何 KC 卡片视图 |
| ChapterWiki 章节 Wiki | ❌ 没有专门页面 |
| 知识图谱（KC.prerequisites） | ❌ 没有可视化 |
| Merkle 增量构建 | ❌ 用户不在意，但开发者也看不到 dashboard |
| SSE 事件（material_processed / skeleton_ready） | ❌ 前端没消费 |
| Citation（引用） | ⚠️ 显示了，但点击不能跳到原文 |

> 这是 FoxSay 当前最痛的点。它有 70 分的工程，40 分的产品力。

### 结论 3：新旧双轨是当前最大的隐性负担

存在三处「同一个意图、两套实现」的耦合臭味，全都没收口：

1. **检索路径**：CRAG（老）vs Agent + 三层 Wiki（新） — 前端只用新的，老的没删，互不通信
2. **骨架生成**：`generate_skeleton`（LLM 看 8000 字 raw text）vs `generate_skeleton_from_wiki`（从 CourseIndex 派生） — 后者**写了但从来没被调用**
3. **文档与代码**：`roadmap-to-prd.md` 还在描述"三元组 + Neo4j + LightRAG 双层"，实际代码已经走 DMAP+KC 路线 — 后来者按旧文档动手会出乱子

---

## 当前最关键的 3 个具体矛盾

| # | 矛盾 | 后果 | 修复成本 |
|---|---|---|---|
| ① | **Wiki 检索没有向量索引** — `search_wiki_layer` 每次提问对所有 KC + ChapterWiki 实时 embed，O(N) 调 embedding API | 课程稍大就慢炸 + 烧钱 | 80-120 行 |
| ② | **ChapterWiki 是空壳** — `_build_chapter_wikis` 输出 overview="", exam_weight=0，但 agent 工具 `get_chapter_outline` 承诺返回这些字段 → LLM 拿到空字段会乱编 | Agent 工具失效 | 1 个 LLM stage |
| ③ | **CitationCard 不能跳原文** — DMAP 里已经记了 page，差最后一公里 | 用户感知不到引用闭环 | 1 个 endpoint + 1 个组件 |

修这 3 件事，**用户感知会有质变**，工程负担反而下降。

---

## 行动清单（按 ROI 排序）

### 🔴 P0（1-2 周内，纯收口，0 风险）

- [ ] **删 `crag.py` 路径**，把 CRAG 三档阈值整合进 agent 的 `search_wiki` 工具
- [ ] **`_generate_and_store_skeleton` 改走 `generate_skeleton_from_wiki`**
- [ ] **Wiki 数据建向量索引**：build 阶段把 KC/ChapterWiki 文本批量 embed 进 Qdrant，检索改为一次向量搜索 + layer 过滤
- [ ] **补 `_build_chapter_wikis` 的 overview / exam_weight**：再起一个 LLM 小 stage 或从 KC 摘要本地派生
- [ ] **重写 `docs/roadmap-to-prd.md`**：旧路线图已严重过时
- [ ] **补 `docs/postmortem/verified.md`**：AGENTS.md 的 HEC-5 强制要求，自己破自己规矩

### 🟡 P1（1-2 月内，产品价值传递）

- [ ] **前端消费 SSE 事件** — 实现 PRD"第一个惊喜"的最小可行版（"我读完了，来看看我发现了什么 👀"）
- [ ] **CitationCard 引用闭环** — 点击跳原 PDF 高亮页（DMAP 已有 page，差 endpoint）
- [ ] **知识图谱可视化** — react-flow 把 KC + prerequisites 画出来，点节点弹 KC 卡 → 直接发起 Chat。**这是 FoxSay 对外的差异化王牌**
- [ ] **备考状态机执行引擎** — `review_session` 表和 API 都建好了，前端 `ReviewTab` 把它用起来
- [ ] **错误文案人格化** — `fox-copy.ts` 框架已有，补全所有错误场景

### 🟢 P2（中长期，能力扩张）

- [ ] **评测体系（RAGAS + 5-10 门课的 ground truth Q&A 集）** — 没有这层，后面所有改动都是抛硬币
- [ ] **图片 OCR + Marker 公式还原** — 理工科必备
- [ ] **可观测性面板** — token 计数、tool call 统计、SSE 错误率、每问平均成本
- [ ] **闪念胶囊** — 全局输入条 + 异步归位
- [ ] **移动端 / PWA** — 大学生主战场在手机

### 🔬 实验性

- [ ] **本地小模型 + 云端 Reviewer 的混合架构** — Qwen 7B / Llama 4 mini 跑 worker 抽 KC，云端只跑 Reviewer，十分之一的成本
- [ ] **教师视角 schema** — 上传考试大纲，pipeline 自动对齐生成"教师视角 ChapterWiki"

---

## 决策树：如果只有 X 时间

### 如果只有 1 周
做 P0 第 3 项 + P1 第 1 项：
> Wiki 数据建向量索引 + 前端消费 SSE 事件。
>
> **效果**：性能立省 90%，用户首次感受到"狐狸真的读完了"。

### 如果只有 1 个月
P0 全做 + P1 前 3 项：
> 收口双轨 + 引用闭环 + 知识图谱可视化。
>
> **效果**：产品力从 46% 跳到 65%+，对外能讲"和别的 RAG 不一样"。

### 如果只有 1 个季度
P0 + P1 + P2 前 2 项：
> 加上评测体系 + 多模态。
>
> **效果**：可以放心换模型、调 prompt，进入"敢迭代"的阶段。

---

## 评分速览

| 维度 | 评分 | 一句话 |
|---|---|---|
| 工程纪律 | ⭐⭐⭐⭐⭐ | HEC-1~7 是模范 |
| 数据模型 | ⭐⭐⭐⭐ | KC schema 有教学产品味 |
| 后端实现 | ⭐⭐⭐⭐ | LangGraph 真并发 + Merkle 增量 + DSML 防御 |
| 前端实现 | ⭐⭐⭐ | 能用，缺图谱可视化，ChatTab 应拆分 |
| 检索性能 | ⭐⭐ | Wiki 无向量索引，每问 O(N) embed |
| 产品完整度 | ⭐⭐ | 约 46%，缺"超级"和"智能体感" |
| 可运维性 | ⭐⭐ | 单机 + 无可观测 + 无评测 |
| 文档新鲜度 | ⭐⭐ | roadmap 严重落后于代码 |

---

## 一张图：从"工程骨架"到"产品价值"

```
今天                                        目标
┌──────────────────────┐                  ┌──────────────────────┐
│  70 分的工程         │                  │  70 分的工程         │
│  40 分的产品力       │                  │  70 分的产品力       │
│                      │                  │                      │
│  KC / Wiki / Merkle  │  ─P0 收口债─▶    │  ↑ 不变              │
│  跑在地下,用户看不到 │  ─P1 价值传递─▶  │  ↑ 全部露在 UI 上    │
│  新旧双轨拖累        │  ─P2 能力扩张─▶  │  ↑ 多模态 + 评测     │
└──────────────────────┘                  └──────────────────────┘
        基线 46%                                   目标 70%+
```

---

## 最后一句

> 这个项目最危险的不是没有图谱可视化、没有评测、没有错题本。
> 最危险的是 **— 工程做对了，但产品没做完 —** 这种状态拖得越久，团队越容易开始怀疑"是不是当初不该建 KC 这么复杂的 schema"。
>
> 答案是：**那是对的，但要赶紧把它接到用户能看到的地方。**

---

*详细评分、模块清单、问题代码定位见同伴文档 `FoxSay-Architecture-Review.md`。*
