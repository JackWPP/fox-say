"""Test MinerU upload with a real file."""
import json
import requests
from pathlib import Path

token = open("D:/fox-say/.env").read().split("MINERU_API_TOKEN=")[1].split("\n")[0].strip()
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Find a test PDF
test_files = list(Path("D:/fox-say/tmp_upload/线代课件/课件").glob("*.pdf"))
if not test_files:
    test_files = list(Path("D:/fox-say/tmp_upload").rglob("*.pdf"))
test_file = test_files[0]
print(f"Testing with: {test_file.name} ({test_file.stat().st_size} bytes)")

# Step 1: get upload URL
payload = {
    "files": [{"name": test_file.name}],
    "enable_formula": True,
    "enable_table": True,
    "is_ocr": True,
    "language": "ch",
}
resp = requests.post(
    "https://mineru.net/api/v4/file-urls/batch",
    json=payload,
    headers=headers,
    timeout=30,
)
data = resp.json()
batch_id = data["data"]["batch_id"]
upload_url = data["data"]["file_urls"][0]
print(f"Step 1 - code={data.get('code')}, batch_id={batch_id}")

# Step 2: PUT upload
print("Uploading to OSS...")
with open(test_file, "rb") as f:
    resp2 = requests.put(upload_url, data=f, timeout=120)
    print(f"Step 2 - status={resp2.status_code}")
    if resp2.status_code >= 400:
        print(f"Body: {resp2.text[:500]}")
    else:
        print("Upload OK")

# Step 3: Poll for result
print(f"Polling batch {batch_id}...")
import time
for i in range(60):
    time.sleep(3)
    resp3 = requests.get(
        f"https://mineru.net/api/v4/extract-results/batch/{batch_id}",
        headers=headers,
        timeout=15,
    )
    rdata = resp3.json().get("data", {})
    results = rdata.get("extract_result", [])
    if results:
        state = results[0].get("state", "")
        print(f"  [{i*3}s] state={state}")
        if state == "done":
            zip_url = results[0].get("full_zip_url")
            print(f"  Done! zip_url={zip_url[:80]}...")
            break
        elif state == "failed":
            print(f"  FAILED: {results[0].get('err_msg', '?')}")
            break
    else:
        progress = rdata.get("extract_progress", {})
        print(f"  [{i*3}s] waiting... progress={progress}")
