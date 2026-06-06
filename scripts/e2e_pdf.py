"""End-to-end demo for PDF path: upload a real PDF and verify pipeline completes.

Since our hand-rolled simple PDF defeats docling's heading detection (returns 0 chunks),
parse_pdf falls back to pdfplumber. This is the designed behavior (HEC-1 graceful
degradation), and the rest of the pipeline (chunking → embedding → storing → skeleton)
proceeds normally.
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
    print(f"\n{'='*60}\n  {msg}\n{'='*60}", flush=True)


def main() -> int:
    pdf_path = Path("D:/fox-say/uploads/test_signals_systems.pdf")
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        print("Run: uv run python scripts/make_test_pdf.py first")
        return 1

    with httpx.Client(base_url=BASE, timeout=120.0) as c:
        banner("1. Create course")
        r = c.post("/courses", json={
            "title": "PDF Test Course",
            "teacher": "Docling Test",
            "exam_date": "2026-07-01",
        })
        assert r.status_code == 200, r.text
        course_id = r.json()["id"]
        print(f"  course_id: {course_id}")

        banner("2. Upload PDF")
        with open(pdf_path, "rb") as f:
            r = c.post(
                f"/courses/{course_id}/materials",
                files={"file": (pdf_path.name, f, "application/pdf")},
            )
        assert r.status_code == 200, r.text
        m = r.json()
        material_id = m["id"]
        print(f"  kind: {m['kind']}, material_id: {material_id}")

        banner("3. Wait for processing")
        for i in range(60):
            r = c.get(f"/courses/{course_id}/materials/{material_id}/status")
            if r.status_code == 200:
                d = r.json()
                status = d.get("status")
                print(f"  attempt {i+1}: status={status}")
                if status in ("ready", "failed"):
                    break
            time.sleep(2)
        else:
            print("  TIMEOUT")
            return 1
        if status == "failed":
            print(f"  FAILED: {d}")
            return 1

        banner("4. Progress steps")
        r = c.get(f"/courses/{course_id}/materials/{material_id}/progress")
        for t in r.json().get("steps", []):
            print(f"  - {t['step']}: {t['status']}")

        banner("5. Skeleton")
        r = c.get(f"/courses/{course_id}/skeleton")
        if r.status_code == 200:
            skel = r.json()
            print(f"  chapters: {len(skel.get('chapters', []))}")
            for ch in skel.get("chapters", [])[:5]:
                print(f"    - {ch.get('title')}: {ch.get('key_concepts', [])[:5]}")

        banner("6. Wiki state")
        r = c.get(f"/courses/{course_id}/wiki")
        if r.status_code == 200:
            wiki = r.json()
            print(f"  kcs: {len(wiki.get('kcs', []))}")
            print(f"  chapter_wikis: {len(wiki.get('chapter_wikis', []))}")
            for kc in wiki.get('kcs', [])[:3]:
                print(f"    - {kc.get('name')}: {kc.get('definition', '')[:80]}")

        banner("DONE")
        return 0


if __name__ == "__main__":
    sys.exit(main())
