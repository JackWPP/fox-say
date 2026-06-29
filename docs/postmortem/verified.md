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

- [已验证] `https://mineru.net/api/v1/agent` — MinerU Agent 轻量解析 API（无需 token，IP 限频），通过 pipeline.py fallback 路径验证 — 2026-06
  - 注意：mineru.py 存在 HEC-1 静默吞错问题，已于本次修复改为返回 `(content, error)` tuple

## 文档解析统一入口

- [已验证] `markitdown[all]` 0.1.5 — 微软开源的统一文档转 Markdown 工具，支持 PDF/PPT/Word/HTML/图片等格式。通过 `uv sync` 安装并 `python -c "from markitdown import MarkItDown"` 实际导入验证 — 2026-06
  - 用途：作为 parsing.py 的统一解析入口（Layer 1），失败时回退到 pdfplumber/python-pptx（Layer 2），PDF/图片最后走 MinerU 云端 OCR（Layer 3）
- [未验证] MinerU API 对图片（PNG/JPG）的 OCR 支持 — mineru.py 现有实现针对 PDF，图片走 MinerU 需实测。若不支持则 image kind 暂走 markitdown 的图片描述能力（质量较低）— 2026-06
