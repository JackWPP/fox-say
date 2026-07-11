# Knowledge V2 G0：DeepSeek 合成线性代数 Smoke

- 日期：2026-07-11（Asia/Shanghai）
- 目的：验证 D0 → explicit `extract_semantic_atoms` → D1a audit → D1b1 evidence-pinned publish 的真实模型链路。
- 数据：临时 SQLite 与一条合成英文“向量空间对加法、标量乘法封闭”的 fragment；未读取、上传或保留用户课程材料。
- 配置来源：本地 `.env`，密钥未读取、打印或提交。

## 结果

| 项 | 观测 |
| --- | --- |
| Provider / model | DeepSeek / `deepseek-v4-flash` |
| 请求数 | 1 |
| job 状态 | `succeeded` |
| Atom 数 | 2 |
| audit 状态 | `succeeded` |
| usage source | `provider` |
| input / output / total tokens | 154 / 893 / 1047 |
| accounted tokens | 1047 |
| elapsed | 10,534 ms |
| error | 无 |

## 边界结论

1. 模型结果经严格 JSON candidate、D0 section、current fragment、同 job audit 与 lease 校验后才发布 Atom。
2. 该观测仅覆盖小型合成输入；不能外推为真实课程的 p50/p95、平均成本或自动调度默认值。
3. G0 未测试 VLM、embedding、Term/KC/Relation、聊天/Agent 迁移或自动 enqueue；这些仍由后续任务单独验收。
