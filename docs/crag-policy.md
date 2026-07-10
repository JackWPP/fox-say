# CRAG 边界策略

CRAG(Confidence-based Retrieval-Augmented Generation)是 FoxSay 的核心差异化机制:根据检索到的课程材料的置信度,动态调整回答策略。

## 阈值
| 检索分数 | 置信状态 | 行为 | 要求 |
| --- | --- | --- | --- |
| `score >= 0.72` | `grounded` | 正常回答 | 包含来自课程材料的引用。 |
| `0.55 <= score < 0.72` | `ambiguous` | 谨慎回答 | 扩大检索,标注置信状态为 `ambiguous`,回答时注明材料覆盖度有限。 |
| `score < 0.55` | `out_of_scope` | 透明补充 | 课程材料未覆盖此内容。可基于通用知识回答,但必须声明"课程材料中未覆盖此内容,以下为通用理解,建议对照教材确认",并标注 `answer_source: "supplementary"`。 |

## 补充回答文案形态
当材料不足以支撑回答时,使用以下语义形态:

```text
课程材料中没有覆盖这部分内容,以下是通用理解,建议对照教材确认:[回答内容]
```

UI 文案可随狐狸人设调整,但语义必须保留:明确告知学生信息来源不是课程材料。

## 引用要求
基于课程材料的回答应包含能定位到来源材料和位置的引用:

```text
来自 [文件名] · 第X部分
```

标注为"补充说明"的内容不强制要求引用,但应鼓励学生对照教材确认。

如果来源位置尚未可知,系统应暴露最佳的可用定位信息,并把回答标记为不完整以供调试,而不是编造一个定位。

## 调试元数据
后端响应应保留:
- `course_id`
- relevance score(相关性分数)
- `confidence_status`(置信状态:`grounded` / `ambiguous` / `out_of_scope`)
- `answer_source`(回答来源:`"material"` / `"supplementary"`)
- retrieval source identifiers(检索来源标识)
- 材料不足时的补充说明标记

生产 UI 可以隐藏调试字段,但测试必须断言这些元数据存在。
