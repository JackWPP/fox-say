"""End-to-end: review plan + /btw interjection."""
import json
import sys
import time
from pathlib import Path

import httpx

# Force UTF-8 stdout on Windows (avoid GBK encoding errors on emoji)
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
        banner("1. Setup: create course + upload PDF + wait for processing")
        r = c.post("/courses", json={"title": "BTW Test", "exam_date": "2026-07-20"})
        course_id = r.json()["id"]
        print(f"  course_id: {course_id}")

        with open(PDF_PATH, "rb") as f:
            r = c.post(f"/courses/{course_id}/materials",
                       files={"file": (PDF_PATH.name, f, "application/pdf")})
        material_id = r.json()["id"]

        for i in range(30):
            r = c.get(f"/courses/{course_id}/materials/{material_id}/status")
            if r.json().get("status") in ("ready", "failed"):
                break
            time.sleep(2)
        if r.json().get("status") != "ready":
            print(f"  FAILED material processing: {r.json()}")
            return 1
        print(f"  material ready")

        banner("2. Generate review plan")
        r = c.post(f"/courses/{course_id}/review-plan", json={"exam_date": "2026-07-20"})
        print(f"  status: {r.status_code}")
        if r.status_code != 200:
            print(f"  FAILED: {r.text[:200]}")
            return 1
        plan = r.json()
        print(f"  remaining_days: {plan.get('remaining_days')}")
        print(f"  daily_plan: {len(plan.get('daily_plan', []))} days")
        print(f"  likely_exam_points: {len(plan.get('likely_exam_points', []))} points")
        for day in plan.get("daily_plan", [])[:3]:
            print(f"    - day {day['day_index']}: {day['focus']} ({day['suggested_minutes']} min)")

        banner("3. /btw interjection (Q1)")
        r = c.post(f"/courses/{course_id}/btw", json={
            "question": "卷积是什么?",
            "current_step_id": "day-1",
        })
        print(f"  status: {r.status_code}")
        if r.status_code != 200:
            print(f"  FAILED: {r.text[:200]}")
            return 1
        btw = r.json()
        answer = btw.get("answer", {}).get("answer", "")
        citations = btw.get("answer", {}).get("citations", [])
        print(f"  answer: {answer[:150]}...")
        print(f"  citations: {len(citations)}")
        for cit in citations[:3]:
            print(f"    - {cit.get('file_name')} · {cit.get('locator')}")
        print(f"  returns_to_review_step_id: {btw.get('returns_to_review_step_id')}")

        banner("4. /btw interjection (Q2) - no current step id")
        r = c.post(f"/courses/{course_id}/btw", json={"question": "傅里叶变换有什么性质?"})
        print(f"  status: {r.status_code}")
        btw2 = r.json()
        print(f"  answer: {btw2.get('answer', {}).get('answer', '')[:150]}...")
        print(f"  returns_to_review_step_id: {btw2.get('returns_to_review_step_id')}")

        banner("5. /btw with no plan / no skeleton")
        # Create a fresh course with no material
        r = c.post("/courses", json={"title": "Empty course"})
        empty_id = r.json()["id"]
        r = c.post(f"/courses/{empty_id}/btw", json={"question": "测试"})
        # The endpoint falls back to crag.ask when plan is None, so we expect 200.
        print(f"  /btw on empty course: {r.status_code}")
        if r.status_code == 200:
            print(f"    answer: {r.json().get('answer', {}).get('answer', '')[:100]}...")

        banner("6. /btw on non-existent course -> 404")
        r = c.post("/courses/00000000-0000-0000-0000-000000000000/btw",
                   json={"question": "test"})
        print(f"  status: {r.status_code}")
        if r.status_code != 404:
            print(f"  FAIL: expected 404")
            return 1

        banner("DONE")
        return 0


if __name__ == "__main__":
    sys.exit(main())
