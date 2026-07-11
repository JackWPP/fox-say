"""Test the full material indexer pipeline to find the real error."""
import os
import glob
import traceback
import asyncio

from app.db.sqlite_store import SqliteStore
from app.services.material_indexer import MaterialIndexer

# Find the test file
pattern = "D:/fox-say/uploads/6a79f553-aab2-4db2-964d-778edf583fdf/6681f26e*"
matches = glob.glob(pattern)
test_file = matches[0]
print(f"Test file: {test_file}")
print(f"Exists: {os.path.isfile(test_file)}")

# Use the real store
store = SqliteStore("D:/fox-say/data/foxsay.db")

# Get the material
course_id = "6a79f553-aab2-4db2-964d-778edf583fdf"
material_id = "6681f26e-be71-4da1-8de0-80b0f8979dc2"
material = store.get_material(course_id, material_id)
print(f"Material: {material.filename if material else 'NOT FOUND'}")
print(f"Material kind: {material.kind if material else 'N/A'}")
print(f"Material revision: {material.revision if material else 'N/A'}")

# Get the job
jobs = store._conn.execute(
    "SELECT * FROM knowledge_jobs WHERE material_id = ? ORDER BY created_at DESC LIMIT 1",
    (material_id,),
).fetchone()
if jobs:
    print(f"Job: {dict(jobs)}")

# Now test the parsing + normalization + fragments + embedding step by step
from app.services.parsing import parse_document_full
from app.services.normalizer import NormalizationEngine
from app.services.source_fragments import build_source_fragments
from app.services.embedding import embed_texts

print("\n--- Step 1: Parse ---")
try:
    output = parse_document_full(test_file, material.kind)
    print(f"  Parser: {output.parser_name}, markdown len: {len(output.markdown_content)}")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
    exit()

print("\n--- Step 2: Normalize ---")
try:
    normalized = NormalizationEngine().normalize(
        output.markdown_content,
        output.raw_input_type,
        output.extracted_assets,
    )
    print(f"  Normalized markdown len: {len(normalized.markdown_content)}")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
    exit()

print("\n--- Step 3: Build fragments ---")
try:
    fragments = build_source_fragments(
        normalized.markdown_content,
        course_id=course_id,
        material_id=material_id,
        material_revision=1,
        parser_name=output.parser_name or "unknown",
    )
    print(f"  Fragments: {len(fragments)}")
    if fragments:
        print(f"  First fragment text length: {len(fragments[0].text)}")
        print(f"  Longest fragment text length: {max(len(f.text) for f in fragments)}")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
    exit()

print("\n--- Step 4: Embed ---")
try:
    texts = [f.text for f in fragments]
    # Check for empty or too-long texts
    for i, t in enumerate(texts):
        if not t.strip():
            print(f"  WARNING: fragment {i} is empty!")
        if len(t) > 8000:
            print(f"  WARNING: fragment {i} is very long: {len(t)} chars")
    embeddings = embed_texts(texts)
    print(f"  Embeddings: {len(embeddings)}, dim: {len(embeddings[0]) if embeddings else 0}")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()

store._conn.close()
