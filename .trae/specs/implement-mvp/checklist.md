# FoxSay MVP 实现检查清单

## Phase 0: 基础架构
- [x] 后端 `uv sync` 成功安装所有依赖
- [x] `uv run uvicorn app.main:app --reload` 启动成功，`/health` 返回 200
- [x] 后端 config.py 正确从环境变量加载配置
- [x] 后端内存存储层 CourseStore / MaterialStore 可用
- [x] 前端 `npm install` 成功安装所有依赖
- [x] `npm run dev` 启动成功，浏览器可访问页面
- [x] Vite 代理配置正确，前端可调用后端 API
- [x] Tailwind CSS 正确渲染 foxAmber / midnightCharcoal / warmWhite 颜色
- [x] Docker Compose 包含 Qdrant + backend 服务，`docker compose up` 正常启动

## Phase 1: 课程管理
- [x] `POST /courses/import-timetable` 接收 CSV 并批量创建课程
- [x] `POST /courses` 手动创建单门课程，初始状态 `empty`
- [x] `GET /courses` 返回全部课程列表
- [x] `GET /courses/{course_id}` 返回单门课程详情
- [x] 课程 API 测试全部通过
- [x] 前端书架页面展示课程卡片网格
- [x] 前端创建课程表单可正常提交
- [x] 前端 CSV 导入功能可用
- [x] React Router 路由正确：`/` 书架、`/courses/:courseId` 详情

## Phase 2: 材料处理
- [x] `POST /courses/{course_id}/materials` 上传文件成功
- [x] `GET /courses/{course_id}/materials/{material_id}/status` 返回正确状态
- [x] `GET /courses/{course_id}/materials` 列出全部材料
- [x] PDF 解析服务可提取文本
- [x] 文本分块服务生成合理大小的 chunk
- [x] Embedding 服务调用 DeepSeek/OpenAI API 成功
- [x] Qdrant 按 course_id 创建 collection 并 upsert 向量
- [x] 异步处理管线完整运行（解析→分块→嵌入→存储）
- [x] 材料处理管线测试通过（mock Qdrant/LLM）
- [x] 前端材料上传组件支持拖拽和点击上传
- [x] 前端材料列表显示处理状态

## Phase 3: 骨架图
- [x] NetworkX 图构建正确（节点=概念，边=依赖）
- [x] LLM 从材料提取章节、核心概念、难点、先修链路
- [x] `GET /courses/{course_id}/skeleton` 返回骨架数据
- [x] 材料处理完成后自动触发骨架生成
- [x] 骨架生成测试通过
- [x] 前端骨架图以层级结构展示

## Phase 4: CRAG 问答
- [x] Qdrant 检索返回分数和源文档
- [x] score >= 0.72 时 confidence_status = grounded，包含 citation
- [x] 0.55 <= score < 0.72 时 confidence_status = ambiguous
- [x] score < 0.55 时 confidence_status = out_of_scope，返回拒答消息
- [x] 非拒答回答包含至少一条 citation（"来自 [文件名] · 第X部分"）
- [x] 检索失败不回退到 model-only 回答
- [x] `POST /courses/{course_id}/chat` 端点工作正常
- [x] CRAG 三个阈值测试全部通过
- [x] citation 包含测试通过
- [x] 无 model-only 回退测试通过
- [x] 前端问答页面显示 AI 回答和用户问题
- [x] 前端显示 citation 和 confidence 状态

## Phase 5: 超级备考
- [x] `POST /courses/{course_id}/review-plan` 生成复习计划
- [x] `POST /courses/{course_id}/btw` 处理 /btw 插话
- [x] /btw 回答后返回当前复习步骤
- [x] 复习计划和 /btw 测试通过
- [x] 前端备考模式展示复习计划日历
- [x] 前端 /btw 输入和回复功能可用

## Phase 6: 集成与完善
- [x] 所有 API 端点与前端 hook 请求/响应完全对齐
- [x] CORS 和代理无问题
- [x] 错误处理和加载状态完整
- [x] 配色一致：fox amber / midnight charcoal / warm white
- [x] 狐狸品牌元素存在
- [x] 考试倒计时正确显示

## 课程隔离约束
- [x] 所有 course-scoped API 端点包含 course_id
- [x] 向量检索按 course_id 隔离
- [x] 知识图谱按 course_id 隔离
- [x] 对话历史按 course_id 隔离
- [x] 复习计划按 course_id 隔离
