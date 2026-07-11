"""Check job errors in the database."""
import sqlite3
import json

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.row_factory = sqlite3.Row
jobs = conn.execute(
    "SELECT job_id, job_type, course_id, material_id, status, error_code, error_detail, attempt "
    "FROM knowledge_jobs ORDER BY created_at DESC LIMIT 10"
).fetchall()
for j in jobs:
    print(f"job_type={j['job_type']} status={j['status']} attempt={j['attempt']}")
    print(f"  error_code={j['error_code']}")
    print(f"  error_detail={j['error_detail']}")
    print()

# Also check materials
mats = conn.execute(
    "SELECT id, course_id, filename, kind, status, revision FROM materials ORDER BY rowid DESC LIMIT 10"
).fetchall()
print("--- Materials ---")
for m in mats:
    print(f"  {m['filename']} kind={m['kind']} status={m['status']} rev={m['revision']}")

conn.close()
