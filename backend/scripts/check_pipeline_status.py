"""Check full knowledge pipeline status."""
import sqlite3

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.row_factory = sqlite3.Row
course_id = "53708338-1116-495f-ab5b-c9fd323ceb4c"

jobs = conn.execute(
    "SELECT job_type, status, attempt, error_code FROM knowledge_jobs WHERE course_id = ? ORDER BY created_at",
    (course_id,),
).fetchall()
print("=== All Jobs ===")
for j in jobs:
    print(f"  {j['job_type']}: status={j['status']} attempt={j['attempt']} err={j['error_code']}")

atoms = conn.execute("SELECT COUNT(*) as c FROM semantic_atoms WHERE course_id = ?", (course_id,)).fetchone()
terms = conn.execute("SELECT COUNT(*) as c FROM terms WHERE course_id = ?", (course_id,)).fetchone()
kcs = conn.execute("SELECT COUNT(*) as c FROM knowledge_components WHERE course_id = ?", (course_id,)).fetchone()
rels = conn.execute("SELECT COUNT(*) as c FROM kc_relations WHERE course_id = ?", (course_id,)).fetchone()
print(f"\n=== Projections ===")
print(f"  Atoms: {atoms['c']}")
print(f"  Terms: {terms['c']}")
print(f"  KCs: {kcs['c']}")
print(f"  Relations: {rels['c']}")

queued = conn.execute(
    "SELECT job_type, status FROM knowledge_jobs WHERE course_id = ? AND status IN ('queued', 'running')",
    (course_id,),
).fetchall()
if queued:
    print(f"\n=== Pending Jobs ===")
    for q in queued:
        print(f"  {q['job_type']}: {q['status']}")
else:
    print(f"\nNo pending jobs")

conn.close()
