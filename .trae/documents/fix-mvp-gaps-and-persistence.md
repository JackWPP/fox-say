# FoxSay MVP 查漏补缺实施计划

## 问题诊断总结

经过对整个代码库的全面审查，发现以下关键问题：

### 核心问题

#### 问题 A：数据不持久化（最严重）

* **现状**：所有 Store（`CourseStore`、`MaterialStore`、`SkeletonStore`、`ReviewPlanStore`）都是纯内存 dict，重启即丢失

* **影响**：创建课程、上传材料后刷新页面全部消失，这是用户反馈的"刷新一下课程就没了"的根因

* **方案**：引入 SQLite 作为持久化存储，使用 Python 标准库 `sqlite3`（零新依赖），实现文件级数据库

#### 问题 B：异步处理管线形同虚设

* **现状**：`pipeline.py` 的 `process_material` 用 `asyncio.create_task` 触发，但核心操作（`parse_document`、`embed_texts`）全是同步阻塞调用，会阻塞事件循环

* **影响**：上传文件后处理可能阻塞整个服务；且由于 embedding 调用外部 API，失败时没有任何重试机制

* **方案**：

  1. 将阻塞的同步调用放入 `asyncio.to_thread` 执行
  2. 增加任务状态追踪表（在 SQLite 中），记录每步进度
  3. 增加 API 端点查询处理进度

#### 问题 C：Store 实例各自为政，不共享状态

* **现状**：`course_store` 在 `courses.py` 创建，`material_store` 在 `materials.py` 创建，`skeleton_store` 同时在 `skeleton.py` 和 `pipeline.py` 各创建了一份，`review_plan_store` 在 `review.py` 创建

* **影响**：`pipeline.py` 中创建的 `skeleton_store` 和 `skeleton.py` API 中的 `skeleton_store` 是不同实例，骨架生成后 API 查询不到

* **方案**：统一 Store 单例管理，使用 FastAPI 的依赖注入或 app.state

#### 问题 D：材料元数据中缺少文件名传递给向量检索

* **现状**：`pipeline.py` 的 metadata 只有 `course_id` 和 `material_id`，缺少 `file_name`

* **影响**：CRAG 回答的 citation 中 `file_name` 为空，违反 "来自 \[文件名] · 第X部分" 的引用要求

* **方案**：在 pipeline 的 metadata 中补充 `file_name`

#### 问题 E：前端轮询材料状态不够完善

* **现状**：`useMaterialStatus` 只跟踪单个 material 的状态，`useMaterials` 没有轮询机制

* **影响**：上传后需要手动刷新才能看到状态变化

* **方案**：`useMaterials` 增加自动轮询（当存在 processing 状态材料时）

#### 问题 F：处理失败的降级策略未实现

* **现状**：`pipeline.py` 的 except 只标记 `status = "failed"`，没有降级到基础文本 RAG

* **影响**：Spec 要求 "解析部分失败但存在可提取文本时降级为基础文本 RAG"

* **方案**：在 pipeline 中实现部分失败的降级逻辑

***

## 实施计划

### Phase 1：持久化存储（最高优先级）

#### Task 1.1：创建 SQLite 持久化层

* 创建 `backend/app/db/sqlite_store.py`，实现基于 SQLite 的持久化 Store

* 数据表设计：

  * `courses`：id, title, status, teacher, exam\_date, created\_at

  * `materials`：id, course\_id, filename, kind, status, file\_path, created\_at

  * `skeletons`：course\_id, data\_json, created\_at

  * `review_plans`：course\_id, data\_json, created\_at

  * `tasks`：id, course\_id, material\_id, step, status, detail, created\_at, updated\_at（任务进度追踪）

* 使用 `sqlite3` 标准库，数据库文件路径从环境变量 `SQLITE_PATH` 读取，默认 `data/foxsay.db`

* 实现与现有 dict Store 相同的接口，方便逐步替换

#### Task 1.2：替换内存 Store 为 SQLite Store

* 在 `main.py` 中初始化 SQLite 数据库和 Store 实例

* 将 Store 实例挂载到 `app.state`，通过 FastAPI 依赖注入访问

* 更新所有 API 路由使用依赖注入获取 Store

* 更新 `pipeline.py` 使用依赖注入的 Store

* 删除旧的 `db/store.py` 中的内存 Store 类（或保留为测试 mock）

#### Task 1.3：验证持久化

* 启动后端，创建课程，重启后端，确认课程仍在

* 编写持久化测试

### Phase 2：统一 Store 实例 + 修复骨架存储断裂

#### Task 2.1：统一 Store 单例管理

* 创建 `backend/app/db/deps.py`，定义 FastAPI 依赖注入函数

* 所有路由模块通过 `Depends()` 获取 Store 实例

* 确保 `pipeline.py` 和所有 API 模块使用同一个 Store 实例

#### Task 2.2：修复骨架存储断裂问题

* 验证 `pipeline.py` 生成的骨架能通过 `GET /courses/{course_id}/skeleton` 查询到

* 修复当前两个 `skeleton_store` 实例不共享的问题

### Phase 3：异步处理管线修复与增强

#### Task 3.1：修复事件循环阻塞

* `parse_document`、`embed_texts`、`_qdrant.upsert_chunks` 等同步阻塞调用包装到 `asyncio.to_thread()`

* `QdrantStore` 的操作全部用 `asyncio.to_thread` 包装

#### Task 3.2：实现任务进度追踪

* 在 SQLite 的 `tasks` 表中记录每步进度

* 定义的步骤：`uploaded` → `parsing` → `chunking` → `embedding` → `storing` → `skeleton_generating` → `ready` / `failed`

* 每步开始和完成时更新 tasks 表

#### Task 3.3：新增任务进度 API

* `GET /courses/{course_id}/materials/{material_id}/progress`：返回详细的步骤进度

* 返回格式：`{ material_id, current_step, steps: [{step, status, detail}] }`

#### Task 3.4：前端材料状态自动轮询

* 修改 `useMaterials` hook，当任一材料 status 为 `processing` 时，每 5 秒自动轮询

* 材料列表卡片显示当前处理步骤（如"正在解析"、"正在嵌入"等）

### Phase 4：Citation 修复 + 降级策略

#### Task 4.1：修复 Citation 缺少文件名

* 在 `pipeline.py` 的 metadata 中增加 `file_name` 字段（从 material 记录获取 filename）

* 在 `retrieval.py` 的 `_format_results` 中确保 `file_name` 从 payload 正确传递

#### Task 4.2：实现部分失败降级

* 在 `pipeline.py` 中，当 `parse_document` 抛出异常但文件可部分读取时，降级为基础文本

* 降级时 material 状态标记为 `ready` 并增加 `degraded: true` 标记

* 在 API 响应中暴露 `degraded` 字段

### Phase 5：安全性修复

#### Task 5.1：.env 文件安全

* **当前 .env 包含真实 API Key**，需要确认 `.gitignore` 包含 `.env`

* 确保 `.env` 不会被提交到版本控制

### Phase 6：前后端对齐验证与端到端测试

#### Task 6.1：前后端联调验证

* 完整走通流程：创建课程 → 上传材料 → 等待处理完成 → 查看骨架 → 问答 → 备考

* 修复联调中发现的问题

#### Task 6.2：补充测试

* 持久化 Store 的单元测试

* Pipeline 步骤追踪测试

* Citation 文件名传递测试

* 降级策略测试

***

## 依赖关系

```
Phase 1 (持久化) ← Phase 2 (统一Store) ← Phase 3 (异步增强)
                                              ← Phase 4 (Citation+降级)
Phase 5 (安全) 可并行
Phase 6 (验证+测试) 依赖 Phase 1-4 全部完成
```

## 预期成果

* 课程和材料数据持久化到 SQLite，重启不丢失

* 文件上传后可追踪每一步处理进度

* 骨架生成后 API 可正确查询

* CRAG 回答包含完整的文件名引用

* 部分解析失败可降级处理

* Store 实例统一，无断裂

