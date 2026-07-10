import sqlite3, json
conn = sqlite3.connect('data/foxsay.db')

# Check wiki_chapters for 数据库原理 (76473f86)
print("=== wiki_chapters for 数据库原理 ===")
rows = conn.execute("SELECT chapter_id, data_json FROM wiki_chapters WHERE course_id LIKE '76473f86%'").fetchall()
print(f"Total chapters: {len(rows)}")
for r in rows[:5]:
    ch_id = r[0]
    data = json.loads(r[1])
    ov = data.get('overview', '')
    title = data.get('title', '')
    kcs = data.get('key_concepts', [])
    print(f"\n  [{ch_id}] {title}")
    print(f"  overview({len(ov)}): {ov[:200]}")
    print(f"  key_concepts({len(kcs)}): {kcs[:5]}")

# Check course_indices
print("\n\n=== course_indices ===")
rows = conn.execute("SELECT course_id, content FROM course_indices").fetchall()
for r in rows:
    cid = r[0]
    content = r[1]
    if len(content) > 500:
        content = content[:500] + "..."
    print(f"\nCourse: {cid[:8]}...")
    print(f"  content({len(r[1])}): {content}")
