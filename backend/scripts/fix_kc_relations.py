"""Fix KC relation audit duplication and retry."""
import sqlite3
import time
import httpx

course_id = "53708338-1116-495f-ab5b-c9fd323ceb4c"
API = "http://localhost:8000"

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")

# Get the kc_relation job_id
job = conn.execute(
    "SELECT job_id FROM knowledge_jobs WHERE course_id = ? AND job_type = 'extract_kc_relations' "
    "ORDER BY updated_at DESC LIMIT 1",
    (course_id,),
).fetchone()
job_id = job[0]
print(f"KC relation job_id: {job_id}")

# Delete ALL audits for this job (clean slate)
deleted = conn.execute(
    "DELETE FROM model_call_audits WHERE job_id = ?",
    (job_id,),
).rowcount
print(f"Deleted {deleted} audits for kc_relation job")

# Delete old relations/compilation if any
conn.execute("DELETE FROM kc_relations WHERE course_id = ?", (course_id,))
conn.execute("DELETE FROM kc_relation_compilations WHERE course_id = ?", (course_id,))
print("Cleared old kc_relations and compilations")

# Reset the job
conn.execute(
    "UPDATE knowledge_jobs "
    "SET status = 'queued', attempt = 0, error_code = NULL, error_detail = NULL, "
    "lease_owner = NULL, lease_expires_at = NULL, "
    "started_at = NULL, finished_at = NULL, updated_at = datetime('now') "
    "WHERE job_id = ?",
    (job_id,),
)
conn.commit()
print(f"Reset job to queued")
conn.close()

# Also check if candidates will be empty
# 3 KCs: 对合矩阵, 对称矩阵, 幂等矩阵
# Check if any fragment contains 2+ of these
conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.row_factory = sqlite3.Row
kcs = conn.execute(
    "SELECT kc_id, name FROM knowledge_components WHERE course_id = ?",
    (course_id,),
).fetchall()
kc_names = {k["name"]: k["kc_id"] for k in kcs}
print(f"\nKCs: {list(kc_names.keys())}")

# Check co-occurrence
frags = conn.execute(
    "SELECT fragment_id, text FROM source_fragments WHERE course_id = ?",
    (course_id,),
).fetchall()
co_occurrence = 0
for f in frags:
    found = [name for name in kc_names if name in f["text"]]
    if len(found) >= 2:
        co_occurrence += 1
        print(f"  Co-occurrence in {f['fragment_id'][:25]}: {found}")

if co_occurrence == 0:
    print("No co-occurrences found - KC relations will be empty (valid but no edges)")
conn.close()

# Wait for job to complete
print("\n--- Waiting for KC relation extraction ---")
for i in range(60):
    time.sleep(3)
    try:
        resp = httpx.get(f"{API}/courses/{course_id}/knowledge-status", timeout=15)
        st = resp.json()
        coverage = st.get("coverage", {})
        rel_count = coverage.get("kc_relation_count", 0)
        print(f"  [{i*3}s] relations={rel_count}")

        conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
        conn.row_factory = sqlite3.Row
        job = conn.execute(
            "SELECT status, error_code, error_detail FROM knowledge_jobs "
            "WHERE course_id = ? AND job_type = 'extract_kc_relations'",
            (course_id,),
        ).fetchone()
        conn.close()

        if job and job["status"] not in ("queued", "running"):
            print(f"\nJob finished: {job['status']}")
            if job["error_code"]:
                print(f"  error: {job['error_code']}: {job['error_detail'][:300] if job['error_detail'] else ''}")
            break
    except Exception as e:
        print(f"  [{i*3}s] error: {e}")
else:
    print("Timeout")
