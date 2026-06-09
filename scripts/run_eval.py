"""CLI: 跑 line B 的 30 题 pilot 评测。

用法:
    cd backend && uv run python -m scripts.run_eval --course-id <id> --pilot
    cd backend && uv run python -m scripts.run_eval --course-id <id> --pilot --mock-foxsay
    cd backend && uv run python -m scripts.run_eval --help
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# 把 backend 加进 sys.path
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))
# 也加上 backend 的兄弟目录 backend/,方便 import app.* 与 backend.eval.*
sys.path.insert(0, str(_BACKEND))

from app.core.config import settings  # noqa: E402
from app.db.sqlite_store import SqliteStore  # noqa: E402

from backend.eval.runner import run_pilot  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_eval",
        description="FoxSay line B 评测 CLI (pilot / full / judge-only / validate-only)",
    )
    parser.add_argument(
        "--course-id",
        required=True,
        help="目标 course_id (e.g. linear-algebra)",
    )
    parser.add_argument(
        "--course-title",
        default=None,
        help="可选,课程标题(用于报告抬头,默认等于 course_id)",
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="跑 30 题 pilot (默认)",
    )
    parser.add_argument(
        "--mock-foxsay",
        action="store_true",
        help="用 runner 内部 mock 代替真实 agent(测试脚手架时用)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_BACKEND / "eval_reports"),
        help="报告输出目录",
    )
    parser.add_argument(
        "--db-path",
        default=settings.sqlite_path,
        help="SqliteStore db 路径(默认 = settings.sqlite_path)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    course_title = args.course_title or args.course_id
    store = SqliteStore(db_path=args.db_path)
    try:
        course = store.get_course(args.course_id)
    except Exception as e:  # noqa: BLE001
        print(f"!! SqliteStore 初始化失败: {e}", file=sys.stderr)
        return 2
    if course is not None and course.title:
        course_title = course.title

    foxsay_call = None
    if args.mock_foxsay:
        # runner 默认就是 mock,这里显式标一下,便于日志输出
        from backend.eval.runner import _default_mock_foxsay
        foxsay_call = _default_mock_foxsay

    result = run_pilot(
        course_id=args.course_id,
        course_title=course_title,
        store=store,
        foxsay_call=foxsay_call,
        output_dir=args.output_dir,
    )

    print("=" * 60)
    print("PILOT SUMMARY")
    print("=" * 60)
    summary = result["summary"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nReport: {summary['report_path']}")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
