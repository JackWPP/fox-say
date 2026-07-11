"""Check semantic atoms and their fragment links."""
import sqlite3
import json

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.row_factory = sqlite3.Row
course_id = "53708338-1116-495f-ab5b-c9fd323ceb4c"

# Check table schema
cols = conn.execute("PRAGMA table_info(semantic_atoms)").fetchall()
print("=== semantic_atoms columns ===")
for c in cols:
    print(f"  {c['name']} {c['type']}")

# Check atoms
atoms = conn.execute(
    "SELECT * FROM semantic_atoms WHERE course_id = ?",
    (course_id,),
).fetchall()
print(f"\n=== Semantic Atoms ({len(atoms)}) ===")
for a in atoms:
    d = dict(a)
    print(f"  atom_id={d.get('atom_id', '?')[:30]}")
    print(f"  type={d.get('atom_type', '?')}")
    stmt = d.get('statement', '')
    print(f"  statement={stmt[:100] if stmt else 'NULL'}")
    print(f"  section_id={d.get('section_id', '?')[:30] if d.get('section_id') else 'NULL'}")
    # Print all columns
    for k, v in d.items():
        if k not in ('atom_id', 'atom_type', 'statement', 'section_id'):
            val_str = str(v)[:80] if v else 'NULL'
            print(f"  {k}={val_str}")
    print()

# Check for a fragment links table
tables = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%atom%'"
).fetchall()
print(f"\n=== Atom-related tables: {[t['name'] for t in tables]} ===")

# Check semantic_atom_compilations
comps = conn.execute(
    "SELECT * FROM semantic_atom_compilations WHERE course_id = ?",
    (course_id,),
).fetchall()
print(f"\n=== Semantic Atom Compilations ({len(comps)}) ===")
for c in comps:
    d = dict(c)
    for k, v in d.items():
        val_str = str(v)[:80] if v else 'NULL'
        print(f"  {k}={val_str}")
    print()

# Check term compilations
term_tables = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%term%'"
).fetchall()
print(f"\n=== Term-related tables: {[t['name'] for t in term_tables]} ===")

terms = conn.execute(
    "SELECT * FROM terms WHERE course_id = ?",
    (course_id,),
).fetchall()
print(f"\n=== Terms ({len(terms)}) ===")

# Check term_compilations
tc = conn.execute(
    "SELECT * FROM term_compilations WHERE course_id = ?",
    (course_id,),
).fetchall()
print(f"\n=== Term Compilations ({len(tc)}) ===")
for t in tc:
    d = dict(t)
    for k, v in d.items():
        val_str = str(v)[:80] if v else 'NULL'
        print(f"  {k}={val_str}")

conn.close()
