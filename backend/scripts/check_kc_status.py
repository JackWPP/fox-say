"""Check term/KC status after rebuild."""
import sqlite3

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.row_factory = sqlite3.Row
course_id = "53708338-1116-495f-ab5b-c9fd323ceb4c"

# Terms
terms = conn.execute("SELECT term_id, canonical_name, term_kind FROM terms WHERE course_id = ?", (course_id,)).fetchall()
print(f"Terms ({len(terms)}):")
for t in terms:
    print(f"  {t['canonical_name']} ({t['term_kind']})")

# Term compilations
tc = conn.execute("SELECT term_count, rejected_atom_count FROM term_compilations WHERE course_id = ?", (course_id,)).fetchone()
print(f"\nTerm compilation: count={tc['term_count']}, rejected={tc['rejected_atom_count']}")

# KC compilation
kcc = conn.execute("SELECT * FROM knowledge_component_compilations WHERE course_id = ?", (course_id,)).fetchone()
if kcc:
    print(f"\nKC compilation: {dict(kcc)}")
else:
    print("\nNo KC compilation found")

# KCs
kcs = conn.execute("SELECT * FROM knowledge_components WHERE course_id = ?", (course_id,)).fetchall()
print(f"KCs: {len(kcs)}")

# Check jobs
jobs = conn.execute(
    "SELECT job_type, status, attempt, error_code, error_detail "
    "FROM knowledge_jobs WHERE course_id = ? AND job_type IN ('compile_kcs', 'extract_kc_relations')",
    (course_id,),
).fetchall()
print(f"\nKC/Relation jobs:")
for j in jobs:
    print(f"  {j['job_type']}: status={j['status']} attempt={j['attempt']}")
    if j['error_code']:
        print(f"    error: {j['error_code']}: {j['error_detail'][:200] if j['error_detail'] else ''}")

conn.close()
