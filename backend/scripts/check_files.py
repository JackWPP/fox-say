"""Check uploaded files on disk."""
import sqlite3
import os
from pathlib import Path

conn = sqlite3.connect("D:/fox-say/data/foxsay.db")
conn.row_factory = sqlite3.Row
mats = conn.execute(
    "SELECT id, course_id, filename, kind, status FROM materials ORDER BY rowid DESC LIMIT 6"
).fetchall()

for m in mats:
    print(f"Material: {m['filename']} kind={m['kind']} status={m['status']}")
    # Check file on disk
    upload_dir = os.path.join("D:/fox-say/uploads", m["course_id"])
    if os.path.isdir(upload_dir):
        files = os.listdir(upload_dir)
        matching = [f for f in files if m["id"] in f]
        if matching:
            fpath = os.path.join(upload_dir, matching[0])
            exists = os.path.isfile(fpath)
            size = os.path.getsize(fpath) if exists else 0
            print(f"  File: {matching[0]} exists={exists} size={size}")
        else:
            print(f"  No matching file in {upload_dir}")
            print(f"  Dir contents: {files[:5]}")
    else:
        print(f"  Upload dir does not exist: {upload_dir}")
    print()

conn.close()
