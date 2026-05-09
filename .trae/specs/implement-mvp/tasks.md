# Tasks

## Phase 0: 基础架构搭建（前后端可并行）

- [x] Task 0.1: 后端基础架构搭建
  - [x] SubTask 0.1.1: 安装后端依赖（`uv sync --extra runtime --extra dev`），确保 pyproject.toml 中依赖正确
  - [x] SubTask 0.1.2: 创建 `backend/app/main.py`，包含 FastAPI app 实例、`/health` 端点、CORS 中间件
  - [x] SubTask 0.1.3: 创建 `backend/app/core/config.py`，使用 pydantic-settings 从环境变量加载配置（DEEPSEEK_API_KEY, DEEPSEEK_API_BASE, DEEPSEEK_MODEL, QDRANT_URL, FOXSAY_ENV）
  - [x] SubTask 0.1.4: 创建 `backend/app/db/` 目录，实现内存存储层（dict-based）用于 MVP 开发，包含 CourseStore 和 MaterialStore
  - [x] SubTask 0.1.5: 验证：运行 `uv run uvicorn app.main:app --reload`，确认 `/health` 返回 200

- [x] Task 0.2: 前端基础架构搭建
  - [x] SubTask 0.2.1: 安装前端依赖（react, react-dom, @vitejs/plugin-react, tailwindcss, postcss, autoprefixer, react-router-dom, lucide-react）
  - [x] SubTask 0.2.2: 配置 Vite（添加 plugin-react、API 代理到 localhost:8000）
  - [x] SubTask 0.2.3: 创建 `frontend/index.html`、`frontend/src/main.tsx`、`frontend/src/App.tsx` 基础入口
  - [x] SubTask 0.2.4: 配置 Tailwind CSS（postcss.config.js，引入 tailwind 指令到全局 CSS）
  - [x] SubTask 0.2.5: 创建 `frontend/src/shared/api.ts` API 客户端，封装 fetch 调用
  - [x] SubTask 0.2.6: 创建 `frontend/src/shared/types.ts` 重新导出 foxsay.ts 类型
  - [x] SubTask 0.2.7: 验证：运行 `npm run dev`，确认浏览器可访问页面

- [x] Task 0.3: Docker Compose 更新
  - [x] SubTask 0.3.1: 创建 `backend/Dockerfile`
  - [x] SubTask 0.3.2: 更新 `infra/docker-compose.yml` 添加 backend 服务

## Phase 1: 课程管理（前后端可并行）

- [x] Task 1.1: 后端课程 API
  - [x] SubTask 1.1.1: 将 `schemas/foxsay.py` 中 dataclass 转为 Pydantic BaseModel（保持字段对齐前端 foxsay.ts 类型）
  - [x] SubTask 1.1.2: 创建 `backend/app/api/courses.py` 路由模块：
    - `POST /courses/import-timetable`：接收 CSV 文件，解析并批量创建课程
    - `POST /courses`：手动创建单门课程
    - `GET /courses`：获取全部课程列表
    - `GET /courses/{course_id}`：获取单门课程详情
  - [x] SubTask 1.1.3: 创建 `backend/app/services/timetable.py`：CSV/Excel 解析服务
  - [x] SubTask 1.1.4: 编写课程 API 的 pytest 测试

- [x] Task 1.2: 前端书架页面
  - [x] SubTask 1.2.1: 创建 `frontend/src/app/Layout.tsx`：整体布局（fox amber 顶部导航 + 内容区）
  - [x] SubTask 1.2.2: 创建 `frontend/src/features/bookshelf/BookshelfPage.tsx`：课程卡片网格
  - [x] SubTask 1.2.3: 创建 `frontend/src/features/bookshelf/CourseCard.tsx`：单个课程卡片组件
  - [x] SubTask 1.2.4: 创建 `frontend/src/features/bookshelf/CreateCourseModal.tsx`：创建课程表单
  - [x] SubTask 1.2.5: 创建 `frontend/src/features/bookshelf/ImportTimetableModal.tsx`：CSV 导入组件
  - [x] SubTask 1.2.6: 配置 React Router 路由：`/` → 书架，`/courses/:courseId` → 课程详情
  - [x] SubTask 1.2.7: 创建 `frontend/src/features/bookshelf/useCourses.ts`：课程数据 hook

## Phase 2: 材料处理（前后端可并行）

- [x] Task 2.1: 后端材料处理管线
  - [x] SubTask 2.1.1: 创建 `backend/app/api/materials.py` 路由模块：
    - `POST /courses/{course_id}/materials`：上传材料文件
    - `GET /courses/{course_id}/materials/{material_id}/status`：查询处理状态
    - `GET /courses/{course_id}/materials`：列出课程全部材料
  - [x] SubTask 2.1.2: 创建 `backend/app/services/parsing.py`：文档解析服务（PDF 使用 PyPDF2/pdfplumber，文本直接读取）
  - [x] SubTask 2.1.3: 创建 `backend/app/services/chunking.py`：文本分块服务（固定窗口 + 重叠）
  - [x] SubTask 2.1.4: 创建 `backend/app/services/embedding.py`：调用 DeepSeek/OpenAI embedding API 生成向量
  - [x] SubTask 2.1.5: 创建 `backend/app/services/vectorstore.py`：Qdrant 客户端封装（按 course_id 创建 collection、upsert、search）
  - [x] SubTask 2.1.6: 创建 `backend/app/services/pipeline.py`：编排异步处理管线（解析→分块→嵌入→存储）
  - [x] SubTask 2.1.7: 编写材料管线测试（使用 mock Qdrant 和 mock LLM）

- [x] Task 2.2: 前端材料上传页面
  - [x] SubTask 2.2.1: 创建 `frontend/src/features/course/CourseDetailPage.tsx`：课程详情页主容器（Tab 切换：材料/骨架/问答/备考）
  - [x] SubTask 2.2.2: 创建 `frontend/src/features/course/MaterialsTab.tsx`：材料列表与上传
  - [x] SubTask 2.2.3: 创建 `frontend/src/features/course/MaterialUpload.tsx`：拖拽上传组件
  - [x] SubTask 2.2.4: 创建 `frontend/src/features/course/MaterialList.tsx`：材料列表与状态指示
  - [x] SubTask 2.2.5: 创建 `frontend/src/features/course/useMaterials.ts`：材料数据 hook

## Phase 3: 骨架图与知识图谱（前后端可并行）

- [x] Task 3.1: 后端骨架生成
  - [x] SubTask 3.1.1: 创建 `backend/app/services/knowledge_graph.py`：NetworkX 图构建（节点=概念，边=依赖关系）
  - [x] SubTask 3.1.2: 创建 `backend/app/services/skeleton.py`：使用 LLM 从材料文本提取章节、核心概念、难点、先修链路
  - [x] SubTask 3.1.3: 创建 `backend/app/api/skeleton.py` 路由模块：
    - `GET /courses/{course_id}/skeleton`：获取课程骨架
  - [x] SubTask 3.1.4: 在材料处理管线完成后触发骨架生成
  - [x] SubTask 3.1.5: 编写骨架生成测试

- [x] Task 3.2: 前端骨架图
  - [x] SubTask 3.2.1: 创建 `frontend/src/features/course/SkeletonTab.tsx`：骨架图展示页
  - [x] SubTask 3.2.2: 创建 `frontend/src/features/course/SkeletonTree.tsx`：层级结构树组件（章节→核心概念→难点）
  - [x] SubTask 3.2.3: 创建 `frontend/src/features/course/useSkeleton.ts`：骨架数据 hook

## Phase 4: CRAG 问答（前后端可并行）

- [x] Task 4.1: 后端 CRAG 问答
  - [x] SubTask 4.1.1: 创建 `backend/app/services/retrieval.py`：Qdrant 检索 + CRAG 分数判断逻辑
  - [x] SubTask 4.1.2: 创建 `backend/app/services/crag.py`：CRAG 核心服务（检索→分数判断→LLM 生成回答/拒答）
  - [x] SubTask 4.1.3: 创建 `backend/app/api/chat.py` 路由模块：
    - `POST /courses/{course_id}/chat`：课程问答端点
  - [x] SubTask 4.1.4: 编写 CRAG 测试：验证三个分数阈值的行为（grounded/ambiguous/out_of_scope）
  - [x] SubTask 4.1.5: 编写测试：验证非拒答回答包含 citation
  - [x] SubTask 4.1.6: 编写测试：验证检索失败不回退到 model-only 回答

- [x] Task 4.2: 前端问答界面
  - [x] SubTask 4.2.1: 创建 `frontend/src/features/course/ChatTab.tsx`：问答页面
  - [x] SubTask 4.2.2: 创建 `frontend/src/features/course/ChatMessage.tsx`：消息气泡组件（区分 AI/用户，显示 citation 和 confidence 状态）
  - [x] SubTask 4.2.3: 创建 `frontend/src/features/course/ChatInput.tsx`：问题输入框
  - [x] SubTask 4.2.4: 创建 `frontend/src/features/course/useChat.ts`：问答 hook

## Phase 5: 超级备考模式（前后端可并行）

- [x] Task 5.1: 后端备考模式
  - [x] SubTask 5.1.1: 创建 `backend/app/services/review.py`：复习计划生成服务（基于骨架 + 倒计时 + LLM）
  - [x] SubTask 5.1.2: 创建 `backend/app/api/review.py` 路由模块：
    - `POST /courses/{course_id}/review-plan`：生成复习计划
    - `POST /courses/{course_id}/btw`：/btw 插话端点
  - [x] SubTask 5.1.3: 编写复习计划和 /btw 测试

- [x] Task 5.2: 前端备考模式
  - [x] SubTask 5.2.1: 创建 `frontend/src/features/course/ReviewTab.tsx`：备考模式页面
  - [x] SubTask 5.2.2: 创建 `frontend/src/features/course/ReviewPlanView.tsx`：复习计划日历视图
  - [x] SubTask 5.2.3: 创建 `frontend/src/features/course/BtwInput.tsx`：/btw 插话输入组件
  - [x] SubTask 5.2.4: 创建 `frontend/src/features/course/useReview.ts`：备考 hook

## Phase 6: 集成与完善

- [x] Task 6.1: 前后端联调
  - [x] SubTask 6.1.1: 确认所有 API 端点与前端 hook 的请求/响应对齐
  - [x] SubTask 6.1.2: 修复 CORS 和代理问题
  - [x] SubTask 6.1.3: 添加错误处理与加载状态

- [x] Task 6.2: 视觉与交互打磨
  - [x] SubTask 6.2.1: 确认 fox amber / midnight charcoal / warm white 配色一致
  - [x] SubTask 6.2.2: 添加狐狸品牌元素（favicon、空状态插画）
  - [x] SubTask 6.2.3: 添加考试倒计时显示

# Task Dependencies
- [Task 1.1] depends on [Task 0.1]
- [Task 1.2] depends on [Task 0.2]
- [Task 2.1] depends on [Task 1.1]
- [Task 2.2] depends on [Task 1.2, Task 2.1] (需要 API 可用)
- [Task 3.1] depends on [Task 2.1]
- [Task 3.2] depends on [Task 2.2]
- [Task 4.1] depends on [Task 2.1]
- [Task 4.2] depends on [Task 2.2]
- [Task 5.1] depends on [Task 3.1, Task 4.1]
- [Task 5.2] depends on [Task 3.2, Task 4.2]
- [Task 6.1] depends on [Task 5.1, Task 5.2]
- [Task 6.2] depends on [Task 6.1]

# 并行策略
- Phase 0 中 Task 0.1 和 Task 0.2 完全并行
- Phase 1 中 Task 1.1 和 Task 1.2 完全并行
- Phase 2 中 Task 2.1 和 Task 2.2 可并行（前端可先 mock API）
- Phase 3 中 Task 3.1 和 Task 3.2 可并行
- Phase 4 中 Task 4.1 和 Task 4.2 可并行
- Phase 5 中 Task 5.1 和 Task 5.2 可并行
- Phase 6 串行执行
