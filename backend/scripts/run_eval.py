"""backend/scripts/run_eval.py — 让 `cd backend && python -m scripts.run_eval` 可用。

真实实现在顶层 scripts/run_eval.py (line B 单文件职责单一)。
本文件仅做 sys.path 注入 + 转发,不在这里复制业务代码。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 1) 把 project root 加进 sys.path(在 backend/ 之前),这样能 import 到顶层 scripts/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BACKEND = Path(__file__).resolve().parent.parent

# 重排 sys.path: project root 必须在 backend 之前,
# 否则 `from scripts.run_eval import main` 会再次 import backend/scripts/run_eval.py(循环)。
new_path: list[str] = []
for p in (str(_PROJECT_ROOT), str(_BACKEND)):
    if p not in sys.path and p not in new_path:
        new_path.append(p)
# 把其它路径挪到后面
for p in sys.path:
    if p not in new_path:
        new_path.append(p)
sys.path[:] = new_path

# 2) 用 importlib + 文件路径直接加载顶层 scripts/run_eval.py,
#    绕开 package 冲突 (因为 backend/scripts 也是 scripts)。
import importlib.util as _ilu  # noqa: E402

_TOP_LEVEL_RUN_EVAL = _PROJECT_ROOT / "scripts" / "run_eval.py"
_spec = _ilu.spec_from_file_location(
    "_top_level_run_eval",  # unique module name,避免与本包名冲突
    str(_TOP_LEVEL_RUN_EVAL),
)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise ImportError(f"无法加载顶层 scripts/run_eval.py: {_TOP_LEVEL_RUN_EVAL}")
_module = _ilu.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

main = _module.main
_parse_args = _module._parse_args  # noqa: F401

if __name__ == "__main__":
    sys.exit(main())
