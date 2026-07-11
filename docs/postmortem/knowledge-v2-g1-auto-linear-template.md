# Knowledge V2 G1：自动线性代数验收记录（模板）

> 此文件是一次获批准的真实运行的脱敏记录模板，不代表 G1 已执行或通过。
> 执行前确认只使用临时 SQLite、合成材料、单一课程和单一语义模型请求。

- 日期（Asia/Shanghai）：`待填`
- 执行人：`待填`
- 代码 revision / commit：`待填`
- 命令：`cd backend && uv run python -m scripts.knowledge_v2_g1_auto_linear --real`
- 模式：`--real；真实单请求；非 offline rehearsal`
- 数据：合成线性代数材料；不含用户材料

## 成本与时延

| 项 | 观测 |
| --- | --- |
| provider / model | `待填` |
| 请求数 | 必须为 `1` |
| semantic job token cap | `待填` |
| course token cap | `待填` |
| input / output / total token | `待填`（未知则明确 usage unavailable） |
| accounted tokens | `待填` |
| elapsed ms | `待填` |

## 自动链路结果

| 阶段 | job 状态 | 产物 |
| --- | --- | --- |
| D0 `compile_course` | `待填` | source-pinned outline |
| D1 `extract_semantic_atoms` | `待填` | Atom count: `待填` |
| D2a `compile_terms` | `待填` | Term count: `待填` |
| D3a `compile_kcs` | `待填` | KC count: `待填` |

## 边界检查

- [ ] 仅有一个 semantic model audit；未发生 SDK/worker 隐式重试。
- [ ] semantic job 由 D0 atomic auto-enqueue，Term/KC job 由上游成功投影 auto-enqueue。
- [ ] 所有 job 的 source/knowledge revision 一致，且均为 `succeeded`。
- [ ] 临时 SQLite 与合成材料已清理；未提交数据库、prompt、材料、API key 或完整模型输出。
- [ ] 失败时记录可见 error code/detail，停止而不扩大请求范围。

## 结论

`待填：仅描述本次小型合成输入；不得外推为真实课程 SLA。`
