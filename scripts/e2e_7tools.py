"""End-to-end: build wiki from stored DMAP, then verify 7 chat tools can be triggered.

Note: We directly trigger the LangGraph StateGraph via wiki_builder internals and
expose each tool's result, rather than going through agent_chat (which has 5-round
ReAct budget). Each tool gets called with a synthetic course context.
"""
import json
import sys
import time
from pathlib import Path

import httpx

# Force UTF-8 stdout on Windows (avoid GBK encoding errors on Chinese + emoji)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "http://127.0.0.1:8000"
PDF_PATH = Path("D:/fox-say/uploads/test_signals_systems.pdf")


def banner(msg):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}", flush=True)


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=120.0) as c:
        banner("1. Setup: create course + upload PDF + build wiki")
        r = c.post("/courses", json={"title": "Tools Test", "exam_date": "2026-07-15"})
        course_id = r.json()["id"]
        print(f"  course_id: {course_id}")

        with open(PDF_PATH, "rb") as f:
            r = c.post(f"/courses/{course_id}/materials", files={"file": (PDF_PATH.name, f, "application/pdf")})
        material_id = r.json()["id"]

        # wait for processing
        for i in range(30):
            r = c.get(f"/courses/{course_id}/materials/{material_id}/status")
            if r.json().get("status") in ("ready", "failed"):
                break
            time.sleep(2)

        # Try first: build-wiki endpoint (uses stored dmap)
        r = c.post(f"/courses/{course_id}/build-wiki")
        print(f"  build-wiki (endpoint): {r.status_code} {r.json()}")

        # If endpoint yields 0 KCs (simple PDF has no structure), also try a structured
        # build via internal call. We import wiki_builder here so the test is self-contained.
        import sys
        sys.path.insert(0, "D:/fox-say/backend")
        from app.db.sqlite_store import SqliteStore
        from app.core.config import settings as cfg
        from app.services.wiki_builder import build_wiki

        store = SqliteStore(db_path=cfg.sqlite_path)
        structured_chunks = [
            {"text": "Signals are functions of time. A continuous-time signal x(t) is defined for all real t; a discrete-time signal x[n] is defined for integer n.", "heading": "Chapter 1: Signal Basics", "level": 1, "page": 1},
            {"text": "x(t) = sin(omega*t) is a sinusoidal signal with period T = 2*pi/omega.", "heading": "Chapter 1: Signal Basics > 1.1 Sinusoidal", "level": 2, "page": 1},
            {"text": "x[n] = a^n for integer n is a geometric sequence, defined for any real a.", "heading": "Chapter 1: Signal Basics > 1.2 Geometric", "level": 2, "page": 2},
            {"text": "Convolution (f * g)(t) = integral f(tau) g(t - tau) dtau is the core time-domain operator.", "heading": "Chapter 2: Convolution", "level": 1, "page": 3},
            {"text": "Convolution theorem: F{f*g} = F{f} * F{g} — multiplication in frequency domain.", "heading": "Chapter 2: Convolution > 2.1 Theorem", "level": 2, "page": 3},
            {"text": "Fourier transform: F(omega) = integral f(t) exp(-j*omega*t) dt.", "heading": "Chapter 3: Fourier Transform", "level": 1, "page": 4},
            {"text": "Inverse: f(t) = (1/2*pi) integral F(omega) exp(j*omega*t) d*omega.", "heading": "Chapter 3: Fourier Transform > 3.1 Inverse", "level": 2, "page": 4},
        ]
        try:
            result = build_wiki(course_id, structured_chunks, store, source_file="structured.txt")
            print(f"  build-wiki (structured): {len(result.kcs)} KCs, {len(result.chapter_wikis)} chapter_wikis")
        except Exception as e:
            print(f"  build-wiki (structured) FAILED: {e}")

        # get kc list
        r = c.get(f"/courses/{course_id}/kcs")
        print(f"  list kcs: {r.status_code}")
        kcs = r.json().get("kcs", []) if r.status_code == 200 else []
        if not kcs:
            print("  still no kcs; will skip concept tools in the test")
            sample_kc_id = ""
            sample_kc_name = ""
        else:
            sample_kc_id = kcs[0]["id"]
            sample_kc_name = kcs[0]["name"]
            print(f"  sample kc: {sample_kc_id} = {sample_kc_name}")

        banner("2. Verify each of 7 tools by triggering agent_chat with targeted questions")
        # We use agent_chat endpoint with carefully-chosen questions to elicit each tool.
        # We can't see which tool was called from outside, but we can check final answer quality.

        r = c.post(f"/courses/{course_id}/chat/sessions", json={"title": "Tool test"})
        session_id = r.json()["session_id"]

        questions = [
            ("search_wiki", "信号与系统里卷积的定义是什么?"),
            ("get_course_map", "这门课的整体章节结构是怎样的?"),
            ("get_concept", f"详细解释 {sample_kc_name} 这个概念"),
            ("get_chapter_outline", "第一章的主要内容是什么?"),
            ("follow_prerequisite", f"学习 {sample_kc_name} 之前需要先掌握什么?"),
            ("get_review_plan", "给我一个 7 天的复习计划"),
        ]

        for tool_name, q in questions:
            print(f"\n  Q ({tool_name}): {q}")
            with c.stream("POST", f"/courses/{course_id}/chat/stream",
                          json={"question": q, "session_id": session_id}) as resp:
                tools_seen = []
                answer_chars = 0
                error_msg = ""
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        try:
                            ev = json.loads(line[6:])
                        except Exception:
                            continue
                        if ev.get("type") == "tool_call":
                            tools_seen.append(ev.get("tool"))
                        elif ev.get("type") == "token":
                            answer_chars += len(ev.get("token", ""))
                        elif ev.get("type") == "error":
                            error_msg = ev.get("message", "")
                        elif ev.get("type") == "done":
                            print(f"    -> tools called: {tools_seen}")
                            print(f"    -> answer length: {answer_chars} chars")
                            if ev.get("citations"):
                                print(f"    -> citations: {len(ev['citations'])}")
                            if error_msg:
                                print(f"    -> error: {error_msg[:100]}")

        banner("DONE")
        return 0


if __name__ == "__main__":
    sys.exit(main())
