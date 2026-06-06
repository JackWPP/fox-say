"""Error path coverage: invalid IDs, cross-course leaks, missing prerequisites."""
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


def banner(msg):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}", flush=True)


def main() -> int:
    sys.path.insert(0, "D:/fox-say/backend")
    from app.db.sqlite_store import SqliteStore
    from app.core.config import settings as cfg
    from app.schemas.foxsay import KC
    from app.services.wiki_builder import build_wiki

    failures: list[str] = []

    with httpx.Client(base_url=BASE, timeout=60.0) as c:
        banner("1. Get non-existent course -> 404")
        r = c.get("/courses/00000000-0000-0000-0000-000000000000")
        print(f"  status: {r.status_code}, body: {r.text[:80]}")
        if r.status_code != 404:
            failures.append("non-existent course should 404")

        banner("2. Create course A + B, attempt cross-course kc access")
        a = c.post("/courses", json={"title": "Course A"}).json()
        b = c.post("/courses", json={"title": "Course B"}).json()
        cid_a, cid_b = a["id"], b["id"]
        print(f"  course_a: {cid_a[:8]}, course_b: {cid_b[:8]}")

        # Manually inject a KC into course A
        store = SqliteStore(db_path=cfg.sqlite_path)
        test_kc = KC(
            id="test_kc_crosscourse",
            course_id=cid_a,
            name="卷积",
            definition="卷积定义",
            chapter_id="ch1",
        )
        store.save_kc(test_kc)
        print(f"  injected test_kc into course A")

        # Try to fetch it with course B's id — should refuse (HEC-6)
        r = c.post(
            f"/courses/{cid_b}/chat/sessions", json={"title": "B"}
        )
        sid_b = r.json()["session_id"]
        # We can't easily call query_tools from outside, so we use the list endpoint as a proxy.
        # A: list kcs for course A — should see test_kc
        r = c.get(f"/courses/{cid_a}/kcs")
        a_kcs = r.json().get("kcs", [])
        print(f"  A kcs: {[k['id'] for k in a_kcs]}")
        if not any(k["id"] == "test_kc_crosscourse" for k in a_kcs):
            failures.append("course A should see its own kc")
        # B: list kcs for course B — should NOT see A's kc
        r = c.get(f"/courses/{cid_b}/kcs")
        b_kcs = r.json().get("kcs", [])
        print(f"  B kcs: {[k['id'] for k in b_kcs]}")
        if any(k["id"] == "test_kc_crosscourse" for k in b_kcs):
            failures.append("course B should NOT see course A's kc")

        banner("3. Build wiki endpoint with non-existent course -> 404")
        r = c.post("/courses/00000000-0000-0000-0000-000000000000/build-wiki")
        print(f"  status: {r.status_code}")
        if r.status_code != 404:
            failures.append("build-wiki on non-existent course should 404")

        banner("4. Build wiki endpoint without DMAP -> 400")
        r = c.post(f"/courses/{cid_a}/build-wiki")
        print(f"  status: {r.status_code}, body: {r.text[:120]}")
        # course A has no material uploaded so no dmap; should be 400
        if r.status_code != 400:
            failures.append("build-wiki on course with no dmap should 400")

        banner("5. Chat SSE error visibility: send empty question, should not crash")
        r = c.post(f"/courses/{cid_a}/chat/sessions", json={"title": "Test"})
        sid = r.json()["session_id"]
        with c.stream("POST", f"/courses/{cid_a}/chat/stream",
                      json={"question": "  ", "session_id": sid}) as resp:
            print(f"  status: {resp.status_code}")
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    try:
                        ev = json.loads(line[6:])
                        if ev.get("type") in ("done", "error"):
                            print(f"  -> got {ev['type']} event")
                    except Exception:
                        pass

        banner("6. CRAG out-of-scope (random query)")
        with c.stream("POST", f"/courses/{cid_a}/chat/stream",
                      json={"question": "今天的天气怎么样", "session_id": sid}) as resp:
            print(f"  status: {resp.status_code}")
            done_ev = None
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    try:
                        ev = json.loads(line[6:])
                        if ev.get("type") == "done":
                            done_ev = ev
                        elif ev.get("type") == "error":
                            print(f"  -> error event: {ev.get('message')}")
                    except Exception:
                        pass
            if done_ev:
                print(f"  -> done: in_scope={done_ev.get('in_scope')}, refusal={done_ev.get('refusal_reason')}, has_answer={bool(done_ev.get('answer'))}")
                # The CRAG gate or post-answer guard may refuse; either way the response
                # should be well-formed (no 500).
            else:
                failures.append("got no done event for out-of-scope query")

    print(f"\n{'='*60}\n  Summary\n{'='*60}")
    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print("  All error paths handled correctly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
