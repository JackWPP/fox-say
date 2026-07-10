import sqlite3
conn = sqlite3.connect('data/foxsay.db')
tables = ['courses', 'wiki_chapters', 'wiki_kcs', 'course_indices', 'dmaps']
for t in tables:
    cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
    print(f"=== {t} ===")
    for c in cols:
        print(f"  {c[1]}: {c[2]}")
    print()
