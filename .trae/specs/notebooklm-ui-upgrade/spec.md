# FoxSay v2 — NotebookLM 风格 UI 升级 + 智能体能力增强 PRD

## Overview
- **Summary**: 参考 Google NotebookLM 的三栏沉浸式布局与交互范式，全面重构 FoxSay 前端 UI 设计体系，同时修复后端已知性能瓶颈与功能缺陷，强化知识理解深度和问答质量，打造更像 NotebookLM 的"超级备考、超级学习智能体"体验。
- **Purpose**: 
  1. 当前 UI 是传统单栏 CRUD 布局，tab 切换割裂体验，缺少 NotebookLM 那种沉浸式工作台感觉
  2. 视觉设计不够精致，缺少现代感、微交互和"fancy"的质感
  3. 后端存在已知性能问题（search_wiki_layer 实时 embed）和功能缺失（ChapterWiki.overview 空、CitationCard 不跳原文）
  4. 智能体能力有提升空间：笔记功能、来源选择、更深层的知识关联
- **Target Users**: 中国本科生期末抱佛脚场景，需要沉浸式 AI 学习陪伴体验

## Goals
1. **布局重构**：实现 NotebookLM 风格三栏布局（来源面板 + 对话主区 + Studio 工具面板）
2. **视觉升级**：全面提升 UI 质感，包括配色体系、阴影层级、圆角规范、微交互动画、字体排版
3. **超级备考模式重设计**：将备考体验从"生成计划列表"升级为沉浸式主线推进体验
4. **Studio 工具面板**：右侧面板聚合知识图谱、思维导图、闪卡、笔记、讲义生成等工具
5. **笔记系统**：支持保存回答到笔记、笔记检索、笔记作为来源参与对话
6. **来源管理增强**：对话时可见来源列表，支持勾选/过滤来源参与回答
7. **后端性能修复**：修复 ChapterWiki.overview 空问题、search_wiki_layer 批量 embed 优化、CitationCard 原文跳转
8. **智能体能力增强**：改进 ReAct 循环工具使用、增加"深度思考"模式、改进引用精度
9. **异步处理状态可视化**：优雅展示材料处理、笔记生成、复习计划生成的进度状态

## Non-Goals (Out of Scope)
- 多用户/账号体系/协作功能（MVP 边界外）
- 课程胶囊分享/社区广场
- 移动端适配（P2，PC Web 优先）
- FSRS/SRS 间隔重复算法（留接口不实现）
- 图片 OCR 处理（已有 docling 路径，但本期不专门攻坚）
- 出卷功能/诊断 15 题
- 更换 LLM 模型（保持现有 DeepSeek + Qwen 分工）

## Background & Context

### 现有实现分析
- **当前布局**：单栏 max-w-4xl 居中，顶栏只有 logo，传统 Tab 切换（材料/骨架/问答/图谱/讲义/练习/备考）
- **当前配色**：只有三个颜色 foxAmber(#F59E0B) / midnightCharcoal(#111317) / warmWhite(#FFF7ED)
- **当前组件**：lucide-react 图标，reactflow 知识图谱，基本的 markdown 渲染
- **已知问题**（来自 HANDOFF.md §12）：
  - ChapterWiki.overview 是空字符串（P1）
  - search_wiki_layer 实时 embed 所有 KC（性能瓶颈）
  - CitationCard 不跳原文（缺 endpoint + PDF preview）
  - 前端 KG tab nodes 颜色不接 mastery
  - 旧 crag.py 路径待清理

### NotebookLM 设计要素参考（从截图提取）
1. **三栏布局**：左 240px（来源）/ 中 flex-1（对话，居中 max-w-3xl）/ 右 280px（Studio）
2. **顶栏**：左侧 Notebook 标题，右侧操作按钮（创建笔记本、分析、分享、设置、PRO、用户头像）
3. **来源面板**：
   - 添加来源按钮（搜索框 + 添加按钮）
   - Web/Fast Research 切换
   - 来源列表带 checkbox 勾选
   - 全选 checkbox
4. **对话主区**：
   - 居中布局，笔记本标题 + 来源数量 + 日期
   - AI 摘要卡片（自动生成的概述）
   - 摘要下方操作按钮（保存到笔记、复制、点赞、踩）
   - 建议问题按钮（3个）
   - 底部输入框（"开始输入..."），右侧显示来源数量 + 发送按钮
5. **Studio 面板**：
   - 工具按钮网格（音频概览、演示文稿、视频概览、思维导图、报告、闪卡、测验、信息图、数据表格）
   - 生成状态列表（正在生成演示文稿...基于6个来源）
   - 笔记区域（新建笔记 + 时间戳）
6. **视觉风格**：
   - 浅色系背景（#F8F9FA 淡灰蓝）
   - 卡片白色，柔和阴影
   - 圆角统一（12px-16px）
   - 按钮 hover 状态精致
   - 配色克制，以灰/白为主，点缀彩色标签
7. **交互细节**：
   - 面板可折叠/展开
   - 生成状态显示加载动画
   - 来源 hover 显示操作
   - 笔记时间戳显示

## Functional Requirements

- **FR-1: 三栏布局重构**
  - 左侧来源面板：可折叠，显示课程材料列表，支持勾选/取消勾选参与对话的来源
  - 中间对话主区：居中 max-w-3xl，笔记本式体验，显示课程标题、来源数、日期
  - 右侧 Studio 面板：可折叠，工具按钮网格 + 生成状态 + 笔记列表
  - 顶栏重构：显示课程名称，右侧操作按钮（分享、设置、模式切换）
  - 支持面板宽度拖拽调整（可选，P2）

- **FR-2: 视觉设计系统升级**
  - 扩展配色体系：增加灰阶层次、辅助色（成功/警告/错误/信息）、微妙的背景色层次
  - 阴影层级系统：定义 3-4 级阴影（sm/md/lg/xl），打造深度感
  - 圆角规范：统一 8px/12px/16px/20px 圆角尺度
  - 字体排版：优化字号层级、行高、字重，增加中文排版优化
  - 微交互动画：按钮 hover/active/focus 状态过渡、卡片悬停效果、消息入场动画、加载状态
  - 深色/浅色模式支持（可选，P2）

- **FR-3: 课程首屏自动摘要**
  - 材料处理完成后，自动生成课程摘要（类似 NotebookLM 顶部的概述卡片）
  - 摘要显示：核心概念数、章节数、来源数、日期
  - 摘要下方操作按钮：保存到笔记、复制、重新生成
  - 建议问题：3-4 个上下文相关的推荐问题

- **FR-4: 来源管理增强**
  - 对话时左侧始终可见来源列表
  - 每个来源带 checkbox，勾选表示该来源参与本次对话检索
  - 支持全选/取消全选
  - 来源 hover 显示：预览、删除、在文件夹中显示（P2）
  - 添加上传按钮常驻在来源面板顶部

- **FR-5: Studio 工具面板**
  - 工具按钮网格布局，每个工具带图标 + 名称
  - 工具包括：知识图谱、思维导图、讲义、闪卡、测验、复习计划、笔记、薄弱点分析
  - 生成中的工具显示加载状态："正在生成思维导图...基于 X 个来源"
  - 点击工具在主区或面板内展开结果
  - 笔记区域：显示笔记列表，点击查看/编辑，支持新建笔记

- **FR-6: 超级备考模式重设计**
  - 沉浸式全屏备考体验，类似 NotebookLM 但带复习主线
  - 左侧改为复习进度时间线（Day 1/Day 2/...），当前 Day 高亮
  - 主区显示当日内容：重点讲解 → 练习题 → 总结
  - 右侧 Studio 改为快速工具：查看计划、查看薄弱点、生成闪卡
  - /btw 插话以气泡形式叠加，不打断主线
  - 进度条可视化整体备考进度
  - 考试倒计时在顶栏醒目显示

- **FR-7: 笔记系统**
  - 任何 AI 回答可"保存到笔记"
  - 笔记自动关联来源引用
  - 笔记列表在右侧 Studio 面板
  - 笔记可编辑、删除、重命名
  - 笔记作为虚拟来源参与对话检索（勾选笔记作为来源）
  - 新建笔记按钮

- **FR-8: 对话体验优化**
  - 用户消息右对齐，AI 消息左对齐，类似现代聊天应用
  - 每条 AI 消息下方操作栏：复制、保存到笔记、点赞、踩、重新生成
  - 引用点击可展开查看原文片段（CitationCard 升级）
  - 引用支持跳转至原文对应位置（PDF 预览）
  - 流式输出优化：光标动画、逐字显示感
  - 工具调用状态更优雅展示（不是文字，而是图标动画）
  - 支持代码块语法高亮优化（已有 react-syntax-highlighter，优化样式）
  - 支持数学公式渲染（KaTeX，理工科必须）

- **FR-9: 后端性能与功能修复**
  - 修复 ChapterWiki.overview 空字符串问题：在 wiki_builder 中增加 overview 生成 stage
  - 优化 search_wiki_layer：KC embedding 批量预存，避免实时 embed 所有 KC
  - 新增 source content endpoint：支持按引用定位原文片段，返回 page 信息
  - 新增笔记 API：创建/列表/编辑/删除笔记，笔记参与向量检索
  - 新增来源过滤 API：chat/stream 支持传入 selected_source_ids 参数
  - 清理旧 crag.py 遗留代码
  - Agent ReAct 循环优化：max_rounds 自适应，简单问题 1 轮，复杂问题最多 5 轮

- **FR-10: 异步处理状态可视化**
  - 材料上传后显示处理进度条/步骤：解析 → 构建结构图 → 生成 Wiki → 分块 → 向量化 → 生成骨架
  - Studio 中工具生成状态实时更新
  - 处理完成后弹出"第一个惊喜"通知：已完成分析，显示核心概念和薄弱点
  - SSE 事件流在 UI 上有对应视觉反馈

- **FR-11: 知识图谱增强**
  - 图谱节点点击弹出详情 Drawer（之前是占位 alert）
  - Drawer 显示：概念定义、公式、常见错误、先修概念链接、相关来源
  - 节点颜色接 mastery_score（如果有数据）
  - 支持在图谱上直接提问该概念
  - 从 Studio 面板点击"思维导图"在主区打开全屏图谱

## Non-Functional Requirements

- **NFR-1: 性能**
  - 首屏加载时间 < 2s（本地开发环境）
  - 对话响应首字时间 < 1.5s（流式）
  - search_wiki_layer 检索延迟 < 500ms（优化后，之前可能数秒）
  - 三栏布局切换流畅，无卡顿
  - 面板展开/折叠动画 60fps

- **NFR-2: 视觉质量**
  - 所有交互元素有明确的 hover/active/focus 状态
  - 配色符合 WCAG 2.1 AA 对比度标准
  - 动画时长 150-300ms，缓动函数自然（cubic-bezier）
  - 响应式：在 1280px-2560px 宽度范围内表现良好
  - 保持 foxAmber 主色调品牌识别

- **NFR-3: 代码质量**
  - 遵循现有 AGENTS.md HEC 约束
  - TypeScript 类型完整，无 any（尽量）
  - React 组件拆分合理，单文件不超过 400 行
  - Tailwind 类名组织清晰，可提取组件类
  - 后端新增 API 必须有测试
  - 不引入不必要的新依赖（HEC-4）

- **NFR-4: 兼容性**
  - Chrome/Edge 最新两个版本
  - 不支持 IE
  - Windows/macOS 桌面浏览器

## Constraints

- **Technical**: 
  - 必须使用现有技术栈：Vite + React + TypeScript + Tailwind（前端），FastAPI + Python + uv（后端）
  - 向量库保持 Qdrant，不更换
  - LLM 保持 DeepSeek V4 Flash + Qwen3.5/4b 分工
  - 不引入重量级 UI 框架（如 MUI/Ant Design），保持 Tailwind 原子化
  - 允许引入轻量工具库（如 dnd-kit 拖拽、floating-ui 弹出层、katex 公式）

- **Business**:
  - 保持 MVP 边界，不做 scope creep
  - 保持"课程"原子单位隔离
  - 保持 CRAG 门控策略（0.72/0.55 阈值）
  - 所有回答必须带来源引用

- **Dependencies**:
  - 现有 API 契约尽量兼容，新增字段可选
  - SQLite 数据库迁移需要向后兼容
  - 现有测试套件必须全部通过

## Assumptions

- 用户主要在 PC Web 浏览器使用，屏幕宽度 ≥ 1280px
- 不需要支持移动端（一期）
- 现有 DeepSeek API 和 Qwen 本地模型可用
- Qdrant 向量库运行正常
- 允许新增少量 npm 包（如 katex、@dnd-kit/core、floating-ui 等）
- ChapterWiki.overview 可以通过补充 wiki_builder 的 stage 来生成，不需要重写整个 pipeline
- 笔记作为新表存储，embedding 后存入 Qdrant 对应 course collection

## Acceptance Criteria

### AC-1: 三栏布局实现
- **Given**: 用户进入某课程详情页
- **When**: 页面加载完成
- **Then**: 显示三栏布局：左侧来源面板、中间对话区、右侧 Studio 面板
- **Verification**: `human-judgment`
- **Notes**: 三栏比例约为 240px : 1fr (max-w-3xl 居中) : 280px；左右面板可折叠

### AC-2: 视觉设计升级
- **Given**: 用户浏览任意页面
- **When**: 观察界面元素
- **Then**: 按钮、卡片、输入框有一致的圆角、阴影、间距规范；hover 状态有平滑过渡；配色层次丰富但不杂乱
- **Verification**: `human-judgment`

### AC-3: 课程自动摘要
- **Given**: 课程材料处理完成
- **When**: 用户进入课程对话页
- **Then**: 对话区顶部显示课程摘要卡片（标题、来源数、日期、自动生成的概述），下方有保存/复制/建议问题按钮
- **Verification**: `programmatic` + `human-judgment`

### AC-4: 来源勾选过滤
- **Given**: 用户在对话页
- **When**: 取消勾选某些来源，然后发送问题
- **Then**: 后端检索仅使用勾选的来源；回答引用只来自勾选的来源
- **Verification**: `programmatic`

### AC-5: Studio 工具面板
- **Given**: 用户在课程页
- **When**: 查看右侧面板
- **Then**: 可见工具网格（知识图谱、思维导图、讲义、闪卡、测验、复习计划、笔记等），每个工具可点击
- **Verification**: `human-judgment`

### AC-6: 超级备考沉浸模式
- **Given**: 用户点击"超级备考"按钮
- **When**: 进入备考模式
- **Then**: 界面切换为备考布局：左侧进度时间线、主区复习内容、右侧快速工具；/btw 插话以气泡形式叠加
- **Verification**: `human-judgment`

### AC-7: 笔记保存与检索
- **Given**: AI 回答了一个问题
- **When**: 用户点击"保存到笔记"
- **Then**: 笔记出现在右侧 Studio 面板；该笔记可勾选作为来源参与后续对话
- **Verification**: `programmatic` + `human-judgment`

### AC-8: 引用原文跳转
- **Given**: AI 回答中包含引用
- **When**: 用户点击引用 pill
- **Then**: 展开显示原文片段预览；若有 page 信息可跳转查看
- **Verification**: `programmatic` + `human-judgment`

### AC-9: ChapterWiki.overview 修复
- **Given**: 课程材料处理完成
- **When**: 请求章节大纲或生成摘要
- **Then**: ChapterWiki.overview 不为空字符串，包含有意义的章节概述
- **Verification**: `programmatic`

### AC-10: search_wiki_layer 性能优化
- **Given**: 课程有 ≥ 20 个 KC
- **When**: 执行 search_wiki 检索
- **Then**: 单次检索耗时 < 500ms（不包括 LLM 生成时间）
- **Verification**: `programmatic`

### AC-11: 数学公式渲染
- **Given**: AI 回答包含 LaTeX 公式（如线性代数中的矩阵、特征值公式）
- **When**: 渲染回答
- **Then**: 公式正确渲染为数学符号，不是原始 LaTeX 文本
- **Verification**: `human-judgment`

### AC-12: 处理进度可视化
- **Given**: 用户上传材料后
- **When**: 后端 pipeline 执行各步骤
- **Then**: UI 显示当前步骤（解析/构建 Wiki/向量化等）和进度状态
- **Verification**: `human-judgment`

### AC-13: 知识图谱节点详情
- **Given**: 知识图谱已加载
- **When**: 用户点击某个节点
- **Then**: 弹出 Drawer 显示概念详情（定义、公式、先修、来源、提问按钮）
- **Verification**: `human-judgment`

### AC-14: 后端测试通过
- **Given**: 代码修改完成
- **When**: 运行 `uv run pytest tests/ -v`
- **Then**: 所有原有测试 + 新增测试全部通过
- **Verification**: `programmatic`

### AC-15: 前端构建通过
- **Given**: 前端代码修改完成
- **When**: 运行 `npm run build`
- **Then**: TypeScript 类型检查通过，Vite 构建成功无错误
- **Verification**: `programmatic`

## Open Questions

- [ ] 是否需要引入 UI 组件库（如 shadcn/ui、Radix UI）来加速高质量组件开发？还是全部用 Tailwind 手写？
- [ ] KaTeX 数学公式渲染是否需要宏包支持（线性代数常用矩阵、行列式等）？
- [ ] 来源 PDF 预览是用 PDF.js 内嵌还是新窗口打开？
- [ ] 面板宽度是否需要用户可拖拽调整？还是固定宽度即可？
- [ ] 深色模式是否在本期实现？还是作为 P2？
- [ ] 笔记是否支持 Markdown 富文本编辑，还是纯文本？
- [ ] 现有 OnboardingPage（3步引导）是否需要同步重设计？
