"""MinerU API 客户端 — PDF 解析 fallback。

使用 MinerU Agent 轻量解析 API (无需 token, IP 限频)。
当 pdfplumber 提取内容不足时,用 MinerU 做 fallback。

API 流程:
1. POST /api/v1/agent/parse/file → 获取 task_id + file_url
2. PUT file_url → 上传文件到 OSS
3. GET /api/v1/agent/parse/{task_id} → 轮询直到 done
4. GET markdown_url → 下载解析结果

限制: 10MB / 20 页 / 单文件
"""

import logging
import time
import urllib.request
import json

logger = logging.getLogger(__name__)

MINERU_BASE = "https://mineru.net/api/v1/agent"
MINERU_TIMEOUT = 120  # 轮询总超时(秒)
MINERU_POLL_INTERVAL = 3  # 轮询间隔(秒)


def parse_pdf_mineru(file_path: str, language: str = "ch") -> tuple[str | None, str | None]:
    """用 MinerU 解析 PDF。

    Returns:
        (markdown_content, error_message)。成功时 error_message 为 None。
        失败时 markdown_content 为 None，error_message 描述具体原因。
    """
    import os

    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    if file_size > 10 * 1024 * 1024:
        return None, f"文件过大 ({file_size} bytes), 超过 10MB 限制"

    # Step 1: 获取签名上传 URL + task_id
    try:
        req_data = json.dumps({
            "file_name": file_name,
            "language": language,
            "enable_table": True,
            "is_ocr": True,
            "enable_formula": True,
        }).encode()
        req = urllib.request.Request(
            f"{MINERU_BASE}/parse/file",
            data=req_data,
            headers={"Content-Type": "application/json"},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
        if resp.get("code") != 0:
            return None, f"submit 失败: {resp.get('msg')}"
        task_id = resp["data"]["task_id"]
        file_url = resp["data"]["file_url"]
    except Exception as e:
        return None, f"submit 请求失败: {e}"

    # Step 2: PUT 上传文件到 OSS (重试 3 次)
    for attempt in range(3):
        try:
            with open(file_path, "rb") as f:
                put_req = urllib.request.Request(file_url, data=f.read(), method="PUT")
                urllib.request.urlopen(put_req, timeout=30)
            break
        except Exception as e:
            if attempt == 2:
                return None, f"上传 OSS 失败 (重试 3 次): {e}"
            time.sleep(2)

    # Step 3: 轮询任务结果
    markdown_url = None
    start = time.time()
    while time.time() - start < MINERU_TIMEOUT:
        time.sleep(MINERU_POLL_INTERVAL)
        try:
            poll_req = urllib.request.Request(f"{MINERU_BASE}/parse/{task_id}")
            poll_resp = json.loads(urllib.request.urlopen(poll_req, timeout=10).read().decode())
            state = poll_resp["data"]["state"]
            if state == "done":
                markdown_url = poll_resp["data"].get("markdown_url")
                break
            elif state == "failed":
                return None, f"解析失败: {poll_resp['data'].get('err_msg')}"
        except Exception as e:
            logger.warning("MinerU: poll error: %s", e)
            continue

    if not markdown_url:
        return None, f"轮询超时 ({MINERU_TIMEOUT}s)"

    # Step 4: 下载 Markdown 结果
    try:
        md_resp = urllib.request.urlopen(markdown_url, timeout=30)
        return md_resp.read().decode("utf-8"), None
    except Exception as e:
        return None, f"下载结果失败: {e}"
