"""FoxSay 评测脚手架 (line B).

本包提供:
- schemas: re-export EvalCase (从 app.schemas.foxsay) + 评测用辅助类型
- generator: 30 题 pilot 生成 (DeepSeek)
- validator: 7 规则格式校验 (qwen3-4b-2507)
- judge: Faithfulness 0-3 主观打分 (qwen3.5-9b)
- runner: 端到端跑评测,输出 eval_reports/<course>_<iso>.md
"""

from backend.eval.schemas import (
    FoxsayAnswer,
    JudgeVerdict,
    PilotCase,
    PilotSuite,
    ValidatorReport,
)

__all__ = [
    "FoxsayAnswer",
    "JudgeVerdict",
    "PilotCase",
    "PilotSuite",
    "ValidatorReport",
]
