"""Test parse_document_full directly to find the real error."""
import os
import glob
import traceback

# Find the actual file using glob
pattern = "D:/fox-say/uploads/6a79f553-aab2-4db2-964d-778edf583fdf/6681f26e*"
matches = glob.glob(pattern)
print(f"Glob matches: {matches}")

if not matches:
    # Try listing the directory
    d = "D:/fox-say/uploads/6a79f553-aab2-4db2-964d-778edf583fdf"
    if os.path.isdir(d):
        files = os.listdir(d)
        print(f"Dir has {len(files)} files:")
        for f in files:
            full = os.path.join(d, f)
            print(f"  {f} -> exists={os.path.isfile(full)} size={os.path.getsize(full) if os.path.isfile(full) else 0}")
    else:
        print(f"Dir does not exist: {d}")
    exit()

test_file = matches[0]
print(f"Testing with: {test_file}")
print(f"File exists: {os.path.isfile(test_file)}")
print(f"File size: {os.path.getsize(test_file)}")

from app.services.parsing import parse_document_full

try:
    output = parse_document_full(test_file, "pdf")
    print(f"Parser: {output.parser_name}")
    print(f"Markdown length: {len(output.markdown_content)}")
    print(f"Page count: {output.page_count}")
    print(f"Assets: {len(output.extracted_assets)}")
    print("First 500 chars:")
    print(output.markdown_content[:500])
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
