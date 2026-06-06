"""End-to-end: incremental wiki rebuild (HEC-6 + Merkle diff + KC invalidation)."""
import sys
import time
import json

import httpx

BASE = "http://127.0.0.1:8000"


def banner(msg):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}", flush=True)


def main() -> int:
    sys.path.insert(0, "D:/fox-say/backend")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    from app.db.sqlite_store import SqliteStore
    from app.core.config import settings as cfg
    from app.schemas.foxsay import MerkleTree
    from app.services.wiki_builder import build_wiki

    with httpx.Client(base_url=BASE, timeout=120.0) as c:
        banner("1. Create course")
        r = c.post("/courses", json={"title": "Incremental Test", "exam_date": "2026-07-20"})
        course_id = r.json()["id"]
        print(f"  course_id: {course_id}")

        store = SqliteStore(db_path=cfg.sqlite_path)

        # First build: chapters A, B, C
        banner("2. First build (chapters A, B, C)")
        chunks_v1 = [
            {"text": "Chapter A: introduction to signals.", "heading": "Chapter A: Intro", "level": 1, "page": 1},
            {"text": "Chapter B: about convolution theorem.", "heading": "Chapter B: Convolution", "level": 1, "page": 2},
            {"text": "Chapter C: about Fourier series.", "heading": "Chapter C: Fourier", "level": 1, "page": 3},
        ]
        result1 = build_wiki(course_id, chunks_v1, store, source_file="v1.txt")
        print(f"  KCs created: {len(result1.kcs)}")
        for kc in result1.kcs:
            print(f"    - {kc.name}")

        # Snapshot pre-incremental state
        pre_kcs = store.get_kcs_by_course(course_id, include_invalid=False)
        pre_merkle_json = store.get_merkle_tree(course_id)
        pre_merkle = MerkleTree.model_validate_json(pre_merkle_json) if pre_merkle_json else None
        print(f"  pre KCs: {len(pre_kcs)}, pre merkle nodes: {len(pre_merkle.nodes) if pre_merkle else 0}")

        # Second build: chapters B (modified), C (unchanged), D (new) — A removed
        banner("3. Second build (B modified, C unchanged, D new, A removed)")
        chunks_v2 = [
            {"text": "Chapter B v2: modified text about convolution.", "heading": "Chapter B: Convolution", "level": 1, "page": 2},
            {"text": "Chapter C: about Fourier series.", "heading": "Chapter C: Fourier", "level": 1, "page": 3},
            {"text": "Chapter D: brand new topic about Laplace transform.", "heading": "Chapter D: Laplace", "level": 1, "page": 4},
        ]
        result2 = build_wiki(
            course_id, chunks_v2, store,
            old_merkle_tree=pre_merkle,
            source_file="v2.txt",
        )
        print(f"  KCs created: {len(result2.kcs)}")
        for kc in result2.kcs:
            print(f"    - {kc.name}")

        # Check invalidation
        banner("4. Verify incremental semantics")
        all_kcs = store.get_kcs_by_course(course_id, include_invalid=True)
        valid_kcs = store.get_kcs_by_course(course_id, include_invalid=False)
        invalid_kcs = [kc for kc in all_kcs if kc.invalid_at is not None]
        print(f"  total KCs (incl. invalid): {len(all_kcs)}")
        print(f"  valid KCs: {len(valid_kcs)}")
        print(f"  invalid KCs: {len(invalid_kcs)}")
        for kc in invalid_kcs:
            print(f"    - {kc.name} (invalid_at={kc.invalid_at})")

        # Verify merkle tree was updated
        post_merkle_json = store.get_merkle_tree(course_id)
        post_merkle = MerkleTree.model_validate_json(post_merkle_json)
        print(f"  post merkle root_hash: {post_merkle.root_hash[:16]}...")
        if pre_merkle and pre_merkle.root_hash == post_merkle.root_hash:
            print(f"  WARN: merkle root unchanged (no diff detected)")
        else:
            print(f"  OK: merkle root changed as expected")

        # Check dmap was updated
        dmap_json = store.get_dmap(course_id)
        dmap = json.loads(dmap_json)
        chapter_titles = [c["title"] for c in dmap["root"].get("children", [])]
        print(f"  dmap chapters: {chapter_titles}")

        banner("DONE")
        return 0


if __name__ == "__main__":
    sys.exit(main())
