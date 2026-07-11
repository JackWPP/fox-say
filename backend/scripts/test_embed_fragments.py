"""Test which fragments cause embedding errors."""
import glob
import os

from app.services.parsing import parse_document_full
from app.services.normalizer import NormalizationEngine
from app.services.source_fragments import build_source_fragments
from app.services.embedding import embed_text

pattern = "D:/fox-say/uploads/6a79f553-aab2-4db2-964d-778edf583fdf/6681f26e*"
test_file = glob.glob(pattern)[0]

output = parse_document_full(test_file, "pdf")
normalized = NormalizationEngine().normalize(
    output.markdown_content, output.raw_input_type, output.extracted_assets
)
fragments = build_source_fragments(
    normalized.markdown_content,
    course_id="test",
    material_id="test",
    material_revision=1,
    parser_name="test",
)

print(f"Total fragments: {len(fragments)}")

# Test embedding one by one to find the problematic ones
failed = []
for i, f in enumerate(fragments):
    text = f.text.strip()
    if not text:
        print(f"  [{i}] EMPTY - skipping")
        continue
    try:
        emb = embed_text(text)
        if not emb:
            print(f"  [{i}] EMPTY EMBEDDING for text len={len(text)}")
    except Exception as e:
        print(f"  [{i}] FAILED len={len(text)}: {e}")
        failed.append(i)
        if len(failed) > 5:
            print("  ... stopping (too many failures)")
            break

if failed:
    print(f"\nFailed fragments: {failed}")
    # Show the first failed fragment
    if failed:
        idx = failed[0]
        print(f"\nFragment {idx} text ({len(fragments[idx].text)} chars):")
        print(repr(fragments[idx].text[:300]))
else:
    print("\nAll fragments embedded successfully!")
