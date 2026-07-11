"""Diagnose KC relation audit issue."""
import sqlite3

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.row_factory = sqlite3.Row
course_id = "53708338-1116-495f-ab5b-c9fd323ceb4c"

# Get the kc_relation job
job = conn.execute(
    "SELECT job_id, status, attempt, error_code, error_detail "
    "FROM knowledge_jobs WHERE course_id = ? AND job_type = 'extract_kc_relations' "
    "ORDER BY updated_at DESC LIMIT 1",
    (course_id,),
).fetchone()
if job:
    print(f"KC Relation Job:")
    print(f"  job_id: {job['job_id']}")
    print(f"  status: {job['status']}")
    print(f"  attempt: {job['attempt']}")
    print(f"  error: {job['error_code']}: {job['error_detail'][:300] if job['error_detail'] else 'None'}")

# Check ALL audits for this course
print(f"\nAll model_call_audits for this course:")
audits = conn.execute(
    "SELECT call_id, job_id, owner_type, owner_id, status, purpose, "
    "input_tokens, output_tokens, error_code "
    "FROM model_call_audits WHERE course_id = ? ORDER BY started_at",
    (course_id,),
).fetchall()
for a in audits:
    print(f"  call_id={a['call_id'][:12]}.. job_id={a['job_id'][:12] if a['job_id'] else 'NULL'}")
    print(f"    owner_type={a['owner_type']} owner_id={a['owner_id'][:12] if a['owner_id'] else 'NULL'}")
    print(f"    status={a['status']} purpose={a['purpose']}")
    print(f"    tokens: in={a['input_tokens']} out={a['output_tokens']}")
    if a['error_code']:
        print(f"    error: {a['error_code']}")
    print()

# Now check if the kc_relation job_id has any audits
if job:
    job_audits = conn.execute(
        "SELECT call_id, status, purpose FROM model_call_audits WHERE job_id = ?",
        (job['job_id'],),
    ).fetchall()
    print(f"\nAudits for KC relation job_id ({job['job_id'][:12]}..): {len(job_audits)}")
    for a in job_audits:
        print(f"  {a['status']} purpose={a['purpose']}")

    # Also check by owner_id
    owner_audits = conn.execute(
        "SELECT call_id, status, purpose FROM model_call_audits WHERE owner_id = ?",
        (job['job_id'],),
    ).fetchall()
    print(f"\nAudits by owner_id: {len(owner_audits)}")
    for a in owner_audits:
        print(f"  {a['status']} purpose={a['purpose']}")

conn.close()
