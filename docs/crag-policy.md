# CRAG Boundary Policy

CRAG is FoxSay's core differentiation: the assistant answers only when retrieved course materials justify an answer.

## Thresholds
| Retrieval score | Behavior | Requirement |
| --- | --- | --- |
| `score >= 0.72` | Normal answer | Include citations from course materials. |
| `0.55 <= score < 0.72` | Cautious answer | Expand retrieval, mark confidence as `ambiguous`, and avoid unsupported claims. |
| `score < 0.55` | Refusal | Do not answer. Return a course-scoped refusal. |

## Refusal Shape
Use this semantic shape:

```text
这个问题超出了[课程名]的范围，我不知道。
```

The exact UI copy may vary with the fox persona, but it must preserve the meaning: out of course scope, no answer.

## Citation Requirements
Every non-refusal answer must include citations that identify source material and position:

```text
来自 [文件名] · 第X部分
```

If the source position is not yet known, the system should expose the best available locator and mark the answer as incomplete for debugging rather than inventing a locator.

## Debug Metadata
Backend responses should preserve:
- `course_id`
- relevance score
- confidence status
- retrieval source identifiers
- refusal reason when refused

Production UI may hide debug fields, but tests should assert that the metadata exists.

