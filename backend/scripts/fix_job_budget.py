"""Fix job budgets and retry semantic extraction."""
import sqlite3
import time
import httpx

course_id = "53708338-1116-495f-ab5b-c9fd323ceb4c"
API = "http://localhost:8000"

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")

# Update all course-level jobs to use the new budget
result = conn.execute(
    "UPDATE knowledge_jobs SET token_budget = 500000 "
    "WHERE job_type IN ('extract_semantic_atoms', 'compile_terms', 'compile_kcs', 'extract_kc_relations')"
)
print(f"Updated {result.rowcount} jobs with new budget")

# Delete old budget row and rejected audits
conn.execute("DELETE FROM course_model_budgets WHERE course_id = ?", (course_id,))
conn.execute(
    "DELETE FROM model_call_audits WHERE course_id = ? AND status = 'rejected'",
    (course_id,),
)
print("Cleared old budget and rejected audits")

# Reset the semantic job
conn.execute(
    "UPDATE knowledge_jobs "
    "SET status = 'queued', attempt = 0, error_code = NULL, error_detail = NULL, "
    "lease_owner = NULL, lease_expires_at = NULL, "
    "started_at = NULL, finished_at = NULL, updated_at = datetime('now') "
    "WHERE course_id = ? AND job_type = 'extract_semantic_atoms'",
    (course_id,),
)
conn.commit()

# Verify
job = conn.execute(
    "SELECT token_budget, status FROM knowledge_jobs "
    "WHERE course_id = ? AND job_type = 'extract_semantic_atoms'",
    (course_id,),
).fetchone()
print(f"Semantic job: token_budget={job[0]}, status={job[1]}")
conn.close()

# Now wait and poll
print("\n--- Waiting for semantic extraction ---")
for i in range(120):
    time.sleep(5)
    try:
        resp = httpx.get(f"{API}/courses/{course_id}/knowledge-status", timeout=15)
        st = resp.json()
        semantic = st.get("semantic_status", "unknown")
        coverage = st.get("coverage", {})
        atom_count = coverage.get("semantic_atom_count", 0)
        term_count = coverage.get("term_count", 0)
        kc_count = coverage.get("kc_count", 0)
        relation_count = coverage.get("kc_relation_count", 0)
        print(f"  [{i*5}s] semantic={semantic} atoms={atom_count} terms={term_count} kcs={kc_count} relations={relation_count}")

        if semantic in ("ready", "failed"):
            print(f"\nSemantic: {semantic}")
            conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
            conn.row_factory = sqlite3.Row
            job = conn.execute(
                "SELECT status, error_code, error_detail FROM knowledge_jobs "
                "WHERE course_id = ? AND job_type = 'extract_semantic_atoms' "
                "ORDER BY updated_at DESC LIMIT 1",
                (course_id,),
            ).fetchone()
            if job:
                print(f"Job: {job['status']} err={job['error_code']}")
                if job["error_detail"]:
                    print(f"  detail: {job['error_detail'][:500]}")

            audits = conn.execute(
                "SELECT call_id, status, error_code, error_detail, "
                "input_tokens, output_tokens, elapsed_ms "
                "FROM model_call_audits WHERE course_id = ? "
                "ORDER BY started_at DESC LIMIT 5",
                (course_id,),
            ).fetchall()
            for a in audits:
                print(
                    f"  audit: status={a['status']} err={a['error_code']} "
                    f"in={a['input_tokens']} out={a['output_tokens']} ms={a['elapsed_ms']}"
                )
                if a["error_detail"]:
                    print(f"    detail: {a['error_detail'][:300]}")
            conn.close()
            break
    except Exception as e:
        print(f"  [{i*5}s] error: {e}")
else:
    print("Timeout")
