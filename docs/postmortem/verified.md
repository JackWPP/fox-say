# 已验证外部依赖记录

> 本文件遵循 AGENTS.md HEC-5：引入任何外部依赖标识符（模型名 / endpoint / config key）前，
> 必须在此文件写一行"已验证"记录。任何"我觉得应该是这样"的推测必须标注 `[未验证]`。

## LLM 模型

- [已验证] `deepseek-v4-flash` — DeepSeek 2026 V4 Flash 模型，通过 agent.py / wiki_builder.py / review.py / skeleton.py 实际调用验证（生成端主力模型） — 2026-06
- [已验证] `deepseek-v4-pro` — DeepSeek 2026 V4 Pro 模型，DeepSeek 官方文档确认存在，兼容同一 API — 2026-06
- [已验证] `deepseek-chat` — DeepSeek 兼容模型名，兼容到 2026/07/24 — 2026-06
- [已验证] `deepseek-reasoner` — DeepSeek 推理模型，兼容到 2026/07/24 — 2026-06

## LLM API Endpoint

- [已验证] `https://api.deepseek.com` — DeepSeek API base URL（OpenAI 兼容），通过 agent.py / wiki_builder.py 等多处实际调用验证 — 2026-06

## VLM 模型与 API Endpoint

- [已验证] `Qwen/Qwen3.6-27B` — SiliconFlow OpenAI 兼容 Chat Completions 接口中的精确模型 ID。2026-07-11 使用仓库公开 README 资产 `assets/readme/logo_foxsay.jpg`（JPEG，1024×1024）以 `image_url` data URI + 文本消息完成最小多模态调用；模型返回非空最终内容，证明可接收当前 `vlm_parser.py` 所使用的图片载荷形态。
  - 验证凭证：本地已有的 `EMBEDDING_API_KEY`（只用于本次兼容性验证；未记录、未输出或提交凭证）。`/models` 返回 91 个模型，包含该精确 ID。
  - 成功请求参数与观测：`extra_body={"enable_thinking": false}`、`max_tokens=64`；耗时 1,086 ms，usage 为 prompt 1,051 / completion 7 / total 1,058 tokens。响应未提供货币成本，单价因此为 `[未验证]`。
  - 行为约束：未显式关闭 thinking 时，两次受控请求（`max_tokens=32`、`256`）均以 `finish_reason=length` 结束，最终 `content` 为空，输出预算被 `reasoning_content` 消耗。因此图片转 Markdown 的生产调用必须显式选择“关闭 thinking”或为推理与最终答案分别设置可审计的 token 预算，不能依赖默认行为。
- [已验证] `https://api.siliconflow.cn/v1` — 对上述 VLM 模型可用的 OpenAI 兼容 API base URL；除既有 embedding 验证外，已在 2026-07-11 通过真实图片 Chat Completions 调用验证。

### VLM 接入实现（2026-07-11）

- [已实施] `backend/app/core/config.py` 通过独立的 `VLM_API_KEY`、`VLM_API_BASE`、`VLM_MODEL`、`VLM_MAX_TOKENS` 配置 VLM；默认 base/model 为上述已验证的 SiliconFlow / Qwen 组合，默认输出上限为 2,048 tokens。不会再把 embedding 或 DeepSeek 字段作为 VLM 的事实源。
- [已实施] `backend/app/services/vlm_parser.py` 保留 data-URI 图片载荷，使用独立的 VLM 配置，并传入 `extra_body={"enable_thinking": false}` 和可配置的 `max_tokens`。未配置 `VLM_API_KEY`、空内容和 API 异常都会抛出可见的 `DocumentParsingException`。
- [已实施] `backend/tests/test_vlm_parser.py` 以 mock 覆盖配置、载荷、模型/endpoint、关闭 thinking、缺少 key、空内容和 API 异常。真实 API 冒烟测试不进入常规 CI。
- [未实施] 当前 legacy 图片路由仍使用 MinerU；本次没有改动 `parsing.py`、pipeline 或路由，是否将已配置的 VLM parser 纳入图片路由需在后续任务中显式决定。

## Embedding 模型

- [已验证] `BAAI/bge-m3` — SiliconFlow 托管的 BGE-M3 embedding 模型，通过 embedding.py 实际调用验证 — 2026-06

## Embedding API Endpoint

- [已验证] `https://api.siliconflow.cn/v1` — SiliconFlow API base URL（OpenAI 兼容），通过 embedding.py 实际调用验证 — 2026-06

## Judge 模型（评测 / 轻量分类）

- [已验证] `qwen/qwen3.5-9b` — LM Studio 本地部署的 Qwen3.5 9B（OpenAI 兼容），通过 DeepEval Judge / prereq 二审调用验证 — 2026-06
- [已验证] `qwen/qwen3-4b-2507` — LM Studio 本地部署的 Qwen3-4B（OpenAI 兼容），轻量分类端验证 — 2026-06
- [已验证] `qwen3-reranker-0.6b` — Qwen3 reranker 模型，reranker 路径验证 — 2026-06
- [已验证] `http://localhost:1234/v1` — LM Studio 本地 API endpoint（OpenAI 兼容） — 2026-06

## PDF 解析

- [已验证] `https://mineru.net/api/v1/agent` — MinerU V1 Agent 轻量解析 API（无需 token，IP 限频），作为 V4 额度耗尽时的降级路径 — 2026-06
- [已验证] `https://mineru.net/api/v4/file-urls/batch` — MinerU V4 批量上传 API（JWT 鉴权），PRIMARY 解析路径，支持 PDF/DOCX/DOC/PPTX/PPT 等格式，1000 pages/day 额度 — 2026-07
  - 注意：mineru.py 已从 V1-only 升级为 V4/V1 hybrid，V4 优先，额度耗尽自动降级到 V1
  - mineru.py 存在过 HEC-1 静默吞错问题，已修复为返回 `(content, error)` tuple

## 文档解析统一入口

- [已验证] `markitdown[all]` 0.1.5 — 微软开源的文档转 Markdown 工具，支持 PDF/PPT/Word/HTML/图片等格式。通过 `uv sync` 安装并 `python -c "from markitdown import MarkItDown"` 实际导入验证 — 2026-06
  - 用途变更 (2026-07)：**不再是统一解析入口**。现仅用于 XLSX 解析（MinerU V4 不支持 XLSX），以及 Word 文件的 MinerU fallback 路径。PDF/Office 文件 PRIMARY 走 MinerU V4/V1 hybrid。
- [未验证] MinerU API 对图片（PNG/JPG）的 OCR 支持 — mineru.py 现有实现针对 PDF，图片走 MinerU 需实测。若不支持则 image kind 暂走 VLM 多模态分支 — 2026-06

## 文档解析扩展依赖

- [已验证] `docling` — IBM 开源文档解析库（电子版 PDF 结构提取 + TableFormer 表格识别），通过 `uv sync` 安装并 `from docling.document_converter import DocumentConverter` 实际导入验证 — 2026-07
  - 用途：电子版 PDF 的 fallback 解析器（MinerU 失败时启用）
- [已验证] `langchain-text-splitters` — LangChain 文本切块库，通过 `uv sync` 安装并 `from langchain_text_splitters import MarkdownHeaderTextSplitter` 实际导入验证 — 2026-07
  - 用途：替换原 500 字符盲切，使用 MarkdownHeaderTextSplitter 按标题层级语义切块 + 表格不可分割保护
- [已验证] `PyMuPDF (fitz)` v1.26.4 — PDF 处理库，通过 `uv sync` 安装并 `import fitz` 实际导入验证 — 2026-07
  - 用途：pdf_detector.py 中快速探测 PDF 是电子版还是扫描件（>30% 页面文字 <20 字符且有图片 → 扫描件）
