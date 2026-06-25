# FoxSay v2 — NotebookLM 风格 UI 升级 + 智能体能力增强 实施计划

## [x] Task 1: 后端基础设施修复（ChapterWiki.overview + 性能优化）
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 修复 wiki_builder.py 中 ChapterWiki.overview 为空的问题：在 LangGraph 4阶段（Supervisor→Workers→Reducer→Reviewer）后增加一个 overview 生成步骤，或者在 Workers 阶段要求生成章节概述
  - 优化 search_wiki_layer（retrieval.py）的性能：将 KC embedding 预计算并缓存到 KC 对象中（KC 增加 embedding 字段），避免每次检索时实时 embed 所有 KC
  - 清理旧的 crag.py 遗留代码路径，确认所有聊天都走 agent.py stream endpoint
  - 更新 sqlite_store.py 支持新字段的读写
- **Acceptance Criteria Addressed**: AC-9, AC-10, AC-14
- **Test Requirements**:
  - `programmatic` TR-1.1: wiki_builder 生成的 ChapterWiki.overview 字段非空且长度 ≥ 50 字符
  - `programmatic` TR-1.2: KC 对象包含预计算的 embedding 字段，search_wiki_layer 不再调用 embedding 接口 embed 所有 KC
  - `programmatic` TR-1.3: 单次 search_wiki 检索（20个KC场景）耗时 < 500ms
  - `programmatic` TR-1.4: 所有现有 pytest 测试通过
- **Notes**: overview 生成可以复用现有 LLM 调用，在 Reducer 阶段合并后增加一个 summarize 步骤。embedding 预存在 wiki_build pipeline 的 chunking 阶段之后、storing 阶段之前批量计算。

## [x] Task 2: 后端新增 API（笔记 + 来源过滤 + 原文片段）
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 新增笔记 CRUD API：
    - POST /courses/{id}/notes 创建笔记（title, content, source_citations）
    - GET /courses/{id}/notes 列表
    - PATCH /courses/{id}/notes/{note_id} 编辑
    - DELETE /courses/{id}/notes/{note_id} 删除
  - 修改 chat/stream endpoint：支持 `selected_source_ids` 和 `selected_note_ids` 参数，检索时仅使用指定来源/笔记
  - 新增 GET /courses/{id}/materials/{mid}/source-preview endpoint：根据 DMAP ID 或 chunk 返回原文片段 + page 信息
  - 笔记内容需要 embedding 后存入 Qdrant，使用独立的 metadata 标记 type=note
  - 更新 schemas/foxsay.py 添加 Note 相关 schema
  - 添加对应的测试
- **Acceptance Criteria Addressed**: AC-4, AC-7, AC-8, AC-14
- **Test Requirements**:
  - `programmatic` TR-2.1: 笔记 CRUD API 返回正确的状态码和数据结构
  - `programmatic` TR-2.2: 传入 selected_source_ids 后，检索结果仅来自指定来源
  - `programmatic` TR-2.3: source-preview endpoint 返回原文片段和 page 信息
  - `programmatic` TR-2.4: 笔记 embedding 存入 Qdrant，可被 search_wiki 检索到
  - `programmatic` TR-2.5: 新增测试覆盖笔记 API，全部 pytest 通过
- **Notes**: 笔记作为一等公民参与检索，但在引用时标记为"来自笔记 · [笔记标题]"区别于材料来源。

## [x] Task 3: 前端设计系统搭建（Tailwind 配置扩展 + 基础组件）
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 扩展 tailwind.config.ts 配色：
    - 灰阶：slate 50-950（背景、边框、文本层次）
    - 语义色：success(green)、warning(amber已有)、error(red)、info(blue)
    - 背景层次：page bg(#F8FAFC)、card bg(white)、sidebar bg(#F1F5F9)
    - 保持 foxAmber(#F59E0B) 主色
  - 定义阴影层级：shadow-sm/subtle/md/lg（参考 NotebookLM 柔和阴影）
  - 定义圆角尺度：rounded-lg(8px)/xl(12px)/2xl(16px)/3xl(20px)
  - 定义动画：统一 transition 时长（150ms/200ms/300ms）和 easing
  - 安装并配置 KaTeX 用于数学公式渲染（npm install katex @types/katex）
  - 创建基础 UI 组件：
    - Button 组件（variants: primary/secondary/ghost/icon）
    - Card 组件
    - Checkbox 组件（带 foxAmber 主色）
    - Input/Textarea 组件
    - ScrollArea 组件（美化滚动条）
    - Tooltip 组件（纯 CSS 或轻量实现）
    - Badge/Pill 组件
    - Drawer 组件（侧边抽屉，用于知识图谱详情）
    - Spinner/Loading 组件
  - 更新 index.css 添加全局样式重置、中文字体优化、KaTeX 样式导入
- **Acceptance Criteria Addressed**: AC-2, AC-11, AC-15
- **Test Requirements**:
  - `programmatic` TR-3.1: npm run build 无 TS 错误，构建成功
  - `human-judgement` TR-3.2: 基础组件在 Storybook 风格的测试页面中视觉一致，hover/active 状态正常
  - `programmatic` TR-3.3: KaTeX 正确配置，CSS 已导入
- **Notes**: 不引入 shadcn/ui 或 Radix，保持手写 Tailwind 组件以符合 HEC-4 不过度工程。组件放在 `frontend/src/components/ui/`。

## [x] Task 4: 三栏布局 + 顶栏重构
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 重写 CourseDetailPage.tsx，从单栏 tab 布局改为三栏布局：
    - 移除传统 Tab 切换，改为三栏常驻
    - 左栏（SourcesPanel）：240px 宽，可折叠为图标条
    - 中栏（ChatWorkspace）：flex-1，内容居中 max-w-3xl
    - 右栏（StudioPanel）：280px 宽，可折叠
  - 重构 Layout.tsx 顶栏：
    - 左侧：返回按钮 + 课程标题
    - 中间：考试倒计时（备考模式下高亮）
    - 右侧：模式切换（日常学习/超级备考）、设置、折叠面板按钮
  - 实现面板折叠/展开动画
  - 书架页（BookshelfPage）也应用新视觉风格：优化 CourseCard 样式，增加 hover 效果
  - 响应式：宽度 < 1280px 时自动折叠右栏
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `human-judgement` TR-4.1: 三栏布局比例正确，视觉上平衡
  - `human-judgement` TR-4.2: 面板折叠/展开动画流畅无卡顿
  - `human-judgement` TR-4.3: 顶栏信息层次清晰
  - `programmatic` TR-4.4: npm run build 通过

## [x] Task 5: 来源面板（SourcesPanel）实现
- **Priority**: high
- **Depends On**: Task 4, Task 2
- **Description**:
  - 创建 SourcesPanel.tsx 组件（左栏）：
    - 顶部："+ 添加来源"按钮（点击打开上传对话框）
    - 上传后显示处理进度（pipeline 步骤可视化）
    - "全选" checkbox
    - 材料列表：每项带 checkbox（默认全选）、文件图标、文件名、来源类型图标
    - 来源项 hover 显示删除按钮
  - 勾选状态通过 props/context 传递给 ChatTab
  - 材料上传组件（MaterialUpload）集成到面板内
  - 处理进度使用步骤条组件显示：解析 → 构建结构图 → 生成 Wiki → 分块 → 向量化 → 就绪
- **Acceptance Criteria Addressed**: AC-1, AC-4, AC-12
- **Test Requirements**:
  - `human-judgement` TR-5.1: 来源列表显示正确，checkbox 可勾选/取消
  - `human-judgement` TR-5.2: 上传后显示处理进度步骤
  - `programmatic` TR-5.3: 勾选状态能正确传递给聊天组件
  - `programmatic` TR-5.4: npm run build 通过

## [x] Task 6: 对话主区重构（ChatWorkspace）+ 课程摘要
- **Priority**: high
- **Depends On**: Task 4, Task 3, Task 2
- **Description**:
  - 创建 ChatWorkspace.tsx 组件（中栏）：
    - 顶部：课程标题（大字号）+ 来源数量 + 日期
    - 课程摘要卡片（CourseSummaryCard）：
      - 首次进入或材料处理完成后显示自动生成的课程概述
      - 下方操作按钮：保存到笔记、复制、重新生成
      - 3个建议问题按钮（横向排列）
    - 消息列表区域重构：
      - 用户消息右对齐（浅灰气泡）
      - AI 消息左对齐（白色卡片，带狐狸头像）
      - 每条 AI 消息底部操作栏：复制、保存到笔记、👍、👎、重新生成
      - 工具调用状态用精致的加载动画替代文字
    - 输入框重构（ChatInput）：
      - 更圆润的大圆角输入框
      - 左侧附件/来源按钮
      - 右侧显示"X个来源" + 发送按钮
      - 输入框 auto-resize
  - 更新 useChat hook 支持传入 selected_source_ids 和 selected_note_ids
  - 集成 KaTeX 数学公式渲染到 MarkdownRenderer
  - CitationCard 升级：点击展开原文预览（调用 source-preview API）
- **Acceptance Criteria Addressed**: AC-1, AC-3, AC-8, AC-11
- **Test Requirements**:
  - `human-judgement` TR-6.1: 课程摘要卡片视觉精致，建议问题按钮可点击
  - `human-judgement` TR-6.2: 消息布局左右对齐，操作栏完整
  - `human-judgement` TR-6.3: 引用点击展开原文预览
  - `human-judgement` TR-6.4: LaTeX 公式正确渲染（如 $\begin{bmatrix}a&b\\c&d\end{bmatrix}$）
  - `programmatic` TR-6.5: npm run build 通过

## [x] Task 7: Studio 面板实现 + 笔记系统前端
- **Priority**: high
- **Depends On**: Task 4, Task 2
- **Description**:
  - 创建 StudioPanel.tsx 组件（右栏）：
    - "Studio" 标题
    - 工具按钮网格（2列）：
      - 知识图谱（Network 图标）
      - 思维导图（GitBranch 图标）
      - 讲义（BookOpen 图标）
      - 闪卡（Layers 图标）
      - 测验（HelpCircle 图标）
      - 复习计划（Calendar 图标）
      - 笔记（FileText 图标）
      - 薄弱分析（AlertTriangle 图标）
    - 工具按钮 hover 效果，点击触发对应功能
    - 生成状态区域：显示正在生成的工具（带旋转加载图标和"基于X个来源"文字）
    - 笔记区域：
      - "笔记" 小标题
      - 新建笔记按钮（+）
      - 笔记列表：每项带标题、时间戳、checkbox（可作为来源勾选）
      - 点击笔记在主区打开查看/编辑
  - 创建 NoteEditor.tsx 组件（简单 markdown 编辑器或纯文本）
  - 创建 useNotes hook 调用笔记 API
  - 笔记的 checkbox 勾选状态传递给聊天
- **Acceptance Criteria Addressed**: AC-1, AC-5, AC-7
- **Test Requirements**:
  - `human-judgement` TR-7.1: 工具网格布局整齐，图标清晰
  - `human-judgement` TR-7.2: 笔记可创建、保存、勾选
  - `human-judgement` TR-7.3: AI 回答的"保存到笔记"按钮正常工作
  - `programmatic` TR-7.4: 笔记 CRUD 操作与后端 API 正确对接
  - `programmatic` TR-7.5: npm run build 通过

## [x] Task 8: 超级备考模式重设计（ExamMode）
- **Priority**: medium
- **Depends On**: Task 4, Task 6, Task 7
- **Description**:
  - 创建 ExamModeLayout.tsx：进入备考模式后切换的布局
    - 顶栏显示醒目的考试倒计时（红色/橙色紧急状态）
    - 左栏改为复习进度时间线：
      - 垂直时间线，Day 1/Day 2/...
      - 当前 Day 高亮（foxAmber），已完成打勾（绿色）
      - 点击 Day 可跳转
    - 中栏：复习内容主区
      - Day N 标题 + 进度条
      - 当前步骤标签（讲解/练习/总结）
      - 内容卡片（白色大卡片）
      - 步骤切换按钮（讲解→练习→总结→下一天）
    - 右栏：备考快速工具
      - 复习计划总览（折叠）
      - 薄弱点列表
      - 生成当日闪卡按钮
      - 查看知识图谱按钮
    - /btw 插话：
      - 在输入框上方显示浮动气泡入口
      - 插话回答以临时卡片形式叠加，不打断主线
      - 有"返回主线"按钮
  - 重构 ReviewTab 和 ReviewPlanView 适配新布局
  - 更新 useReview hook 适配新的交互流程
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `human-judgement` TR-8.1: 进入备考模式后三栏切换为备考布局
  - `human-judgement` TR-8.2: 时间线进度显示正确，Day 之间可切换
  - `human-judgement` TR-8.3: /btw 插话以叠加形式显示，可返回主线
  - `human-judgement` TR-8.4: 步骤切换（讲解→练习→总结→下一天）流程顺畅
  - `programmatic` TR-8.5: npm run build 通过

## [x] Task 9: 知识图谱增强（节点详情 Drawer）
- **Priority**: medium
- **Depends On**: Task 3, Task 7
- **Description**:
  - 升级 KnowledgeGraphTab 为在主区全屏打开（从 Studio 点击触发）
  - 创建 ConceptDrawer.tsx 组件：
    - 从右侧滑入的 Drawer 面板
    - 概念名称（标题）
    - 定义/解释
    - 公式（KaTeX 渲染）
    - 常见错误列表
    - 先修概念列表（可点击跳转）
    - "关于这个概念提问"按钮（预填问题到对话）
    - 相关来源引用列表
  - 节点颜色根据 mastery_score 着色（如果有数据，否则默认颜色）
  - 更新 KnowledgeGraphTab 使用 Drawer 替代 alert/console.log
- **Acceptance Criteria Addressed**: AC-13
- **Test Requirements**:
  - `human-judgement` TR-9.1: 点击图谱节点滑出详情 Drawer
  - `human-judgement` TR-9.2: Drawer 内显示概念定义、公式、先修概念
  - `human-judgement` TR-9.3: "提问该概念"按钮正确跳转到对话并预填问题
  - `programmatic` TR-9.4: npm run build 通过

## [x] Task 10: 书架页 + 全局视觉润色 + Onboarding
- **Priority**: medium
- **Depends On**: Task 3
- **Description**:
  - 优化 BookshelfPage 视觉：
    - CourseCard 增加更精致的阴影、hover 抬升效果
    - 考试倒计时标签更醒目
    - 空状态更友好（大狐狸图标 + 引导文案）
  - 优化 CreateCourseModal 和 ImportTimetableModal 样式：
    - 统一圆角、输入框样式
    - 更好的错误提示
  - 微交互完善：
    - 所有按钮添加 focus-visible ring（可访问性）
    - 列表项入场动画（stagger）
    - 消息发送后的滚动动画
  - 优化 MarkdownRenderer 中代码块样式（匹配新配色）
  - OnboardingPage 适配新视觉风格
  - 错误状态/空状态/加载状态统一设计
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `human-judgement` TR-10.1: 书架页课程卡片视觉精致
  - `human-judgement` TR-10.2: 模态框样式统一美观
  - `human-judgement` TR-10.3: 所有交互元素有明确的状态反馈
  - `programmatic` TR-10.4: npm run build 通过

## [x] Task 11: Agent 智能体能力增强
- **Priority**: medium
- **Depends On**: Task 1, Task 2
- **Description**:
  - 优化 Agent ReAct 循环：
    - max_rounds 自适应：如果 tool_calls 中还有未使用的高置信度工具，允许最多 5 轮（而非硬编码 3 轮）
    - 改进 system prompt，强调工具使用策略：深度概念解释时必须 get_concept 拿完整 KC，跨章节问题必须 get_course_map
  - 改进引用精度：
    - 确保工具返回的 source 信息被正确传递到最终回答
    - 引用格式验证更严格，缺少引用时触发补充检索
  - "深度思考"模式（可选）：
    - 输入框旁增加"深度思考"切换按钮
    - 开启后 Agent 使用更多轮工具调用，显式展示思考步骤（类似 NotebookLM 的分析）
  - 优化来源过滤场景下的检索：当 selected_source_ids 传入时，vector search 使用 filter 条件
- **Acceptance Criteria Addressed**: AC-4, AC-8
- **Test Requirements**:
  - `programmatic` TR-11.1: 传入 selected_source_ids 后，Qdrant 检索使用 must filter 条件
  - `programmatic` TR-11.2: 复杂问题（需要多步推理）能得到充分回答，不因 3 轮限制而过早终止
  - `programmatic` TR-11.3: 所有回答包含至少一个有效引用（拒答场景除外）
  - `programmatic` TR-11.4: 所有现有测试通过，新增测试覆盖
- **Notes**: 深度思考模式默认关闭，用户主动开启后才触发。不改变 CRAG 阈值。

## [ ] Task 12: 集成测试 + 浏览器验证 + 文档更新
- **Priority**: high
- **Depends On**: All previous tasks
- **Description**:
  - 端到端流程验证：
    1. 创建课程 → 上传材料 → 等待处理完成
    2. 查看课程摘要 → 点击建议问题
    3. 勾选/取消来源 → 提问 → 验证回答只引用勾选来源
    4. 保存回答到笔记 → 勾选笔记作为来源 → 提问
    5. 点击引用 → 查看原文预览
    6. 切换到超级备考模式 → 走一遍复习流程
    7. 打开知识图谱 → 点击节点查看详情
    8. Studio 面板各工具点击响应
  - 修复视觉对齐问题、交互bug
  - 性能检查：三栏布局下页面滚动流畅、聊天响应无明显延迟
  - 更新 docs/architecture.md 反映新架构变化
  - 运行完整后端测试套件 + 前端构建
  - Git 提交（遵循 HEC-2）
- **Acceptance Criteria Addressed**: AC-14, AC-15
- **Test Requirements**:
  - `programmatic` TR-12.1: `uv run pytest tests/ -v` 100% 通过
  - `programmatic` TR-12.2: `cd frontend && npm run build` 无 TS 错误，构建成功
  - `human-judgement` TR-12.3: 端到端核心流程顺畅无阻断 bug
  - `human-judgement` TR-12.4: 视觉质量达到 NotebookLM 类似的精致感
  - `programmatic` TR-12.5: architecture.md 已更新
