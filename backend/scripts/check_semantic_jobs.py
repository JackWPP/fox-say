"""Check semantic job and model call audit errors."""
import sqlite3
import json

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.row_factory = sqlite3.Row

# Check knowledge jobs for semantic/compile
print("=== Knowledge Jobs (non-index) ===")
jobs = conn.execute(
    "SELECT job_id, job_type, course_id, status, attempt, max_attempts, "
    "error_code, error_detail, target_source_revision, target_knowledge_revision "
    "FROM knowledge_jobs WHERE job_type != 'index_material' "
    "ORDER BY created_at DESC"
).fetchall()
for j in jobs:
    print(f"\n  job_type={j['job_type']} status={j['status']} attempt={j['attempt']}/{j['max_attempts']}")
    print(f"  source_rev={j['target_source_revision']}")
    print(f"  error_code={j['error_code']}")
    if j['error_detail']:
        print(f"  error_detail={j['error_detail'][:500]}")

# Check model call audits
print("\n=== Model Call Audits ===")
audits = conn.execute(
    "SELECT call_id, course_id, job_id, owner_type, owner_id, status, call_kind, "
    "purpose, model, error_code, error_detail, input_tokens, output_tokens, "
    "usage_source, elapsed_ms "
    "FROM model_call_audits ORDER BY started_at DESC LIMIT 20"
).fetchall()
for a in audits:
    print(f"\n  call_id={a['call_id'][:12]}... status={a['status']} kind={a['call_kind']}")
    print(f"  purpose={a['purpose']} model={a['model']}")
    print(f"  owner_type={a['owner_type']} owner_id={a['owner_id']}")
    print(f"  input_tokens={a['input_tokens']} output_tokens={a['output_tokens']}")
    print(f"  usage_source={a['usage_source']} elapsed_ms={a['elapsed_ms']}")
    if a['error_code']:
        print(f"  error_code={a['error_code']}")
    if a['error_detail']:
        print(f"  error_detail={a['error_detail'][:300]}")

if not audits:
    print("  (no model call audits found)")

# Check course model budgets
print("\n=== Course Model Budgets ===")
budgets = conn.execute(
    "SELECT * FROM course_model_budgets ORDER BY updated_at DESC"
).fetchall()
for b in budgets:
    print(f"  course={b['course_id'][:12]}... source_rev={b['source_revision']}")
    print(f"  budget={b['token_budget']} status={b['status']}")

conn.close()
