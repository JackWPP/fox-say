"""Check why all atoms are rejected by term compiler."""
import sqlite3
import json
import re
import sys
sys.path.insert(0, ".")
from app.services.term_compiler import _QUOTED_LITERAL, _LEADING_LITERAL, _literal_term_from_atom
from app.schemas.semantic_atoms import SemanticAtom
from app.schemas.evidence import EvidenceRef, SourceFragment

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.row_factory = sqlite3.Row
course_id = "53708338-1116-495f-ab5b-c9fd323ceb4c"

# Get atoms
atoms_rows = conn.execute(
    "SELECT * FROM semantic_atoms WHERE course_id = ?",
    (course_id,),
).fetchall()

# Get fragments
frag_rows = conn.execute(
    "SELECT fragment_id, text FROM source_fragments WHERE course_id = ?",
    (course_id,),
).fetchall()
fragment_by_id = {}
for f in frag_rows:
    # Use a simple object instead of Pydantic model
    class FakeFragment:
        pass
    sf = FakeFragment()
    sf.fragment_id = f["fragment_id"]
    sf.text = f["text"]
    fragment_by_id[f["fragment_id"]] = sf

print(f"Fragments loaded: {len(fragment_by_id)}")
print(f"Atoms to check: {len(atoms_rows)}\n")

for row in atoms_rows:
    evidence_json = json.loads(row["evidence_json"])
    statement = row["statement"]

    print(f"=== Atom: {row['atom_type']} ===")
    print(f"Statement (first 200): {statement[:200]}")

    # Check quoted literals
    quoted = [m.group(1).strip() for m in _QUOTED_LITERAL.finditer(statement)]
    print(f"Quoted literals found: {quoted}")

    # Check leading literals
    leading = _LEADING_LITERAL.match(statement)
    leading_text = leading.group(1).strip() if leading else None
    print(f"Leading literal: {leading_text}")

    # Check evidence
    print(f"Evidence fragments: {len(evidence_json)}")
    for ev in evidence_json:
        fid = ev["fragment_id"]
        frag = fragment_by_id.get(fid)
        if frag is None:
            print(f"  fragment {fid[:20]} NOT FOUND in fragment_by_id")
        else:
            # Check if any candidate appears in the fragment text
            text = frag.text
            for candidate in quoted + ([leading_text] if leading_text else []):
                if candidate and candidate in text:
                    print(f"  FOUND '{candidate}' in fragment {fid[:20]}")
                elif candidate:
                    print(f"  NOT FOUND '{candidate}' in fragment {fid[:20]}")
                    # Show first 200 chars of fragment text
                    print(f"    Fragment text preview: {text[:100]}")
    print()

conn.close()
