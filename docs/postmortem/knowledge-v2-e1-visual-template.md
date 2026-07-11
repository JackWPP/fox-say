# Knowledge V2 E1：视觉验收记录（模板）

> 此文件是一次获批准的真实运行的脱敏记录模板，不代表 E1 已执行或通过。
> 默认命令是离线 fake VLM rehearsal；只有显式 `--real` 才允许一个 SiliconFlow VLM 请求。

- 日期（Asia/Shanghai）：`待填`
- 执行人：`待填`
- 代码 revision / commit：`待填`
- 命令：`cd backend && uv run python -m scripts.knowledge_v2_e1_visual --real`
- 模式：`--real；真实单 asset、单请求；非 offline rehearsal`
- 数据：临时生成的无敏感线性代数坐标轴/向量 PNG；不含用户材料

## 成本与时延

| 项 | 观测 |
| --- | --- |
| provider / model | `待填` |
| 请求数 | 必须为 `1` |
| visual job token cap | 必须不超过 `4000` |
| reserved / accounted tokens | `待填` |
| input / output / total token | `待填`（未知则明确 usage unavailable） |
| elapsed ms | `待填` |

## 运行结果

| 项 | 观测 |
| --- | --- |
| `visual_analysis` job | `待填` |
| model-call audit | `待填` |
| visual result count | 必须为 `1` |
| 临时 SQLite / uploads / PNG | `待填：已清理` |

## 边界检查

- [ ] 只选择一个当前课程、当前 revision 的 parser asset；不从上传或索引流程自动触发。
- [ ] 仅有一个 visual model audit；未发生 SDK/worker 隐式重试。
- [ ] 结果仍是隔离的 visual result，未直接写入 Fragment、Atom、Term、KC 或 Relation。
- [ ] 未提交 SQLite、上传文件、图片、prompt、完整模型输出或 API key。
- [ ] 失败时记录可见 error code/detail，停止而不扩大请求范围。

## 结论

`待填：仅描述本次小型合成图像；不得外推为真实课程 SLA。`
