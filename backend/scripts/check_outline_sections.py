"""Check outline sections and estimate token cost for semantic extraction."""
import sqlite3
import json

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.row_factory = sqlite3.Row

course_id = "53708338-1116-495f-ab5b-c9fd323ceb4c"

# Get the latest course compilation
comp = conn.execute(
    "SELECT * FROM course_compilations WHERE course_id = ? ORDER BY created_at DESC LIMIT 1",
    (course_id,),
).fetchone()
if comp is None:
    print("No compilation found")
    exit()

print(f"Compilation: knowledge_rev={comp['knowledge_revision']}")
print(f"  source_fragment_count={comp['source_fragment_count']}")
print(f"  outline_section_count={comp['outline_section_count']}")

# Get the outline snapshot
snapshot = conn.execute(
    "SELECT payload_json FROM course_projection_snapshots "
    "WHERE course_id = ? AND knowledge_revision = ?",
    (course_id, comp["knowledge_revision"]),
).fetchone()
if snapshot is None:
    print("No snapshot found")
    exit()

outline = json.loads(snapshot["payload_json"])
sections = outline.get("sections", [])
print(f"\nOutline has {len(sections)} sections:")
total_text_size = 0
for s in sections:
    mat_ids = s.get("material_ids", [])
    frag_count = len(s.get("fragment_ids", []))
    title = s.get("title", "?")
    print(f"  - {title} | fragments={frag_count} | materials={len(mat_ids)}")

# Count total fragment text size
frags = conn.execute(
    "SELECT text FROM source_fragments WHERE course_id = ? AND material_revision = 1",
    (course_id,),
).fetchall()
total_size = sum(len(f["text"]) for f in frags)
total_bytes = sum(len(f["text"].encode("utf-8")) for f in frags)
print(f"\nTotal fragments: {len(frags)}")
print(f"Total text chars: {total_size}")
print(f"Total text bytes (UTF-8): {total_bytes}")
print(f"Conservative input upper bound estimate: {total_bytes + 32 + 8 * len(frags)}")
print(f"Course budget (default): 36000")
print(f"Job budget (default): 12000")
print(f"\nFirst section fragment text sample:")
first_section = sections[0] if sections else None
if first_section:
    frag_ids = first_section.get("fragment_ids", [])[:3]
    for fid in frag_ids:
        f = conn.execute(
            "SELECT text FROM source_fragments WHERE fragment_id = ?", (fid,)
        ).fetchone()
        if f:
            print(f"  [{fid[:12]}] {len(f['text'])} chars: {f['text'][:100]}...")

# Check the budget row
budget = conn.execute(
    "SELECT * FROM course_model_budgets WHERE course_id = ? AND source_revision = ?",
    (course_id, comp["knowledge_revision"]),
).fetchone()
if budget:
    cols = [k for k in budget.keys()]
    print(f"\nBudget columns: {cols}")
    print(f"Budget values: {dict(budget)}")
else:
    print("\nNo budget row found")
    # Try with source_revision pattern
    budget2 = conn.execute(
        "SELECT * FROM course_model_budgets WHERE course_id = ?",
        (course_id,),
    ).fetchall()
    for b in budget2:
        print(f"  source_rev={b['source_revision'][:30]}... budget={b['token_budget']}")

conn.close()
