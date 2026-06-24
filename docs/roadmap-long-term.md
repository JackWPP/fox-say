# FoxSay 长期规划：从 MVP 到产品

> 起草时间：2026-06-22
> 状态：v1.0 — 首次系统性长期规划
> 约束：本文件是长期推进的指导纲领，每阶段结束时回顾和调整
> 前置文档：`AGENTS.md`、`docs/project-charter.md`

---

## 一、产品愿景

**FoxSay 是第一个真正理解课程结构的 AI 学习助手。**

不是通用聊天框，不是简单 RAG，而是：
- 能从材料中抽取知识结构（KC + 先修关系 + 章节骨架）
- 能主动引导学习（"你该学这个了"）
- 能实时响应问题（带来源引用 + 超范围拒答）
- 能自动生成教学内容（讲义、练习题、思维导图）
- 能管理学习进度（日程、薄弱诊断、复习计划）

**与 NotebookLM 的差异**：课程结构感知 + 主动引导 + 练习判分 + 中国大学生场景。

---

## 二、阶段规划总览

```
Phase 0: MVP 收尾（当前 → 2 周）
  ↓
Phase 1: Skill 系统 + 生成能力（2 → 6 周）
  ↓
Phase 2: 备考工作台（6 → 10 周）
  ↓
Phase 3: 产品打磨 + 开源准备（10 → 14 周）
```

---

## Phase 0: MVP 收尾（当前 → 2 周）

**目标**：MVP 功能全部达到可用水准，154 测试全过，端到端链路稳定。

### 里程碑

| # | 事项 | 验收标准 | 状态 |
|---|------|---------|------|
| 0.1 | 文档口径统一 | `architecture.md` 与代码一致，HEC-8 生效 | ✅ |
| 0.2 | Pipeline 端到端跑通 | 上传 PDF → KC 抽取 → 骨架图 → Agent 问答 | ✅ |
| 0.3 | Worker KC 成功率 ≥ 80% | 概率论 5/5 章节有 KC | ✅ |
| 0.4 | CRAG 边界控制生效 | 超范围问题正确拒答 | ✅ |
| 0.5 | 超级备考模式 v1 | 对话式引导（teach→quiz→review） | ✅ |
| 0.6 | 前端 build 通过 | `npm run build` 无错误 | ✅ |
| 0.7 | 第一个惊喜 | 材料处理完主动推骨架 + 薄弱诊断 | ✅ |
| 0.8 | 知识图谱 Drawer | 点击节点弹 KC 详情 | ✅ |

### 验收方式

- 每个里程碑有对应测试或可观察产出
- 端到端测试：上传概率论材料 → 27 KC → Agent 问答有引用 → 拒答生效
- 前端 `npm run build` 通过
- 后端 `pytest` 154+ 通过

---

## Phase 1: Skill 系统 + 生成能力（2 → 6 周）

**目标**：建立可扩展的 Skill 注册机制，实现核心生成类工具。

### 核心设计

**Skill = Agent 可调用的结构化能力单元。**

当前 Agent 有 7 个查询类工具。Phase 1 新增生成类 + 交互类工具：

```
查询层（已有）：search_wiki, get_concept, get_course_map, ...
生成层（新增）：generate_lecture, generate_quiz, generate_flashcards
交互层（新增）：show_concept_graph, show_formula
```

### 里程碑

| # | 事项 | 验收标准 | 状态 |
|---|------|---------|------|
| 1.1 | Skill 注册机制 | 新增 Skill 不改 Agent 代码，tool 列表动态构建 | ✅ |
| 1.2 | `generate_lecture` Skill | Agent 能从 KC + Wiki 生成结构化讲义（Markdown + 公式 + 引用） | ✅ |
| 1.3 | `generate_quiz` Skill | Agent 能从 KC 生成练习题（选择/填空/证明）+ 答案 + 解析 | ✅ |
| 1.4 | `generate_flashcards` Skill | Agent 能从 KC 生成闪卡（front/back） | ✅ |
| 1.5 | `show_concept_graph` Skill | 返回概念的先修链路 + 相关概念，前端渲染为图谱 | ✅ |
| 1.6 | 讲义生成前端 | 讲义渲染为可交互页面（公式、图谱、练习题入口） | ✅ |
| 1.7 | 练习题前端 | 练习题渲染为交互式卡片（选择/填空 + 判分） | ✅ |

### Skill 架构

```python
# backend/app/services/skills.py
SKILL_REGISTRY: dict[str, SkillDef] = {}

@dataclass
class SkillDef:
    name: str
    description: str
    parameters: dict
    handler: Callable
    category: str  # "query" | "generate" | "interactive"

def register_skill(name, description, parameters, category):
    def decorator(fn):
        SKILL_REGISTRY[name] = SkillDef(name, description, parameters, fn, category)
        return fn
    return decorator

# Agent TOOLS 动态构建
def build_tools() -> list[dict]:
    tools = [STATIC_TOOL_DEFS...]  # 现有 7 个
    for skill in SKILL_REGISTRY.values():
        tools.append({
            "type": "function",
            "function": {"name": skill.name, "description": skill.description, "parameters": skill.parameters}
        })
    return tools
```

### 验收方式

- `generate_lecture("概率论", "ch-2", "brief")` 返回结构化讲义（≥ 500 字，含公式和引用）
- `generate_quiz("概率论", "ch-2", count=5)` 返回 5 道练习题（含答案和解析）
- 新增 Skill 只需写一个函数 + 装饰器，不改 Agent 代码
- 前端讲义页能渲染公式和引用

---

## Phase 2: 备考工作台（6 → 10 周）

**目标**：超级备考模式从"对话式引导"升级为"AI 工作台"。

### 核心能力

```
通用 Agent 能力（已有）
  ├── 问答 + 引用 ✅
  ├── 拒答 ✅
  └── /btw 插话 ✅

备考工作台（新增）
  ├── 上下文感知（Agent 知道你在学什么）
  ├── 侧边栏进度面板（Todo + 倒计时）
  ├── 自动讲义/练习题生成（调 Skill）
  ├── 日程管理（今天要学完第2、3章）
  └── 薄弱诊断（基于 KC 答题历史）
```

### 里程碑

| # | 事项 | 验收标准 | 依赖 |
|---|------|---------|------|
| 2.1 | 上下文感知 | Agent 回答时自动关联当前学习进度 | Phase 1 |
| 2.2 | 侧边栏进度面板 | 显示章节完成状态 + 倒计时 + 当前任务 | 无 |
| 2.3 | 日程管理 | 用户输入"今天要学完第2、3章"→ 系统生成任务列表 | 2.2 |
| 2.4 | 自动讲义生成 | 用户说"学第2章"→ 系统调 `generate_lecture` 生成讲义 | 1.2 |
| 2.5 | 自动练习题生成 | 用户说"出几道题"→ 系统调 `generate_quiz` 生成题目 | 1.3 |
| 2.6 | 薄弱诊断 | 基于答题历史，自动标记薄弱 KC | 1.3 |
| 2.7 | 知识图谱子图 | 只显示当前章节的 KG 节点和边 | 1.5 |

### 验收方式

- 用户进入备考模式 → 侧边栏显示"Day 2/5 · 当前：第3章多维随机变量"
- 用户说"帮我生成第2章的讲义"→ 系统返回结构化讲义
- 用户做完 5 道题 → 系统标记"条件概率：薄弱，需要复习"
- 用户说"今天要学完第2、3章"→ 侧边栏更新任务列表

---

## Phase 3: 产品打磨 + 开源准备（10 → 14 周）

**目标**：从"能用"到"好用"，准备开源发布。

### 里程碑

| # | 事项 | 验收标准 | 依赖 |
|---|------|---------|------|
| 3.1 | Docker Compose 一键启动 | `docker compose up` 5 分钟内跑起来 | 无 |
| 3.2 | README 重写 | 产品视角，30 秒 GIF 演示 | 3.1 |
| 3.3 | CONTRIBUTING.md | 开发者能理解代码并贡献 | 3.2 |
| 3.4 | 性能优化 | search_wiki_layer 预存 embedding | 无 |
| 3.5 | 多课程支持验证 | 5 门课程全部跑通 | 无 |
| 3.6 | 狐狸人设完善 | 全场景个性化对话 | 无 |
| 3.7 | 前端响应式 | 移动端基本可用 | 无 |

### 验收方式

- 新开发者 `git clone` + `docker compose up` → 5 分钟跑起来
- README 有 30 秒 GIF 展示核心功能
- 5 门课程（线性代数、数据库、计算机网络、概率论、公司理财）全部端到端跑通

---

## 三、技术债清单（持续维护）

| 项 | 优先级 | 状态 | 说明 |
|----|--------|------|------|
| search_wiki_layer 预存 embedding | P1 | 待修 | 当前每次查询实时 embed |
| PPT 旧格式支持 | P2 | 待修 | 需要外部工具转换 |
| 前端 chunk size 优化 | P3 | 待修 | code-splitting |
| 旧 crag.py 清理 | P0 | ✅ | 已删除 |
| datetime deprecation | P0 | ✅ | 已修复 |
| Worker KC 成功率 | P0 | ✅ | 27 KC, 5/5 章节 |

---

## 四、验收机制

### 每阶段结束时

1. **功能验收**：每个里程碑有对应测试或可观察产出
2. **回归测试**：`pytest` 154+ 通过，`npm run build` 通过
3. **端到端测试**：上传真实材料 → pipeline → Agent 问答 → 拒答
4. **文档更新**：`architecture.md` + `project-charter.md` 同步更新

### 每周回顾

- 本周完成了哪些里程碑？
- 有哪些阻塞项？
- 下周优先做什么？

### 质量门禁

- 代码：154+ 测试通过，0 warnings
- 文档：`architecture.md` 与代码一致（HEC-8）
- 功能：每个新功能有测试或 `Not-tested` 标注
- 依赖：`pyproject.toml` 里的库都有 import（HEC-7）

---

## 五、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| LLM API 不稳定 | Worker KC 提取失败 | 重试机制 + JSON 修复（已实现） |
| 大文件处理慢 | 用户体验差 | MinerU fallback + 流式上传 |
| 前端复杂度增长 | 维护困难 | 组件化 + 代码分割 |
| 开源后贡献者少 | 社区不活跃 | 好文档 + good first issues |

---

## 六、成功标准

### MVP 成功（Phase 0 完成后）
学生上传一门课的全部材料后，FoxSay 能：
1. 生成准确的课程骨架图（章节 + 核心概念 + 先修链路）✅
2. 在课程范围内回答问题，每条回答带来源引用 ✅
3. 超范围问题诚实拒答 ✅
4. 给出"你最薄弱的章节是 X"的诊断 ❌

### 产品成功（Phase 2 完成后）
一个中国本科生在期末前一周，用 FoxSay 复习一门课，觉得"比自己看书快"。

### 开源成功（Phase 3 完成后）
其他开发者能在 5 分钟内跑起来，能理解代码，愿意贡献。
