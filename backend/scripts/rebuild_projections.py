"""Rebuild Term/KC/Relation projections after term compiler fix."""
import sqlite3
import time
import httpx

course_id = "53708338-1116-495f-ab5b-c9fd323ceb4c"
API = "http://localhost:8000"

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")

# Delete old term/KC/relation projections
conn.execute("DELETE FROM terms WHERE course_id = ?", (course_id,))
conn.execute("DELETE FROM term_atom_links WHERE course_id = ?", (course_id,))
conn.execute("DELETE FROM term_compilations WHERE course_id = ?", (course_id,))
conn.execute("DELETE FROM knowledge_components WHERE course_id = ?", (course_id,))
conn.execute("DELETE FROM knowledge_component_compilations WHERE course_id = ?", (course_id,))
conn.execute("DELETE FROM kc_relations WHERE course_id = ?", (course_id,))
conn.execute("DELETE FROM kc_relation_compilations WHERE course_id = ?", (course_id,))
print("Deleted old term/KC/relation projections")

# Reset term/KC/relation jobs to queued
result = conn.execute(
    "UPDATE knowledge_jobs "
    "SET status = 'queued', attempt = 0, error_code = NULL, error_detail = NULL, "
    "lease_owner = NULL, lease_expires_at = NULL, "
    "started_at = NULL, finished_at = NULL, updated_at = datetime('now') "
    "WHERE course_id = ? AND job_type IN ('compile_terms', 'compile_kcs', 'extract_kc_relations')",
    (course_id,),
)
print(f"Reset {result.rowcount} jobs to queued")
conn.commit()
conn.close()

# Poll
print("\n--- Waiting for term/KC/relation compilation ---")
for i in range(60):
    time.sleep(3)
    try:
        resp = httpx.get(f"{API}/courses/{course_id}/knowledge-status", timeout=15)
        st = resp.json()
        semantic = st.get("semantic_status", "?")
        coverage = st.get("coverage", {})
        atom_count = coverage.get("semantic_atom_count", 0)
        term_count = coverage.get("term_count", 0)
        kc_count = coverage.get("kc_count", 0)
        relation_count = coverage.get("kc_relation_count", 0)
        print(f"  [{i*3}s] semantic={semantic} atoms={atom_count} terms={term_count} kcs={kc_count} relations={relation_count}")

        # Check pending jobs
        conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
        pending = conn.execute(
            "SELECT job_type, status FROM knowledge_jobs "
            "WHERE course_id = ? AND status IN ('queued', 'running')",
            (course_id,),
        ).fetchall()
        conn.close()

        if not pending and term_count > 0:
            print(f"\nDone! Terms={term_count}, KCs={kc_count}, Relations={relation_count}")
            break
        elif not pending and term_count == 0 and i > 5:
            print(f"\nAll jobs done but 0 terms. Check term_compilations rejected count.")
            break
    except Exception as e:
        print(f"  [{i*3}s] error: {e}")
else:
    print("Timeout")

# Final check
conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.row_factory = sqlite3.Row
tc = conn.execute(
    "SELECT term_count, rejected_atom_count FROM term_compilations WHERE course_id = ?",
    (course_id,),
).fetchone()
if tc:
    print(f"\nTerm compilation: term_count={tc['term_count']}, rejected_atom_count={tc['rejected_atom_count']}")

terms = conn.execute("SELECT canonical_name, term_kind FROM terms WHERE course_id = ?", (course_id,)).fetchall()
print(f"\nTerms ({len(terms)}):")
for t in terms:
    print(f"  {t['canonical_name']} ({t['term_kind']})")

kcs = conn.execute("SELECT name, atom_type FROM knowledge_components WHERE course_id = ?", (course_id,)).fetchall()
print(f"\nKCs ({len(kcs)}):")
for k in kcs:
    print(f"  {k['name']} ({k['atom_type']})")

conn.close()
