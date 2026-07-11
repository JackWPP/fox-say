"""Test term extraction with new patterns."""
import re
import sqlite3
import json

_QUOTED_LITERAL = re.compile(r"[\u201c\"\u300c`]([^\u201d\"\u300d`]{1,160})[\u201d\"\u300d`]")
_LEADING_LITERAL = re.compile(
    r"^\s*([^\uff0c\u3002\uff1b\uff1a\uff08()]{1,160}?)(?:\u662f\u630e|\u79f0\u4e3a|\u53eb\u505a|\u5b9a\u4e49\u4e3a|\u5b9a\u4e49\u6210|\u8868\u793a|\u6ee1\u8db3|\u5177\u6709|\u662f)"
)
_TERM_AFTER_DEFINITION = re.compile(
    r"(?:\u5219\u79f0|\u79f0|\u79f0\u4e4b\u4e3a|\u79f0\u4e3a|\u53eb\u505a)[^\uff0c\u3002\uff1b\uff1a\uff08()]{0,40}?\u4e3a\s*"
    r"([^\uff0c\u3002\uff1b\uff1a\uff08()\uff0c\u3002\uff1b\uff1a]{1,80})"
    r"|\u79f0\u4e3a\s*([^\uff0c\u3002\uff1b\uff1a\uff08()\uff0c\u3002\uff1b\uff1a]{1,80})"
    r"|\u53eb\u505a\s*([^\uff0c\u3002\uff1b\uff1a\uff08()\uff0c\u3002\uff1b\uff1a]{1,80})"
    r"|\u79f0\u4e4b\u4e3a\s*([^\uff0c\u3002\uff1b\uff1a\uff08()\uff0c\u3002\uff1b\uff1a]{1,80})"
)

# Simpler test with actual unicode chars
_QUOTED = re.compile(r'["\u201c\u300c]([^"\u201d\u300d]{1,160})["\u201d\u300d]')
_LEADING = re.compile(
    r'^\s*([^\uff0c\u3002\uff1b\uff1a\uff08()]{1,160}?)'
    r'(?:\u662f\u630e|\u79f0\u4e3a|\u53eb\u505a|\u5b9a\u4e49\u4e3a|\u5b9a\u4e49\u6210|\u8868\u793a|\u6ee1\u8db3|\u5177\u6709|\u662f)'
)
_TRAILING = re.compile(
    r'(?:\u5219\u79f0|\u79f0|\u79f0\u4e4b\u4e3a|\u79f0\u4e3a|\u53eb\u505a)'
    r'[^\uff0c\u3002\uff1b\uff1a\uff08()]{0,40}?\u4e3a\s*'
    r'([^\uff0c\u3002\uff1b\uff1a\uff08()]{1,80})'
    r'|\u79f0\u4e3a\s*([^\uff0c\u3002\uff1b\uff1a\uff08()]{1,80})'
    r'|\u53eb\u505a\s*([^\uff0c\u3002\uff1b\uff1a\uff08()]{1,80})'
)

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.row_factory = sqlite3.Row
course_id = "53708338-1116-495f-ab5b-c9fd323ceb4c"

atoms = conn.execute(
    "SELECT statement, evidence_json FROM semantic_atoms WHERE course_id = ?",
    (course_id,),
).fetchall()

frags = {}
for f in conn.execute("SELECT fragment_id, text FROM source_fragments WHERE course_id = ?", (course_id,)):
    frags[f["fragment_id"]] = f["text"]

print(f"Testing {len(atoms)} atoms\n")
for row in atoms:
    stmt = row["statement"]
    ev = json.loads(row["evidence_json"])

    quoted = [m.group(1).strip() for m in _QUOTED.finditer(stmt)]
    leading = _LEADING.match(stmt)
    leading_val = leading.group(1).strip() if leading else None
    trailing = []
    for m in _TRAILING.finditer(stmt):
        for gi in range(1, 4):
            v = m.group(gi)
            if v:
                trailing.append(v.strip())
                break

    print(f"Statement: {stmt[:120]}")
    print(f"  Quoted: {quoted}")
    print(f"  Leading: {leading_val}")
    print(f"  Trailing: {trailing}")

    # Check if any candidate is in evidence
    all_candidates = quoted + ([leading_val] if leading_val else []) + trailing
    for cand in all_candidates:
        if not cand:
            continue
        for e in ev:
            fid = e["fragment_id"]
            ftext = frags.get(fid, "")
            found = cand in ftext
            print(f"    {'FOUND' if found else 'NOT FOUND'} '{cand}' in {fid[:25]}")
    print()

conn.close()
