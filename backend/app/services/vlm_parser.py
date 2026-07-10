"""VLM 多模态图片解析器。

对用户上传的单张图片（.png/.jpg/.jpeg），调用 DeepSeek VL API
做端到端的结构化 Markdown 提取。
"""

import base64
import logging
import uuid
from pathlib import Path

from app.core.config import settings
from app.services.parser_interface import (
    BaseDocumentParser,
    DocumentParsingException,
    ExtractedAssetMeta,
    UnifiedParserOutput,
)

logger = logging.getLogger(__name__)

VLM_PROMPT = (
    "请仔细分析这张图片，提取其中的所有文字、表格、公式和图表信息。"
    "输出格式要求：\n"
    "1. 用 Markdown 格式输出\n"
    "2. 表格用 GFM 管线表格格式\n"
    "3. 数学公式用 LaTeX 格式（行内 $...$，块级 $$...$$）\n"
    "4. 如果有流程图或示意图，用文字描述其内容\n"
    "5. 保持原始的结构层级关系\n"
)


class VLMImageParser(BaseDocumentParser):
    """用视觉大模型解析用户上传的图片。"""

    def can_handle(self, file_extension: str) -> bool:
        return file_extension.lower() in (".png", ".jpg", ".jpeg", ".webp")

    def parse(self, file_path: Path, storage_root: Path, **kwargs) -> UnifiedParserOutput:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        img_output_dir = storage_root / "user_uploads"
        img_output_dir.mkdir(parents=True, exist_ok=True)

        # 保存原图到物理存储
        ext = file_path.suffix
        stored_name = f"{doc_id}{ext}"
        stored_path = img_output_dir / stored_name
        if file_path != stored_path:
            import shutil
            shutil.copy2(str(file_path), str(stored_path))

        # 调用 VLM API
        markdown_content = self._call_vlm(file_path)

        asset = ExtractedAssetMeta(
            element_id=f"img_{uuid.uuid4().hex[:8]}",
            element_type="Image",
            sequential_label="[Image_1]",
            page_number=1,
            source_chapter="",
            storage_path=f"images/user_uploads/{stored_name}",
            alt_text="用户上传的图片（VLM 已提取内容）",
        )

        return UnifiedParserOutput(
            document_id=doc_id,
            raw_input_type="USER_IMAGE",
            markdown_content=f"<!-- PAGE_START 1 -->\n{markdown_content}\n<!-- PAGE_END 1 -->",
            extracted_assets=[asset],
            page_count=1,
            parser_name="VLM-Image",
        )

    def _call_vlm(self, file_path: Path) -> str:
        """调用 DeepSeek VL API 提取图片内容。"""
        from openai import OpenAI

        # 读取图片并 base64 编码
        with open(file_path, "rb") as f:
            img_data = base64.standard_b64encode(f.read()).decode("utf-8")

        suffix = file_path.suffix.lower().lstrip(".")
        mime_type = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }.get(suffix, "image/png")

        client = OpenAI(
            api_key=settings.deepseek_api_key or "placeholder",
            base_url=settings.deepseek_api_base,
            timeout=60,
        )

        try:
            response = client.chat.completions.create(
                model=settings.deepseek_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{img_data}",
                                },
                            },
                            {
                                "type": "text",
                                "text": VLM_PROMPT,
                            },
                        ],
                    }
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content or ""
            if not content.strip():
                raise DocumentParsingException(file_path, "VLM returned empty content")
            return content.strip()
        except DocumentParsingException:
            raise
        except Exception as e:
            raise DocumentParsingException(file_path, "VLM API call failed", e)
