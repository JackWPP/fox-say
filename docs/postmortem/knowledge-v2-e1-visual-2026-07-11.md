# Knowledge V2 E1：真实 VLM 合成视觉验证

- 日期：2026-07-11（Asia/Shanghai）
- 输入：临时 SQLite、临时 uploads 与合成线性代数示意图；未上传用户图片，临时资源已清理。
- 模式：`uv run python -m scripts.knowledge_v2_e1_visual --real`
- 凭证：通过环境配置解析的 SiliconFlow 凭证；未记录或输出密钥。

| 项目 | 结果 |
| --- | --- |
| Provider / Model | SiliconFlow / `Qwen/Qwen3.6-27B` |
| 请求数 / 资产数 | 1 / 1 |
| visual job / audit | `succeeded` / `succeeded` |
| 输入 / 输出 / 总 token | 132 / 76 / 208 |
| 预留 token | 3600 |
| 模型耗时 | 3105 ms |
| 结果数 | 1 |
| 临时 DB/uploads 清理 | true |

视觉任务仍默认关闭，只有显式选择解析未覆盖的资产后才允许入队。该结果仅验证 endpoint、审计、预算、lease 和合成图路径，不能外推为真实课程图片的 SLA。
