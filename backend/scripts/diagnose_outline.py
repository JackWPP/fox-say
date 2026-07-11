"""Diagnose outline section evidence."""
import sqlite3
import json

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.row_factory = sqlite3.Row
course_id = "53708338-1116-495f-ab5b-c9fd323ceb4c"

# Get the outline snapshot
snapshot = conn.execute(
    "SELECT payload_json FROM course_projection_snapshots "
    "WHERE course_id = ? ORDER BY created_at DESC LIMIT 1",
    (course_id,),
).fetchone()

if snapshot is None:
    print("No snapshot found")
    exit()

outline = json.loads(snapshot["payload_json"])
sections = outline.get("sections", [])
print(f"Total sections: {len(sections)}")

# Check how many sections have non-empty evidence
non_empty = 0
empty = 0
for s in sections:
    evidence = s.get("evidence", [])
    if evidence:
        non_empty += 1
    else:
        empty += 1

print(f"Sections with evidence: {non_empty}")
print(f"Sections without evidence: {empty}")

# Show first 5 sections with evidence
print("\n=== First 5 sections with evidence ===")
count = 0
for s in sections:
    evidence = s.get("evidence", [])
    if evidence:
        print(f"\n  section_id={s['section_id'][:30]}")
        print(f"  title={s['title']}")
        print(f"  heading_path={s.get('heading_path', [])}")
        print(f"  evidence count={len(evidence)}")
        if evidence:
            print(f"  first evidence: fragment_id={evidence[0].get('fragment_id', '?')[:30]}")
            print(f"    material_id={evidence[0].get('material_id', '?')[:30]}")
            print(f"    locator={evidence[0].get('locator', '?')}")
        count += 1
        if count >= 5:
            break

# Show first 5 sections WITHOUT evidence
print("\n=== First 5 sections WITHOUT evidence ===")
count = 0
for s in sections:
    evidence = s.get("evidence", [])
    if not evidence:
        print(f"\n  section_id={s['section_id'][:30]}")
        print(f"  title={s['title']}")
        print(f"  heading_path={s.get('heading_path', [])}")
        print(f"  ordinal={s.get('ordinal', '?')}")
        count += 1
        if count >= 5:
            break

# Now check the semantic atoms
print("\n=== Semantic Atoms ===")
atoms = conn.execute(
    "SELECT atom_id, atom_type, statement, section_id, rejected "
    "FROM semantic_atoms WHERE course_id = ?",
    (course_id,),
).fetchall()
for a in atoms:
    print(f"  atom_id={a['atom_id'][:30]}")
    print(f"  type={a['atom_type']} section={a['section_id'][:30] if a['section_id'] else 'NULL'}")
    print(f"  statement={a['statement'][:100]}")
    print(f"  rejected={a['rejected']}")
    print()

# Check semantic_atom_fragment_links or however fragments are linked
print("=== Semantic Atom Fragment Links ===")
try:
    links = conn.execute(
        "SELECT * FROM semantic_atom_fragment_links LIMIT 10"
    ).fetchall()
    if links:
        cols = [k for k in links[0].keys()]
        print(f"Columns: {cols}")
        for l in links:
            print(f"  {dict(l)}")
    else:
        print("No links found or table doesn't exist")
except Exception as e:
    print(f"Error: {e}")

# Check actual fragments to see heading_path
print("\n=== Sample Fragments ===")
frags = conn.execute(
    "SELECT fragment_id, heading_path, material_id, material_revision, "
    "substr(text, 1, 80) as text_preview "
    "FROM source_fragments WHERE course_id = ? LIMIT 5",
    (course_id,),
).fetchall()
for f in frags:
    print(f"  fragment_id={f['fragment_id'][:30]}")
    print(f"  heading_path={f['heading_path']}")
    print(f"  material_id={f['material_id'][:30]}")
    print(f"  text={f['text_preview']}")
    print()

conn.close()
