"""Retry the failed semantic atoms job after increasing the budget."""
import sqlite3
import httpx
import time

course_id = "53708338-1116-495f-ab5b-c9fd323ceb4c"
API = "http://localhost:8000"

# Step 1: Update the existing course_model_budgets row to the new limit
conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.execute(
    "UPDATE course_model_budgets SET token_budget = 500000 WHERE course_id = ?",
    (course_id,),
)
conn.commit()

# Verify
row = conn.execute(
    "SELECT token_budget FROM course_model_budgets WHERE course_id = ?", (course_id,)
).fetchone()
print(f"Updated course budget to: {row[0] if row else 'NOT FOUND'}")
conn.close()

# Step 2: Retry the failed material jobs first (in case any materials are retryable)
print("\n--- Retrying failed/retryable jobs ---")
jobs_resp = httpx.get(f"{API}/courses/{course_id}/knowledge-status", timeout=15)
status = jobs_resp.json()
print(f"Source: {status['source_status']}, Projection: {status['projection_status']}, Semantic: {status.get('semantic_status', 'unknown')}")

# Step 3: Use the retry endpoint to re-enqueue the semantic job
# The retry endpoint is POST /courses/{course_id}/materials/{material_id}/retry
# But semantic is a course-level job, not a material job.
# We need to manually re-enqueue the semantic job.
# Let's check if there's a way to do this via the API or if we need to do it via the store.

# Actually, the simplest approach is to update the job status back to 'queued' so the worker picks it up again.
conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
# Reset the failed semantic job to queued
result = conn.execute(
    """UPDATE knowledge_jobs 
       SET status = 'queued', attempt = 0, error_code = NULL, error_detail = NULL,
           lease_owner = NULL, lease_expires_at = NULL, 
           started_at = NULL, finished_at = NULL, updated_at = datetime('now')
       WHERE course_id = ? AND job_type = 'extract_semantic_atoms' AND status = 'failed'
    """,
    (course_id,),
)
print(f"\nReset {result.rowcount} semantic jobs to queued")
conn.commit()
conn.close()

# Step 4: Wait and poll
print("\n--- Waiting for semantic extraction ---")
for i in range(120):  # up to 10 minutes
    time.sleep(5)
    try:
        resp = httpx.get(f"{API}/courses/{course_id}/knowledge-status", timeout=15)
        st = resp.json()
        source = st.get("source_status", "?")
        projection = st.get("projection_status", "?")
        semantic = st.get("semantic_status", "unknown")
        coverage = st.get("coverage", {})
        atom_count = coverage.get("semantic_atom_count", 0)
        term_count = coverage.get("term_count", 0)
        kc_count = coverage.get("kc_count", 0)
        relation_count = coverage.get("kc_relation_count", 0)
        print(f"  [{i*5}s] source={source} proj={projection} semantic={semantic} atoms={atom_count} terms={term_count} kcs={kc_count} relations={relation_count}")
        
        # Check if we're done (semantic succeeded or failed)
        if semantic in ("ready", "failed"):
            print(f"\nSemantic extraction finished: {semantic}")
            if semantic == "failed":
                # Check the error
                conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
                conn.row_factory = sqlite3.Row
                job = conn.execute(
                    "SELECT error_code, error_detail FROM knowledge_jobs WHERE course_id = ? AND job_type = 'extract_semantic_atoms' ORDER BY updated_at DESC LIMIT 1",
                    (course_id,),
                ).fetchone()
                if job:
                    print(f"  error_code: {job['error_code']}")
                    print(f"  error_detail: {job['error_detail'][:500] if job['error_detail'] else 'None'}")
                # Check model call audit
                audit = conn.execute(
                    "SELECT call_id, status, error_code, error_detail, input_tokens, output_tokens, elapsed_ms FROM model_call_audits WHERE course_id = ? ORDER BY started_at DESC LIMIT 3",
                    (course_id,),
                ).fetchall()
                for a in audit:
                    print(f"  audit: status={a['status']} err={a['error_code']} in={a['input_tokens']} out={a['output_tokens']} ms={a['elapsed_ms']}")
                    if a['error_detail']:
                        print(f"    detail: {a['error_detail'][:300]}")
                conn.close()
            break
    except Exception as e:
        print(f"  [{i*5}s] API error: {e}")
else:
    print("Timeout waiting for semantic extraction")
