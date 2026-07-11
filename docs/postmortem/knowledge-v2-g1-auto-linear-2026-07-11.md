# Knowledge V2 G1：真实自动线性代数链路

- 日期：2026-07-11（Asia/Shanghai）
- 输入：临时 SQLite 与合成线性代数材料；未上传用户材料，临时库已清理。
- 模式：`uv run python -m scripts.knowledge_v2_g1_auto_linear --real`
- 请求上限：1；semantic job/course token cap 均为 4000。

## 观测

| 项目 | 结果 |
| --- | --- |
| Provider / Model | DeepSeek / `deepseek-v4-flash` |
| 请求数 | 1 |
| D0 / Semantic / Term / KC | 均 `succeeded` |
| Semantic Atom / Term / KC | 1 / 1 / 1 |
| 输入 / 输出 / 总 token | 145 / 276 / 421 |
| 预留 token | 1963 |
| 模型耗时 | 3295 ms |
| 临时 DB 清理 | true |

关系抽取与视觉分析均保持显式 opt-in，本次没有调用。该小样本只验证自动调度、审计和成本边界，不能当作真实课程的延迟或成本 SLA。
