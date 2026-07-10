"""FoxSay 文档解析器统一接口。

所有解析器（Docling、MinerU、MarkItDown、VLM）都实现 BaseDocumentParser，
输出统一的 UnifiedParserOutput，确保下游管线（归一化 → 切块 → 向量化）
不需要关心底层解析器的差异。
"""

import abc
import uuid
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """页面坐标系中的矩形区域（左上角原点）。"""

    coord_system: str = "TOPLEFT"
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0


class ExtractedAssetMeta(BaseModel):
    """被提取出的物理元素元信息（图片、表格截图、公式截图等）。"""

    element_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    element_type: str  # "Image" / "Table" / "Formula"
    sequential_label: str  # "[Image_1]", "[Table_1]"
    page_number: int  # 物理页码 (1-based)
    source_chapter: str = ""  # 最近的上级标题
    bounding_box: Optional[BoundingBox] = None
    storage_path: Optional[str] = None  # 图片的物理存储相对路径
    alt_text: Optional[str] = None  # VLM 生成的语义描述


class UnifiedParserOutput(BaseModel):
    """所有解析器的统一输出结构。"""

    document_id: str = Field(default_factory=lambda: f"doc_{uuid.uuid4().hex[:8]}")
    raw_input_type: str  # "DIGITAL_PDF" / "SCANNED_PDF" / "WORD" / "EXCEL" / "PPT" / "TEXT" / "USER_IMAGE"
    markdown_content: str  # 解析器原始输出的 Markdown（尚未经过归一化）
    extracted_assets: list[ExtractedAssetMeta] = Field(default_factory=list)
    page_count: int = 0
    parser_name: str = ""  # 标识是哪个解析器产出的，用于调试


class DocumentParsingException(Exception):
    """解析器统一异常类。失败时必须抛出此异常，不允许返回空字符串。"""

    def __init__(self, file_path: Path, message: str, original_error: Exception | None = None):
        detail = f"Parsing Error [{file_path}]: {message}"
        if original_error:
            detail += f" | {type(original_error).__name__}: {original_error}"
        super().__init__(detail)
        self.file_path = file_path
        self.message = message
        self.original_error = original_error


class BaseDocumentParser(abc.ABC):
    """FoxSay 解析器统一抽象基类。

    所有具体解析器（DoclingParser、MinerUParser、MarkItDownParser、VLMParser）
    都必须继承此类并实现 can_handle() 和 parse() 方法。
    """

    @abc.abstractmethod
    def can_handle(self, file_extension: str) -> bool:
        """判断当前解析器是否支持处理该文件后缀。"""

    @abc.abstractmethod
    def parse(self, file_path: Path, storage_root: Path, **kwargs) -> UnifiedParserOutput:
        """核心解析方法。

        Args:
            file_path: 待解析文件的物理路径
            storage_root: 图片等提取资产的物理存储根目录

        Returns:
            UnifiedParserOutput

        Raises:
            DocumentParsingException: 解析失败时必须抛出，不允许静默返回空内容
        """
