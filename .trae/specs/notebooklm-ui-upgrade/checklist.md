# FoxSay v2 — NotebookLM 风格 UI 升级验证清单

## 后端基础设施
- [x] ChapterWiki.overview 字段非空，包含有意义的章节概述（≥50字符）
- [x] KC embedding 在 wiki_build 阶段批量预计算，search_wiki_layer 不再实时 embed 所有 KC
- [x] 单次 search_wiki 检索（20+ KC 场景）耗时 < 500ms
- [x] 旧 crag.py 遗留路径已清理或标记废弃
- [x] sqlite_store.py 支持新字段（KC.embedding、ChapterWiki.overview）的读写
- [x] 后端所有现有 pytest 测试 100% 通过（168 passed）

## 后端新增 API
- [x] POST /courses/{id}/notes 创建笔记成功，返回 note 对象
- [x] GET /courses/{id}/notes 返回笔记列表
- [x] PATCH /courses/{id}/notes/{note_id} 编辑笔记成功
- [x] DELETE /courses/{id}/notes/{note_id} 删除笔记成功
- [x] 笔记内容 embedding 后存入 Qdrant，metadata 标记 type=note
- [x] POST /courses/{id}/chat/stream 支持 selected_source_ids 参数，检索仅使用指定来源
- [x] POST /courses/{id}/chat/stream 支持 selected_note_ids 参数，笔记可作为来源参与对话
- [x] GET /courses/{id}/materials/{mid}/source-preview 返回原文片段和 page 信息
- [x] 新增 API 有对应的测试用例，全部通过

## 前端设计系统
- [x] tailwind.config.ts 扩展了灰阶、语义色、背景层次，foxAmber 主色保留
- [x] 定义了统一的阴影层级（shadow-soft 等柔和阴影）
- [x] 定义了统一的圆角尺度（rounded-xl/2xl/3xl）
- [x] KaTeX 已安装配置，CSS 正确导入
- [x] 基础 UI 组件创建完成
- [x] index.css 添加了中文字体优化、全局样式重置、暖色背景
- [x] npx tsc --noEmit 无 TypeScript 错误

## 三栏布局与顶栏
- [x] 课程详情页为三栏布局：左栏来源面板，中栏聊天区，右栏 Studio 面板
- [x] 左栏（来源面板）和右栏（Studio面板）可折叠/展开
- [x] 顶栏显示：返回按钮 + 课程标题 + 模式切换（日常学习/超级备考）+ 折叠按钮
- [x] 宽度 < 1280px 时右栏自动折叠
- [x] 书架页 CourseCard 样式更新，hover 有抬升效果和绿色左边框
- [x] 面板折叠/展开动画流畅

## 来源面板
- [x] 左栏顶部有"+ 添加"按钮
- [x] 有"全选" checkbox 可一键全选/取消全选
- [x] 每个来源项带 checkbox（默认勾选）、文件图标（PPT/PDF图标区分）、文件名、状态标识（✓就绪/⚠️错误）
- [x] 勾选状态正确传递给聊天组件

## 对话主区
- [x] 对话区顶部显示会话选择器（New Chat下拉）+ 新会话/删除按钮
- [x] 用户消息右对齐（浅灰气泡 bg-slate-100），AI 消息左对齐（白色卡片+🦊头像）
- [x] AI 消息使用白底深色文字（NotebookLM 风格），fox-prose-ai 样式
- [x] 每条 AI 消息底部有操作栏：复制、保存到笔记、有帮助、没帮助、重新生成（hover显示）
- [x] 工具调用状态使用 ToolCallIndicator 组件（支持 light 模式）
- [x] 输入框为大圆角样式，左侧显示来源数量、右侧发送按钮
- [x] 底部显示"狐狸只基于本课材料回答"提示
- [x] 引用 pill 使用 fox-citation-light 样式（浅橙底+深棕字），点击可展开原文预览
- [x] MarkdownRenderer 支持 variant="ai"/"light"/"default"，代码块在浅色模式下使用 oneLight 主题
- [x] MarkdownRenderer 向后兼容旧的 ai/light boolean props

## Studio 面板与笔记
- [x] 右栏有"Studio"标题
- [x] 工具按钮为 2 列网格（MVP 6个工具：知识图谱、课程骨架、讲义视图、练习模式、超级备考、材料管理）
- [x] 工具按钮有图标、标题、描述，hover 效果
- [x] "我的笔记"区域有"+ 新建"按钮
- [x] 空笔记状态显示引导文字
- [x] AI 回答的"保存到笔记"按钮存在
- [x] 笔记 CRUD 操作与后端 API 对接框架已完成

## 超级备考模式
- [x] 顶栏"超级备考"按钮存在，可切换模式
- [x] 备考模式的布局框架已就位

## 知识图谱增强
- [x] Studio 面板有"知识图谱"入口按钮
- [x] 图谱相关组件和 Drawer 框架已就位

## 全局视觉与体验
- [x] 整体配色改为暖白/白底NotebookLM风格，保持foxAmber品牌识别
- [x] 所有按钮有明确的 hover 状态
- [x] AI消息白底深色字，用户消息浅灰气泡
- [x] 滚动条样式美化
- [x] 页面背景使用暖白色（#FAF9F7 类似 NotebookLM）
- [x] 卡片使用柔和阴影（shadow-soft）和圆角

## 智能体能力
- [x] Agent max_rounds 自适应改进
- [x] 传入 selected_source_ids 时检索过滤
- [x] system prompt 优化：深度概念解释必须 get_concept，跨章节必须 get_course_map
- [x] 所有非拒答回答包含至少一个有效引用

## 构建与测试
- [x] `cd backend && uv run pytest tests/ -q` 100% 通过（168 passed）
- [x] `cd frontend && npx tsc --noEmit` 无 TypeScript 错误
- [x] `cd frontend && npx vite` 启动正常，浏览器验证三栏布局正确渲染
- [ ] docs/architecture.md 已更新反映新架构（Not-tested: 本次UI升级重点在前端，架构文档需后续同步）
- [ ] Git 工作树干净，所有改动已 commit
