# FoxSay 指导纲领

> 起草时间：2026-06-16
> 状态：v1.0 — 首次系统性规划
> 约束：本文件优先级低于 AGENTS.md，高于其他文档

---

## 一、项目定位（一句话）

**FoxSay 是第一个真正理解课程结构的 AI 学习助手。**

不是"又一个 RAG 聊天框"。FoxSay 的核心差异化是：从材料中抽取知识结构（KC + 先修关系 + 章节骨架），在课程边界内精准回答，诚实拒答超范围问题。

---

## 二、成功标准

### MVP 成功（近期）
学生上传一门课的全部材料后，FoxSay 能：
1. 生成准确的课程骨架图（章节 + 核心概念 + 先修链路）
2. 在课程范围内回答问题，每条回答带来源引用
3. 超范围问题诚实拒答
4. 给出"你最薄弱的章节是 X"的诊断

### 产品成功（中期）
一个中国本科生在期末前一周，用 FoxSay 复习一门课，觉得"比自己看书快"。

### 开源成功（远期）
其他开发者能在 5 分钟内跑起来，能理解代码，愿意贡献。

---

## 三、技术路线

### 解析链路（已实现）
```
pdfplumber（快）→ Docling（结构化，CPU 慢）→ MinerU API（云端）→ flat fallback
```
默认 pdfplumber。MinerU 作为 fallback 处理扫描件。

### 知识抽取链路（已实现）
```
DMAP → LangGraph 4 阶段 Wiki Build → KC 抽取 → Merkle 增量合并
```

### 检索链路（已实现）
```
macro（章节级，文本匹配）→ micro（KC 级，文本匹配）→ chunk（向量检索）→ CRAG 门控
```

### Agent 链路（已实现）
```
7 工具 ReAct 循环（max 3 轮）→ DeepSeek V4 Flash → SSE 流式
```

---

## 四、推进阶段

### Phase 1：真实材料验证（当前）
**目标**：用真实线性代数材料跑通全链路，验证 KC 质量。

动作：
- 解压线性代数课件 + 课堂资料
- 上传到 FoxSay，触发 pipeline
- 检查 KC 抽取质量（数量、名称、定义、先修关系）
- 检查骨架图是否合理
- 用 Agent 问几个典型问题，验证回答质量

验收：
- KC 数量 ≥ 15（一门课的核心概念）
- 先修关系 ≥ 5 条
- 骨架图章节划分合理
- Agent 回答带来源引用
- 超范围问题正确拒答

### Phase 2：产品体验补全
**目标**：让 MVP 有"灵魂"。

动作：
- 材料处理完后推送"第一个惊喜"（骨架图 + 薄弱诊断）
- 狐狸人设 prompt 工程
- 陪伴复习改为有状态推进
- 知识图谱 Drawer（点击节点弹 KC 详情）

### Phase 3：前端修复
**目标**：前端能正常构建和运行。

动作：
- 修 reactflow / react-syntax-highlighter 类型声明
- CitationCard 跳原文
- 知识图谱节点颜色接 mastery

### Phase 4：开源准备
**目标**：其他开发者能 5 分钟跑起来。

动作：
- Docker Compose 一键启动
- README 重写（产品视角）
- CONTRIBUTING.md
- 演示 GIF

---

## 五、技术债清单

| 项 | 优先级 | 状态 |
|----|--------|------|
| search_wiki_layer 性能 | P0 | ✅ 已修（文本匹配） |
| DMAP fallback 丢数据 | P0 | ✅ 已修 |
| ChapterWiki.overview 为空 | P0 | ✅ 已修 |
| LLM 客户端无 timeout | P0 | ✅ 已修 |
| skeleton core_concepts 为空 | P1 | ✅ 已修（prompt 改进） |
| Docling heading 丢失 | P1 | ✅ 已修 |
| MinerU fallback 集成 | P1 | ✅ 已修 |
| 前端 build 类型错误 | P1 | 待修 |
| datetime.utcnow() deprecation | P2 | 待修 |
| 旧 crag.py 待清理 | P2 | 待修 |

---

## 六、禁止事项

- ❌ 不做多用户 / 权限 / 协作
- ❌ 不做课程胶囊分享 / 社区广场
- ❌ 不做移动端（一期）
- ❌ 不做诊断 15 题 / 出卷功能
- ❌ 不引入新的重依赖（Neo4j、新框架）除非有具体需求
- ❌ 不在没有真实数据验证的情况下声称"完成"

---

## 七、决策记录

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-06 | pdfplumber 默认，Docling/MinerU 作为 fallback | Docling CPU 太慢，MinerU 处理扫描件 |
| 2026-06 | macro/micro 层改文本匹配 | 消除 N 次 embedding API 调用 |
| 2026-06 | HEC-8 文档必须与代码对齐 | 防止新 agent 走偏 |
| 2026-06 | skeleton prompt 请求 core_concepts | 之前硬编码空列表 |
