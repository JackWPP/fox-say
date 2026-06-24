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


def parse_pdf_mineru(file_path: str, language: str = "ch") -> str:
    """用 MinerU 解析 PDF,返回 Markdown 文本。失败返回空字符串。"""
    import os

    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    if file_size > 10 * 1024 * 1024:
        logger.warning("MinerU: file too large (%d bytes), limit 10MB", file_size)
        return ""

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
            logger.error("MinerU: submit failed: %s", resp.get("msg"))
            return ""
        task_id = resp["data"]["task_id"]
        file_url = resp["data"]["file_url"]
    except Exception as e:
        logger.error("MinerU: submit request failed: %s", e)
        return ""

    # Step 2: PUT 上传文件到 OSS (重试 3 次)
    for attempt in range(3):
        try:
            with open(file_path, "rb") as f:
                put_req = urllib.request.Request(file_url, data=f.read(), method="PUT")
                urllib.request.urlopen(put_req, timeout=30)
            break
        except Exception as e:
            if attempt == 2:
                logger.error("MinerU: file upload failed after 3 attempts: %s", e)
                return ""
            logger.warning("MinerU: upload attempt %d failed: %s, retrying...", attempt + 1, e)
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
                logger.error("MinerU: parse failed: %s", poll_resp["data"].get("err_msg"))
                return ""
        except Exception as e:
            logger.warning("MinerU: poll error: %s", e)
            continue

    if not markdown_url:
        logger.error("MinerU: timeout after %ds", MINERU_TIMEOUT)
        return ""

    # Step 4: 下载 Markdown 结果
    try:
        md_resp = urllib.request.urlopen(markdown_url, timeout=30)
        return md_resp.read().decode("utf-8")
    except Exception as e:
        logger.error("MinerU: download result failed: %s", e)
        return ""
