"""End-to-end demo: 建课 → 上传材料 → 问问题。

不依赖 Docker (Qdrant local mode 走进程内文件持久化)。
"""
import sys
import time
import json
from pathlib import Path

import httpx

# Force UTF-8 stdout on Windows (avoid GBK encoding errors on Chinese + emoji)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "http://127.0.0.1:8000"


def banner(msg: str) -> None:
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60.0) as c:
        banner("1. Health check")
        r = c.get("/health")
        print(f"  status: {r.status_code}, body: {r.json()}")
        assert r.status_code == 200

        banner("2. Create course")
        r = c.post("/courses", json={
            "title": "信号与系统",
            "teacher": "张老师",
            "exam_date": "2026-06-20",
        })
        print(f"  status: {r.status_code}, body: {r.json()}")
        assert r.status_code == 200
        course = r.json()
        course_id = course["id"]
        print(f"  course_id: {course_id}")

        banner("3. List courses")
        r = c.get("/courses")
        print(f"  status: {r.status_code}, count: {len(r.json())}")
        assert r.status_code == 200

        banner("4. Upload text material")
        # 写一个真材料文件(避免 docling 依赖)
        material_text = """\
# 第一章 信号基础

## 1.1 连续时间信号
连续时间信号是定义在连续时间轴上的信号,例如 x(t), t ∈ ℝ。
典型例子:正弦信号 sin(ωt),指数信号 e^(at)。

## 1.2 离散时间信号
离散时间信号是定义在离散时间点上的信号,例如 x[n], n ∈ ℤ。
常见例子:单位冲激 δ[n],单位阶跃 u[n]。

## 1.3 卷积
卷积是两个信号的"乘积积分",定义:
(f * g)(t) = ∫ f(τ) g(t - τ) dτ
它是时域分析的核心工具,等价于频域的乘法。

## 1.4 傅里叶变换
傅里叶变换将时域信号分解为频域表示:
F(ω) = ∫ f(t) e^(-jωt) dt
逆变换: f(t) = (1/2π) ∫ F(ω) e^(jωt) dω
"""
        material_path = Path("uploads") / f"{course_id}_lecture.txt"
        material_path.parent.mkdir(parents=True, exist_ok=True)
        material_path.write_text(material_text, encoding="utf-8")

        # 上传
        with open(material_path, "rb") as f:
            r = c.post(
                f"/courses/{course_id}/materials",
                files={"file": (material_path.name, f, "text/plain")},
            )
        print(f"  status: {r.status_code}, body: {r.json()}")
        assert r.status_code in (200, 201)
        material = r.json()
        material_id = material["id"]
        print(f"  material_id: {material_id}")

        banner("5. Wait for material processing")
        for i in range(60):
            r = c.get(f"/courses/{course_id}/materials/{material_id}/status")
            if r.status_code == 200:
                data = r.json()
                status = data.get("status", "unknown")
                print(f"  attempt {i+1}: status={status}")
                if status in ("ready", "failed"):
                    break
            else:
                print(f"  attempt {i+1}: HTTP {r.status_code} {r.text[:100]}")
            time.sleep(2)
        else:
            print("  TIMEOUT: material processing did not complete in 120s")
            return 1
        if status == "failed":
            print(f"  FAILED: {data}")
            return 1
        print(f"  material ready: {data}")

        # 同时也看一下进度详情
        r = c.get(f"/courses/{course_id}/materials/{material_id}/progress")
        if r.status_code == 200:
            print(f"  progress steps:")
            for t in r.json().get("steps", []):
                print(f"    - {t['step']}: {t['status']}")

        banner("6. Wait for skeleton generation")
        for i in range(20):
            r = c.get(f"/courses/{course_id}/skeleton")
            if r.status_code == 200:
                skel = r.json()
                print(f"  skeleton: {len(skel.get('chapters', []))} chapters")
                for ch in skel.get("chapters", [])[:5]:
                    print(f"    - {ch.get('title')}: key_concepts={ch.get('key_concepts', [])[:3]}")
                break
            print(f"  attempt {i+1}: skeleton not ready (status {r.status_code})")
            time.sleep(3)
        else:
            print("  TIMEOUT: skeleton not generated")
            return 1

        banner("7. Ask a question (SSE stream)")
        # 创建一个 chat session
        r = c.post(f"/courses/{course_id}/chat/sessions", json={"title": "测试对话"})
        print(f"  create session: {r.status_code} {r.json()}")
        session_id = r.json()["session_id"]

        question = "卷积的定义是什么?"
        print(f"  question: {question}")
        print(f"  streaming response:")

        # SSE 流式读取
        with c.stream(
            "POST",
            f"/courses/{course_id}/chat/stream",
            json={"question": question, "session_id": session_id},
        ) as resp:
            print(f"  status: {resp.status_code}")
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    event = json.loads(line[6:])
                    if event.get("type") == "tool_call":
                        print(f"    [tool_call] {event.get('tool')}({event.get('args')})")
                    elif event.get("type") == "token":
                        print(event.get("token", ""), end="", flush=True)
                    elif event.get("type") == "done":
                        print(f"\n    [done] citations={len(event.get('citations', []))}")
                    elif event.get("type") == "error":
                        print(f"\n    [error] {event.get('message')}")

        banner("DONE")
        return 0


if __name__ == "__main__":
    sys.exit(main())
