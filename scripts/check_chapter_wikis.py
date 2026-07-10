import sys, json, urllib.request

courses = {
    "76473f86": "数据库原理",
    "991c94c6": "计算机网络",
    "80b366d4": "技术经济",
    "158f2392": "概率论",
}

for cid_prefix, name in courses.items():
    url = f"http://127.0.0.1:8000/courses/{cid_prefix}%25/chapter-wikis"
    # use exact ID from course_indices
import sqlite3
conn = sqlite3.connect('data/foxsay.db')
course_ids = [r[0] for r in conn.execute("SELECT id FROM courses").fetchall()]
conn.close()

for cid in course_ids:
    url = f"http://127.0.0.1:8000/courses/{cid}/chapter-wikis"
    try:
        with urllib.request.urlopen(url) as resp:
            d = json.loads(resp.read())
            print(f"=== {cid[:8]}... ===")
            print(f"  Count: {d['count']}")
            for cw in d['chapter_wikis'][:4]:
                ov = cw['overview']
                title = cw['title']
                ch_id = cw['chapter_id']
                kcs = cw['key_concepts']
                print(f"  [{ch_id}] {title}")
                print(f"    overview({len(ov)}): {ov[:120]}...")
                print(f"    key_concepts({len(kcs)}): {kcs[:5]}")
            print()
    except Exception as e:
        print(f"Error for {cid[:8]}: {e}")
