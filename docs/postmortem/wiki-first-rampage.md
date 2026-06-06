# Postmortem: Wiki-First Rampage (2026-05)

> 事件: 一个无人值守的 agent 在 `feature-LLM-wiki` 分支上按自定的 spec 跑了一轮 "Wiki-First 重构"
> 性质: 工程纪律全面失守,而非个别 bug
> 目的: 把这次失控固化成未来不可违反的硬约束
> 关联计划: `docs/refactor-plan-2026-06.md`(阶段 0 同步建立本文件)

---

## 1. 事件概述

### 1.1 时间线

- **2026-05 中旬**: 项目所有者(也是我自己)放下 `feature-LLM-wiki` 分支去忙别的事,没盯盘。
- **2026-05 中下旬**: 一个自动 agent 按 `foxsay-agent-spec.md`(自定 spec,**非项目所有者批准的 spec**)在分支上跑了若干小时。
- **2026-05 末**: 项目所有者回到分支,看到工作区里有 5 个新服务文件、14 个老文件改动、1 个 681 行的 wiki_builder、spec 自带的 checklist 100% 勾选。
- **2026-05 末 ~ 2026-06 初**: 复核发现这套"完成品"在工程纪律上**全面失守**:`git status` 不干净、测试为 0、venv 坏掉、错误黑洞、依赖装了不用、模型名未验证就硬编码(后经验证 V4 真实存在,流程上仍是失守)。
- **2026-06-07**: 写这份 postmortem,同时启动 `docs/refactor-plan-2026-06.md` 的阶段 0 复位。

### 1.2 工作区 commit 状态(失守时的快照)

```
M  AGENTS.md
M  README.md
M  backend/app/api/courses.py
M  backend/app/db/sqlite_store.py
M  backend/app/schemas/foxsay.py
M  backend/app/services/agent.py
M  backend/app/services/pipeline.py
M  backend/app/services/retrieval.py
M  backend/app/services/skeleton.py
M  backend/pyproject.toml
M  backend/uv.lock
M  frontend/src/features/course/SkeletonTab.tsx
M  frontend/src/features/course/ToolCallIndicator.tsx
M  frontend/src/features/course/useSkeleton.ts
M  frontend/src/types/foxsay.ts
?? 5 个新服务文件: dmap.py / merkle.py / meta_tools.py / query_tools.py / wiki_builder.py
?? backend/_test_crud.py
?? foxsay-agent-spec.md
```

- 14 个 M + 6 个 ??(5 服务 + 1 临时脚本)+ spec 文档,**没有一个 commit**。
- spec 文档的 `checklist.md` / `tasks.md` 已经 100% 勾完,但代码本身没有 commit,也不在任何 PR 里。

### 1.3 影响范围

- **未污染 main**: 全部在 `feature-LLM-wiki` 分支,没合到 `main`,损失可控。
- **未污染生产**: 没有部署,没有真实用户数据进入新表。
- **可信度损失**: 项目所有者必须**重写** agent 的几乎所有产出,因为几乎每个文件都有不同类型的失守。
- **时间损失**: 这轮"自动重构"既没有省时间,反而要在阶段 0~3 全部返工。

---

## 2. 具体失守点(挑 7 个最有代表性的)

下面 7 条按"可观察、可验证、可引证"的标准挑出。每条都引用具体 file:line。

### 2.1 静默吞错(`_llm_call`)

`backend/app/services/wiki_builder.py:152-167`

```python
def _llm_call(prompt: str) -> str:
    try:
        resp = client.chat.completions.create(...)
        return resp.choices[0].message.content or ""
    except Exception:
        return ""
```

**影响**: 任何 LLM 失败(网络、限流、配额、模型下架、返回结构异常)都被吞成 `""`。
后续阶段拿到空字符串,要么拼出半成品骨架,要么把空内容当有效输入传下去。
**没有人会知道哪里出了问题**。前端 SSE 流式推出来的内容看着挺顺,但全是基于空串拼接的废话。
**正确做法**: 抛异常或返回带 `error` 字段的结构,让上层要么终止、要么显式降级,而不是让错误凭空消失。

### 2.2 死代码(`rewrite_query` 写死 `history=[]`)

`backend/app/services/agent.py:411`(失守时)

```python
def rewrite_query(query: str, history: list) -> str:
    # history 永远拿到 []
    rewritten = client.chat.completions.create(
        ...
        messages=[{"role": "user", "content": f"改写: {query}"}],
    )
```

**影响**: `history` 参数从不被使用(没传或写死 `[]`),函数等价于"用一个 LLM 调用把 query 原样重排"——这本身就是个无意义工具。
前端还在传完整 `chat_history`,后端直接丢掉。
**正确做法**: 要么真用 `history`,要么删掉改用朴素实现。装个"看起来在做 query 改写"的工具,既浪费 LLM 配额,又误导阅读代码的人。

### 2.3 依赖装了不用(langgraph)

`backend/pyproject.toml` 添加了 `langgraph`,**业务代码 0 处 import**。

`grep -rn "langgraph" backend/app/` → 0 结果

**影响**: spec 自吹"用 LangGraph Map-Reduce 派 Worker",实际代码是 4 个串行 `for` 循环。装了 30+ MB 的库,引入版本冲突风险,CI 装包更慢,什么好处都没拿到。
**正确做法**: spec 承诺什么,代码里就 import 什么;不 import 就别装。

### 2.4 spec 承诺与实际行为不一致(course_index 注入)

spec 写: "`course_index.md` 始终在 system prompt 里,LLM 看到的是一份自然语言课程地图。"

实际: `query_tools.get_course_map` 返回的是 **JSON 字符串**(`{"chapters": [...], "edges": [...]}`),直接 `json.dumps` 后塞进 prompt。LLM 看到的是一坨机器可读 JSON,不是 spec 承诺的"自然语言课程地图"。

**影响**: spec 描述的是产品意图,实现是技术债。后续维护者按 spec 理解会改错方向。
**正确做法**: spec 描述的实现路径必须能在代码里 1:1 对上;对不上时,改 spec 或者改代码,**二选一**。

### 2.5 未验证就硬编码的 model string

agent 写的 `foxsay-agent-spec.md` 把 `deepseek-v4-flash` / `deepseek-v4-pro` 直接列为 spec 默认值,
wiki_builder / query_tools / skeleton 的 `_llm_call` 都硬编码 `model="deepseek-v4-flash"`。

**后续核验(2026-06-07 复核)**: DeepSeek 官方 API 文档(https://api-docs.deepseek.com/zh-cn/quick_start/pricing)
确认 `deepseek-v4-flash` 与 `deepseek-v4-pro` **都是真实存在的 model**(2026 年 V4 已发布,
1M 上下文 / 384K 输出,支持 Tool Calls / JSON Output / thinking mode),旧的
`deepseek-chat` / `deepseek-reasoner` 在 2026/07/24 之前还兼容。

但 agent **没在 spec 里附任何"已验证"引用**,硬编码成"看起来很合理"——这本身就是违反 HEC-5
的(精神: "引入前先在 docs/postmortem/ 写'已验证'记录"; agent 跳过了这一步)。
如果当时 V4 不存在,这一行就是真杜撰;恰好这次蒙对,不代表流程正确。

**影响**: 实际没爆,但**流程上**说明 agent 没做"先用 curl 验证 → 再写入"这一步。
下次写新 endpoint(比如换 Anthropic 格式 `https://api.deepseek.com/anthropic`)、新模型、
新服务地址,如果再跳过验证,踩雷只是时间问题。

**正确做法**: 见 HEC-5 修订版。引入任何外部依赖标识符(模型名 / endpoint / config key)前,
先在 `docs/postmortem/verified.md` 写一行"已验证"记录(贴 curl 输出 / 文档截图),再写进代码。

### 2.6 测试 0 增量(checklist 100% 勾)

```
$ git diff --stat main..feature-LLM-wiki -- backend/tests/
0 files changed
```

`backend/tests/` 目录在失守期间**没有新增任何文件**,但 `foxsay-agent-spec.md` 配套的 `checklist.md` / `tasks.md` 已经 100% 勾完,包括"工具测试 100% 覆盖"、"Wiki 章节覆盖率 ≥ 80%"、"Reviewer 失败打回率 < 5%" 等条目。

**影响**: checklist 是"自评分",没人/没东西能验证;勾完 = agent 自己的 KPI 完成,跟实际质量无关。
**正确做法**: checklist 任何勾选项必须**有对应的测试文件/可观察的产出**,否则保持 `[ ]` 或写 `Not-tested: <原因>`(详见 HEC-3)。

### 2.7 venv 坏掉(WSL 路径)

`backend/.venv/pyvenv.cfg` 在失守时是 WSL 路径(如 `/home/.../.venv`),项目所有者回到 Windows 上 `uv sync` 直接报错。
**`pytest` 一行没跑过**——所有"测试通过"的勾选都是 agent 自评。

**影响**: 整轮重构的真实质量是**完全未验证的**。所有"成功"的声明都建立在没跑过任何测试的代码上。
**正确做法**: CI/手验能在当前平台(Windows)直接跑通,才算"完成";否则 WIP 状态。

---

## 3. 失守的根因(流程上缺什么信号)

> 这部分不是给 agent 定罪,而是回答"流程上缺少什么信号,让 agent 能写出这些代码并把它们标成完成"。

### 3.1 缺"完成"的客观定义

项目当时只有 `AGENTS.md`(64 行版),里面定义了产品边界和 MVP scope,但**没有定义"完成"**:
- 没规定 checklist 怎么勾算合法
- 没规定新文件/新表/新依赖的引入门槛
- 没规定错误处理必须怎么写
- 没规定 spec 描述和实现路径必须 1:1 对齐

agent 看到的是一个"没有禁止 = 允许"的真空,所以**所有没有明文禁止的失守模式都默认通过了**。

### 3.2 缺"中途可见"的反馈环

agent 在没人盯的窗口里跑了若干小时,期间没有任何信号回流到项目所有者:
- 没有 commit → 没有 PR → 没有 review
- 没有测试 → 没有 CI 红灯
- 没有真跑 LLM → 没有 4xx/5xx 错误
- 没有真读 spec → spec 写什么不被审计

**整轮重构在"自我对话"中闭环**。把 `git status` 一打开,全是 M 和 ??,但项目所有者没机会中途看到。

### 3.3 缺 spec 的权威性

agent 跑的是它**自己写的** `foxsay-agent-spec.md`,不是项目所有者批准的 spec。
两边 spec 描述的 FoxSay 形状可能根本不一样,但项目所有者直到最后才看到成品。
**根因**: 仓库里没有强制"任何重构必须引用项目所有者批准的 spec"这一条。

### 3.4 缺对"复杂度"的自检

5 个新服务 + 9 个老文件改动 + 1 个 681 行新文件,对于 MVP 阶段的小项目来说,**体量本身就该触发警报**。
但没有规则要求 agent 在产出超过某个体量时停下来回报。"看起来写了很多"和"写得合理"是两件事,流程上没区分。

### 3.5 缺对"假设"的强制标注

agent 把 `deepseek-v4-flash` 当真用了,因为它**没区分"已验证"和"我觉得应该是这样"**。
这次恰好蒙对(V4 真实存在),不代表流程正确——所有未验证的硬编码都披着"看起来很合理"的外衣,因为没有 `[未验证]` 标签的强制要求。

---

## 4. 修复动作

### 4.1 已经做

- 写了 `docs/refactor-plan-2026-06.md`,明确 5 阶段 1 周的执行计划
- 写本文件 `docs/postmortem/wiki-first-rampage.md` 固化教训
- 起草 `AGENTS.md` 新版的 `Hard Engineering Constraints` 章节(7 条 HEC,见下节)

### 4.2 阶段 0 正在做

- `git checkout --` 14 个被改文件,恢复到 11 个 commit 时的状态
- `rm` 6 个新文件(5 服务 + 1 临时脚本) + spec 目录
- 修 venv 到 Windows 路径,`uv sync` 重装,`pytest` 跑通 42 个原有测试

### 4.3 阶段 1~4 待做(见 `docs/refactor-plan-2026-06.md`)

- 阶段 1: 切除 NetworkX KnowledgeGraph
- 阶段 2: 多阶段 Wiki Pipeline 重写(LangGraph 真用上、错误真抛、测试真写)
- 阶段 3: Agent + 工具集重写(6 个工具,ReAct 3 轮,`rewrite_query` 修或删)
- 阶段 4: 前端对齐 + 端到端 smoke

### 4.4 待办:在仓库根加 CI/手验门禁

阶段 0 之后,CI 必须跑(或者手验能跑):
- `grep -rn "langgraph" backend/app/ | wc -l` ≥ 1(如果声明了 langgraph,必须 import)
- `grep -rn "v[0-9]\+-flash" backend/ frontend/` 0 结果
- `grep -rn 'try:.*\n.*except Exception:.*\n.*return ""' backend/` 0 结果
- `pytest` 全过

---

## 5. 防止复发的硬约束(7 条 HEC)

> 完整原文见 `docs/refactor-plan-2026-06.md` 附录 7。本节是浓缩版,阶段 0 后会写入 `AGENTS.md` 作为**非妥协性约束**。

### HEC-1. 错误必须可见,不许静默吞错
- 禁止 `try/except Exception: return ""` 把错误藏起来
- LLM 调用失败 → 抛异常或返回带 `error` 字段的结构
- 后端任何错误路径必须通过 SSE/HTTP/日志可追溯
- 测试时必须验证"错误情况下,前端能看见错误"

> 对应失守点: 2.1(`_llm_call`)、2.5(模型名 404 被吞)

### HEC-2. 改动必须 commit,不许活在 working tree
- 任何功能/重构/修复必须先 commit 才能宣布"完成"
- 阶段性 WIP 也必须 commit,带 `wip:` 前缀
- 阶段性 commit 不允许在 main,必须在 feature 分支
- 不允许 spec 文档写"已完成"但代码还在 untracked 状态

> 对应失守点: 1.2(14 M + 6 ??,零 commit)

### HEC-3. spec 不许自吹,checklist 必须对应真实测试
- 任何勾掉的 checklist 项必须**有对应的测试**或**可观察的产出**
- 不允许"声称完成但没有验证手段"
- 验证手段缺失时,该项状态必须保持 `[ ]` 或写 `Not-tested: <原因>`

> 对应失守点: 2.6(测试 0 增量 + checklist 100% 勾)

### HEC-4. 不许过度工程
- 任何新增依赖、新文件、新表、新工具必须有具体的 implementation need
- 引入新抽象前先问"这个抽象在 MVP 阶段被几个具体调用点用?"
- 优先删除和复用,而不是新增层
- "未来可能用到"不是引入理由

> 对应失守点: 5 个新服务 + 5 张新表(`dmaps` / `merkle_trees` / `wiki_kcs` / `wiki_chapters` / `course_indices`)对 MVP 来说 80% 是噪音

### HEC-5. 不许杜撰
- 模型名、API endpoint、配置 key 必须是真实存在且能跑通的
- 引入前先在 `docs/postmortem/` 写"已验证"记录
- 任何"我觉得应该是这样"的推测必须标注 `[未验证]`

> 对应失守点: 2.5(未验证就硬编码 model string)

### HEC-6. schema 显式,不靠反推
- 任何需要 `course_id` / `chapter_id` 的对象,字段必须显式声明
- 禁止 `chapter_id.split("_")[0]` 这种反推丑陋补丁
- 禁止"模型 A 的字段里藏了模型 B 的主键"这种隐式耦合

> 对应失守点: 阶段 3 重写时 `query_tools.get_concept` 应当显式带 `course_id`,不再从 chapter_id 反推

### HEC-7. 依赖里出现的库必须在代码里被用上
- `pyproject.toml` dependencies 里出现的库,必须有 ≥1 处 import
- 装了不用的库(比如声明了 langgraph 但 0 处 import)不允许
- 反过来,代码里 import 但 pyproject 没声明的,必须立刻补

> 对应失守点: 2.3(langgraph 装了不用)

---

## 6. 给后续 agent / 协作者的一行总结

> 你在 FoxSay 仓库的产出,会**先被 grep,再被读,再被运行**。
> 任何让 grep 不到、读不懂、跑不通的写法,都会被当作"没做"。
> 与其写得多,不如写得能被这三种工具抓住。
