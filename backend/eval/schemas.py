"""评测脚手架的辅助 schema。

EvalCase 从 app.schemas.foxsay import,本文件只追加 runner/judge
等模块需要的辅助 dataclass,**绝不在这里重定义 EvalCase**。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

# ★ PR0 contract:从 app.schemas.foxsay 共享 EvalCase + Citation
# (line B 消费 PR0 schema,不在本文件重定义字段,避免双源不一致)
from app.schemas.foxsay import Citation, EvalCase  # noqa: F401

QuestionType = Literal[
    "definition", "derivation", "cross_chapter", "refusal", "ambiguous"
]

BloomLevel = Literal[
    "Remembering",
    "Understanding",
    "Applying",
    "Analyzing",
    "Evaluating",
    "Creating",
]

# validator 校验结果(7 规则)
Verdict = Literal["pass", "fail"]


class ValidatorReport(BaseModel):
    """单条 EvalCase 通过 qwen3-4b 跑 7 规则格式校验的结果。"""

    case_id: str
    verdict: Verdict
    failed_rules: list[str] = Field(default_factory=list)
    # 调试用:原始 LLM 输出 (truncated)
    raw_judge: str = ""


class FoxsayAnswer(BaseModel):
    """FoxSay 实际跑出来的回答(由 runner 注入或 mock)。

    与 app.schemas.foxsay.CragAnswer 字段保持最小对齐,但允许 runner
    mock 阶段用 --mock-foxsay 直接给一个 fake answer。
    """

    course_id: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence_status: str = "grounded"
    refusal_reason: str | None = None
    # 工具调用轨迹(可选,judge 用)
    tool_calls: list[dict] = Field(default_factory=list)


class JudgeVerdict(BaseModel):
    """qwen3.5-9b 打出的 Faithfulness 0-3 分。"""

    case_id: str
    faithfulness: int  # 0-3
    reasoning: str = ""
    # 0=完全 hallucinated,1=部分支撑,2=大部分支撑,3=完全 grounded
    passed: bool  # faithfulness >= 2


class PilotCase(BaseModel):
    """单条 pilot 用例 = EvalCase + 必备的生成元数据。"""

    eval_case: EvalCase
    generated_at: str = Field(default_factory=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None).isoformat())
    generator_model: str = ""


class PilotSuite(BaseModel):
    """30 题 pilot 集(8 def / 10 derivation / 5 cross / 4 refusal / 3 ambiguous)。"""

    course_id: str
    cases: list[PilotCase]
    generated_at: str = Field(default_factory=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None).isoformat())
    generator_model: str = ""

    def by_type(self, qtype: QuestionType) -> list[PilotCase]:
        return [c for c in self.cases if c.eval_case.question_type == qtype]

    def refusal_cases(self) -> list[PilotCase]:
        return [c for c in self.cases if c.eval_case.answerability is False]
