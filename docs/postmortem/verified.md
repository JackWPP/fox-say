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
