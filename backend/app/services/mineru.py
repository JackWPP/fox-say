"""MinerU 文档解析器（V4/V1 混合模式）。

路由策略：
1. 优先走 V4 Precision API（本地文件上传端点 /api/v4/file-urls/batch）
   - 支持 200MB / 200-600 页
   - 返回 ZIP（markdown + layout.json + images/）
   - 每日约 1000 页高优先级额度，超出仅降优先级不阻断
2. V4 失败或无 token 时降级到 V1 Agent API
   - 支持 10MB / 20 页
   - 仅返回 markdown
   - 无需 token，IP 限频
3. 都失败时由上层 parsing.py 降级到 Docling/pdfplumber
"""

import io
import json
import logging
import time
import uuid
import zipfile
from datetime import date
from pathlib import Path

import requests

from app.core.config import settings
from app.services.parser_interface import (
    BaseDocumentParser,
    DocumentParsingException,
    ExtractedAssetMeta,
    UnifiedParserOutput,
)

logger = logging.getLogger(__name__)

# ---- API 端点 ----
V4_BASE = "https://mineru.net/api/v4"
V1_BASE = "https://mineru.net/api/v1/agent"

# ---- 额度追踪 ----
_quota_date: date | None = None
_quota_pages_used: int = 0
V4_DAILY_PAGE_LIMIT = 1000  # 高优先级额度


def _check_v4_quota() -> bool:
    """检查 V4 今日是否还有高优先级额度。"""
    global _quota_date, _quota_pages_used
    today = date.today()
    if _quota_date != today:
        _quota_date = today
        _quota_pages_used = 0
    return _quota_pages_used < V4_DAILY_PAGE_LIMIT


def _track_v4_usage(pages: int) -> None:
    """记录 V4 使用页数。"""
    global _quota_date, _quota_pages_used
    today = date.today()
    if _quota_date != today:
        _quota_date = today
        _quota_pages_used = 0
    _quota_pages_used += pages
    logger.info("MinerU V4 quota: %d/%d pages used today", _quota_pages_used, V4_DAILY_PAGE_LIMIT)


class MinerUParser(BaseDocumentParser):
    """MinerU 文档解析器，V4/V1 混合模式。"""

    _SUPPORTED_EXTENSIONS = (
        ".pdf", ".png", ".jpg", ".jpeg",
        ".doc", ".docx", ".ppt", ".pptx",
    )

    def can_handle(self, file_extension: str) -> bool:
        return file_extension.lower() in self._SUPPORTED_EXTENSIONS

    def parse(self, file_path: Path, storage_root: Path, **kwargs) -> UnifiedParserOutput:
        token = settings.mineru_api_token
        file_size = file_path.stat().st_size

        # 尝试 V4（需要 token，且有额度）
        if token and _check_v4_quota() and file_size <= 200 * 1024 * 1024:
            try:
                return self._parse_v4_local(file_path, storage_root, token)
            except Exception as e:
                logger.warning("MinerU V4 failed for %s: %s, trying V1", file_path.name, e)

        # 降级到 V1（10MB / 20 页限制）
        if file_size <= 10 * 1024 * 1024:
            try:
                return self._parse_v1(file_path, storage_root)
            except Exception as e:
                logger.warning("MinerU V1 also failed for %s: %s", file_path.name, e)
                raise DocumentParsingException(
                    file_path, "All MinerU APIs failed", e
                )

        raise DocumentParsingException(
            file_path,
            f"File too large for V1 ({file_size} bytes > 10MB) and V4 unavailable",
        )

    # ================================================================
    # V4 Precision API — 本地文件上传（via batch endpoint）
    # ================================================================

    def _parse_v4_local(
        self, file_path: Path, storage_root: Path, token: str
    ) -> UnifiedParserOutput:
        """V4: 通过 /api/v4/file-urls/batch 上传本地文件。"""
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        img_output_dir = storage_root / doc_id
        img_output_dir.mkdir(parents=True, exist_ok=True)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Step 1: 获取预签名上传 URL + batch_id
        batch_id, upload_url = self._v4_get_upload_url(file_path.name, headers)

        # Step 2: PUT 上传文件
        self._put_file(file_path, upload_url)

        # Step 3: 轮询 batch 结果
        zip_url = self._v4_poll_batch(batch_id, headers)

        # Step 4: 下载解压 ZIP
        raw_markdown, assets, page_count = self._v4_extract_zip(
            zip_url, img_output_dir, doc_id
        )

        _track_v4_usage(page_count)

        return UnifiedParserOutput(
            document_id=doc_id,
            raw_input_type="SCANNED_PDF",
            markdown_content=raw_markdown,
            extracted_assets=assets,
            page_count=page_count,
            parser_name="MinerU-V4",
        )

    def _v4_get_upload_url(self, file_name: str, headers: dict) -> tuple[str, str]:
        """V4: POST /api/v4/file-urls/batch 获取预签名上传 URL。"""
        payload = {
            "files": [{"name": file_name}],
            "enable_formula": True,
            "enable_table": True,
            "is_ocr": True,
            "language": "ch",
        }
        for attempt in range(3):
            try:
                resp = requests.post(
                    f"{V4_BASE}/file-urls/batch",
                    json=payload,
                    headers=headers,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != 0:
                    raise ValueError(f"V4 batch error: {data.get('msg')}")
                batch_id = data["data"]["batch_id"]
                file_urls = data["data"]["file_urls"]
                if not file_urls:
                    raise ValueError("V4 batch: no file_urls returned")
                logger.info("MinerU V4 upload URL obtained for %s", file_name)
                return batch_id, file_urls[0]
            except Exception as e:
                if attempt == 2:
                    raise DocumentParsingException(
                        Path(file_name), f"V4 get upload URL failed: {e}", e
                    )
                time.sleep(2 ** attempt)
        raise DocumentParsingException(Path(file_name), "V4 upload URL unreachable")

    def _put_file(self, file_path: Path, upload_url: str) -> None:
        """PUT 上传文件到预签名 URL。"""
        for attempt in range(3):
            try:
                with open(file_path, "rb") as f:
                    resp = requests.put(upload_url, data=f, timeout=120)
                    resp.raise_for_status()
                logger.info("File uploaded to MinerU: %s (%d bytes)", file_path.name, file_path.stat().st_size)
                return
            except Exception as e:
                if attempt == 2:
                    raise DocumentParsingException(file_path, f"PUT upload failed: {e}", e)
                time.sleep(2 ** attempt)

    def _v4_poll_batch(self, batch_id: str, headers: dict) -> str:
        """V4: 轮询 batch 结果，返回 ZIP 下载 URL。"""
        max_time = settings.mineru_max_poll_time
        interval = settings.mineru_poll_interval
        start = time.time()

        while time.time() - start < max_time:
            time.sleep(interval)
            try:
                resp = requests.get(
                    f"{V4_BASE}/extract-results/batch/{batch_id}",
                    headers=headers,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})

                # 实际格式: data.extract_result = [{state, full_zip_url, ...}]
                results = data.get("extract_result", [])
                if not results:
                    # 可能还在排队中，data 里没有 extract_result
                    continue

                result = results[0]
                state = result.get("state", "")

                if state == "done":
                    zip_url = result.get("full_zip_url")
                    if not zip_url:
                        raise ValueError(f"V4 done but no zip URL: {result}")
                    logger.info("MinerU V4 batch %s completed", batch_id)
                    return zip_url
                elif state == "failed":
                    raise ValueError(f"V4 failed: {result.get('err_msg', '?')}")
                else:
                    progress = data.get("extract_progress", {})
                    if progress:
                        logger.debug(
                            "V4 progress: %s", progress
                        )
            except ValueError:
                raise
            except Exception as e:
                logger.warning("V4 poll error: %s", e)
                continue

        raise DocumentParsingException(
            Path("unknown"), f"V4 batch {batch_id} timed out after {max_time}s"
        )

    def _v4_extract_zip(
        self, zip_url: str, img_dir: Path, doc_id: str
    ) -> tuple[str, list[ExtractedAssetMeta], int]:
        """V4: 下载 ZIP 并解压，返回 (markdown, assets, page_count)。"""
        try:
            resp = requests.get(zip_url, timeout=60)
            resp.raise_for_status()
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
        except Exception as e:
            raise DocumentParsingException(Path("unknown"), f"V4 ZIP download failed: {e}", e)

        # 读取 Markdown
        raw_markdown = ""
        for name in zf.namelist():
            if name.endswith(".md"):
                raw_markdown = zf.read(name).decode("utf-8")
                break
        if not raw_markdown:
            raise DocumentParsingException(Path("unknown"), "V4 ZIP contains no markdown")

        # 读取 layout.json 估算页数
        page_count = 0
        for layout_name in ("layout.json", "content_list.json"):
            try:
                layout_data = json.loads(zf.read(layout_name).decode("utf-8"))
                if isinstance(layout_data, list):
                    pages_seen = set()
                    for item in layout_data:
                        p = item.get("page_idx", item.get("page", 0))
                        pages_seen.add(p)
                    page_count = max(page_count, len(pages_seen))
                break
            except (KeyError, json.JSONDecodeError):
                continue

        # 提取图片
        assets: list[ExtractedAssetMeta] = []
        img_counter = 0
        for info in zf.infolist():
            if info.filename.startswith("images/") and not info.is_dir():
                img_counter += 1
                img_name = f"page_1_img_{img_counter}.png"
                with open(img_dir / img_name, "wb") as f:
                    f.write(zf.read(info.filename))
                assets.append(ExtractedAssetMeta(
                    element_id=f"img_{uuid.uuid4().hex[:8]}",
                    element_type="Image",
                    sequential_label=f"[Image_{img_counter}]",
                    page_number=1,
                    storage_path=f"images/{doc_id}/{img_name}",
                ))

        logger.info(
            "V4 extracted: %d chars markdown, %d images, ~%d pages",
            len(raw_markdown), img_counter, page_count,
        )
        return raw_markdown, assets, max(page_count, 1)

    # ================================================================
    # V1 Agent API — 轻量 fallback
    # ================================================================

    def _parse_v1(self, file_path: Path, storage_root: Path) -> UnifiedParserOutput:
        """V1 Agent API: 本地文件直接上传，返回 markdown-only 结果。"""
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        # Step 1: 获取预签名 URL + task_id
        payload = json.dumps({
            "file_name": file_path.name,
            "language": "ch",
            "enable_table": True,
            "is_ocr": True,
            "enable_formula": True,
        }).encode()

        task_id, file_upload_url = None, None
        for attempt in range(3):
            try:
                req = requests.post(
                    f"{V1_BASE}/parse/file",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=15,
                )
                req.raise_for_status()
                resp_data = req.json()
                if resp_data.get("code") != 0:
                    raise ValueError(f"V1 submit error: {resp_data.get('msg')}")
                task_id = resp_data["data"]["task_id"]
                file_upload_url = resp_data["data"]["file_url"]
                break
            except Exception as e:
                if attempt == 2:
                    raise DocumentParsingException(file_path, f"V1 submit failed: {e}", e)
                time.sleep(2 ** attempt)

        # Step 2: PUT 上传
        self._put_file(file_path, file_upload_url)

        # Step 3: 轮询
        markdown_url = self._v1_poll(task_id)

        # Step 4: 下载
        raw_markdown = self._v1_download(markdown_url)

        return UnifiedParserOutput(
            document_id=doc_id,
            raw_input_type="SCANNED_PDF",
            markdown_content=f"<!-- PAGE_START 1 -->\n{raw_markdown}\n<!-- PAGE_END 1 -->",
            extracted_assets=[],
            parser_name="MinerU-V1",
        )

    def _v1_poll(self, task_id: str) -> str:
        start = time.time()
        while time.time() - start < 180:
            time.sleep(3)
            try:
                resp = requests.get(f"{V1_BASE}/parse/{task_id}", timeout=10)
                resp.raise_for_status()
                data = resp.json()["data"]
                state = data.get("state", "")
                if state == "done":
                    md_url = data.get("markdown_url")
                    if not md_url:
                        raise ValueError("V1 done but no markdown_url")
                    return md_url
                elif state == "failed":
                    raise ValueError(f"V1 failed: {data.get('err_msg', '?')}")
            except ValueError:
                raise
            except Exception as e:
                logger.warning("V1 poll error: %s", e)
                continue
        raise DocumentParsingException(
            Path("unknown"), f"V1 task {task_id} timed out"
        )

    def _v1_download(self, markdown_url: str) -> str:
        try:
            resp = requests.get(markdown_url, timeout=30)
            resp.raise_for_status()
            text = resp.content.decode("utf-8")
            if not text.strip():
                raise ValueError("Empty markdown")
            return text
        except Exception as e:
            raise DocumentParsingException(Path("unknown"), f"V1 download failed: {e}", e)


# ---- 向后兼容 ----
def parse_pdf_mineru(file_path: str, language: str = "ch") -> tuple[str | None, str | None]:
    storage_root = Path(settings.upload_root) / "storage" / "images"
    storage_root.mkdir(parents=True, exist_ok=True)
    parser = MinerUParser()
    try:
        output = parser.parse(Path(file_path), storage_root)
        return output.markdown_content, None
    except DocumentParsingException as e:
        return None, str(e)
