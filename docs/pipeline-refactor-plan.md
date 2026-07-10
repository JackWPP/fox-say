# FoxSay 文档管线重构计划

## 目标

将当前"markitdown 统一入口 + 500字符盲切"的粗糙管线，重构为"多路路由 + 语义感知切块 + 结构化归一化"的生产级管线，从根本上提升检索质量和回答准确性。

## 决策记录

| 决策项 | 选择 | 理由 |
|--------|------|------|
| MinerU API | 迁移到 V4（JWT 鉴权） | 支持更大文件、HTML 多格式输出、公式/表格专项识别 |
| PDF 策略 | 双轨制：电子版 → Docling，扫描件 → MinerU 云端 | 本地精确结构 + 云端重度 OCR，互补 |
| 切块库 | LangChain TextSplitter | 功能全面，MarkdownHeaderTextSplitter + RecursiveCharacterTextSplitter |
| 数据库 | 保持 SQLite，新增 extracted_assets 表 | 避免引入 PostgreSQL 运维，当前规模足够 |
| 重构范围 | 全量：解析 + 切块 + 表格保护 + 页面锚定 + 图片存储 | 一次性完成，避免多次重构 |

## 现有依赖状态

| 依赖 | 状态 | 动作 |
|------|------|------|
| PyMuPDF (fitz) | 已安装 v1.26.4 | 保留，用于 PDF 扫描件探测 |
| Docling | 未安装 | 需安装 `docling` |
| LangChain | 未安装 | 需安装 `langchain-text-splitters` |
| markitdown | 已安装 | 保留，用于 Word/Excel 轻量解析 |
| pdfplumber | 已安装 | 保留，作为 Docling 的 fallback |
| python-pptx | 已安装 | 保留，PPT 解析 |
| MinerU SDK | 当前用 urllib 手写 | 改用 `requests` 重写（已在依赖中） |

## 架构总览

```
[用户上传文件]
      │
      ▼
[文件类型路由]
      │
      ├── .docx/.xlsx/.html → [MarkItDown 分支] → 轻量 Markdown
      │
      ├── .pdf ────────────→ [PDF 探测路由]
      │                         │
      │                         ├── 电子版 → [Docling 本地解析]
      │                         │             → 结构树 + TableFormer 表格
      │                         │
      │                         └── 扫描件 → [MinerU V4 云端 API]
      │                                       → 高精度 OCR + UniMERNet 公式
      │                                       → ZIP 包（markdown + images + layout）
      │
      ├── .ppt/.pptx ──────→ [python-pptx 分支]（当前实现保留）
      │
      ├── .txt/.md ────────→ [直接读取]
      │
      └── .png/.jpg/.jpeg ─→ [VLM 多模态分支]
                              → DeepSeek VL 端到端 Markdown 提取
                              → 原图保存到物理存储卷
      │
      ▼
[归一化引擎 NormalizationEngine]
      │
      ├── 页面锚定：<!-- PAGE_START N --> / <!-- PAGE_END N -->
      ├── 表格保护：复杂表格（合并单元格）→ HTML <table> 格式
      ├── 全局编号：[Image_1], [Table_1], [Formula_1]
      ├── 公式对齐：行内 $...$，块级 $$...$$
      └── 提取资产记录：写入 extracted_assets 表
      │
      ▼
[语义切块 SemanticChunker]（LangChain）
      │
      ├── MarkdownHeaderTextSplitter：按 # / ## / ### 标题层级切分
      ├── 表格不可分割：整个 <table> 或 GFM 表格作为一个 chunk
      ├── 上下文补齐：每个 chunk 自动 prepend 父级标题路径
      └── 段落边界感知：不在句子/公式/表格中间切断
      │
      ▼
[Embedding + Qdrant 存储]
      │
      ▼
[检索层统一语义评分]（修复 _text_overlap_score 问题）
```

## 分阶段实施

### Phase 1：解析器接口与统一输出

**新建文件**：`backend/app/services/parser_interface.py`

```python
class BoundingBox(BaseModel):
    coord_system: str = "TOPLEFT"
    x0: float
    y0: float
    x1: float
    y1: float

class ExtractedAssetMeta(BaseModel):
    element_id: str          # 全局唯一 UUID
    element_type: str        # "Image" / "Table" / "Formula"
    sequential_label: str    # "[Image_1]", "[Table_1]"
    page_number: int         # 物理页码 (1-based)
    source_chapter: str      # 最近的上级标题
    bounding_box: BoundingBox | None = None
    storage_path: str | None = None
    alt_text: str | None = None

class UnifiedParserOutput(BaseModel):
    document_id: str
    raw_input_type: str      # "DIGITAL_PDF" / "SCANNED_PDF" / "WORD" / "USER_IMAGE" 等
    markdown_content: str    # 符合 FoxSay 规范的归一化 Markdown
    extracted_assets: list[ExtractedAssetMeta] = []

class DocumentParsingException(Exception): ...

class BaseDocumentParser(ABC):
    def can_handle(self, file_extension: str) -> bool: ...
    def parse(self, file_path: Path, storage_root: Path, **kwargs) -> UnifiedParserOutput: ...
```

**涉及文件**：
- 新建 `parser_interface.py`
- 修改 `parsing.py` → 重构为路由器，调度到各分支解析器
- 修改 `parsing_docling.py` → 实现 `BaseDocumentParser` 接口
- 修改 `mineru.py` → 实现 `BaseDocumentParser` 接口 + V4 API 迁移

### Phase 2：PDF 扫描件探测

**修改文件**：`backend/app/services/parsing.py`

在 PDF 解析入口增加 PyMuPDF 探测逻辑：

```python
def detect_pdf_type(file_path: str) -> str:
    """用 PyMuPDF 快速探测 PDF 是电子版还是扫描件。
    判定标准：>30% 的页面文字 <20 字符且有图片 → 扫描件。
    """
    import fitz
    doc = fitz.open(file_path)
    total = len(doc)
    scanned = 0
    for page in doc:
        text_len = len(page.get_text().strip())
        has_images = len(page.get_images()) > 0
        if text_len < 20 and has_images:
            scanned += 1
    doc.close()
    return "SCANNED_PDF" if (scanned / max(total, 1)) > 0.3 else "DIGITAL_PDF"
```

**路由逻辑**：
```
PDF 上传 → detect_pdf_type()
  ├── DIGITAL_PDF → Docling（本地）
  │                    └── 失败 → pdfplumber fallback
  └── SCANNED_PDF → MinerU V4（云端）
```

### Phase 3：MinerU V4 API 迁移

**重写文件**：`backend/app/services/mineru.py`

关键变更：
1. 使用 V4 端点：`POST https://mineru.net/api/v4/extract/task`
2. JWT 鉴权：从 `settings.mineru_api_token` 读取
3. 下载 ZIP 包（含 full.md + layout.json + images/）
4. 提取图片到物理存储卷
5. 返回 `UnifiedParserOutput`（含 `extracted_assets`）
6. 重试机制：指数退避，最多 3 次

**配置新增**（`config.py`）：
```python
mineru_api_token: str = ""           # MinerU V4 JWT Token
mineru_api_base: str = "https://mineru.net/api/v4"
mineru_poll_interval: int = 5        # 轮询间隔（秒）
mineru_max_poll_time: int = 300      # 最大轮询时间（秒）
```

### Phase 4：Docling 集成

**安装**：`uv add docling`

**重写文件**：`backend/app/services/parsing_docling.py`

关键变更：
1. 利用 Docling 的 `DoclingDocument` 结构树提取标题层级
2. TableFormer 表格提取：检测合并单元格 → 输出 HTML 格式
3. 图片提取：输出 BBox 坐标 + 保存到物理存储
4. 页面边界：从 Docling 的 `page_no` 属性生成 `<!-- PAGE_START N -->` 标记
5. 返回 `UnifiedParserOutput`

### Phase 5：归一化引擎

**新建文件**：`backend/app/services/normalizer.py`

```python
class NormalizationEngine:
    def normalize(self, raw_markdown: str, source_type: str) -> NormalizedOutput:
        """将任意解析器的输出归一化为 FoxSay 标准 Markdown。"""
        ...

class NormalizedOutput(BaseModel):
    markdown_content: str
    extracted_assets: list[ExtractedAssetMeta]
    page_count: int
    table_count: int
    image_count: int
    formula_count: int
```

归一化规则：
1. **页面锚定**：插入 `<!-- PAGE_START N -->` / `<!-- PAGE_END N -->` 标记
2. **表格保护**：检测合并单元格 → 保留 HTML `<table>` 格式；简单表格 → GFM 管线表格
3. **公式对齐**：行内 `$...$`，块级独行 `$$...$$`，禁止 `\[...\]` 或 `\(...\)`
4. **全局编号**：`[Image_1]`、`[Table_1]`、`[Formula_1]` 顺序递增
5. **标题统一**：所有标题映射为 `#` / `##` / `###` 标准格式

### Phase 6：语义切块（LangChain）

**安装**：`uv add langchain-text-splitters`

**重写文件**：`backend/app/services/chunking.py`

```python
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[dict]:
    """语义感知切块：
    1. 先按 Markdown 标题层级切分（保留层级上下文）
    2. 表格作为不可分割的整体
    3. 段落内按语义边界切分（不在句子/公式中间断）
    4. 每个 chunk 自动 prepend 父级标题路径
    """
    ...
```

关键行为：
- 标题层级切分：`MarkdownHeaderTextSplitter` 按 `#` / `##` / `###` 分割
- 表格保护：检测 `<table>` 到 `</table>` 或 GFM 表格边界，整个表格作为单独 chunk
- 上下文补齐：每个 chunk 的 metadata 包含 `heading_path`（如 "第三章 > 3.1 卷积计算模型"）
- chunk 大小：默认 800 字符，表格 chunk 允许超限
- 返回格式保持与现有 `vectorstore.py` 兼容（`{"text": ..., "index": ...}`）

### Phase 7：提取资产存储

**修改文件**：`backend/app/db/sqlite_store.py`

新增表：
```sql
CREATE TABLE IF NOT EXISTS extracted_assets (
    asset_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    element_type TEXT NOT NULL,       -- 'Image', 'Table', 'Formula'
    sequential_label TEXT NOT NULL,   -- '[Image_1]', '[Table_1]'
    page_number INTEGER NOT NULL,
    closest_heading TEXT DEFAULT '',
    storage_path TEXT DEFAULT '',
    alt_text TEXT DEFAULT '',
    x0 REAL, y0 REAL, x1 REAL, y1 REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_asset_material ON extracted_assets(material_id);
CREATE INDEX IF NOT EXISTS idx_asset_course ON extracted_assets(course_id);
```

**物理存储目录**：
```
backend/data/storage/images/
├── {course_id}/
│   └── {material_id}/
│       ├── page_1_img_1.png
│       ├── page_3_img_2.png
│       └── page_3_table_img_1.png
└── user_uploads/
    └── {uuid}.png
```

### Phase 8：检索评分修复

**修改文件**：`backend/app/services/retrieval.py`

问题：`search_wiki_layer()` 的 macro 层（章节）用字符级 Jaccard 评分（`_text_overlap_score`），而 micro 层（KC + chunk）用 cosine 相似度。两种分数尺度完全不同，混合排序后结果无意义。

修复方案：
1. **macro 层**：给 ChapterWiki 生成 embedding，用 cosine 相似度评分（与 micro 层统一）
2. **micro 层 KC 无 embedding 时**：也走 embedding 计算，而不是退化到 Jaccard
3. **删除 `_text_overlap_score` 函数**（或保留为调试用，不参与正式评分）
4. **权重调整**：三层结果合并时，可以按 layer 加权（chunk > KC > chapter）

### Phase 9：VLM 图片分支

**修改文件**：`backend/app/services/parsing.py`

图片输入（.png/.jpg/.jpeg）路由到 VLM 分支：

```python
def parse_image_vlm(file_path: str) -> UnifiedParserOutput:
    """调用 DeepSeek VL API 对图片做端到端 Markdown 提取。"""
    ...
```

行为：
1. 保存原图到 `backend/data/storage/images/user_uploads/{uuid}.png`
2. 调用 DeepSeek VL API，prompt 要求输出结构化 Markdown
3. 返回 `UnifiedParserOutput`（`raw_input_type: "USER_IMAGE"`）

### Phase 10：Pipeline 集成

**修改文件**：`backend/app/services/pipeline.py`

更新 `process_material()` 以适配新的管线流程：

1. 解析阶段输出 `UnifiedParserOutput`（而非纯文本字符串）
2. `extracted_assets` 写入 SQLite
3. 图片文件保存到物理存储
4. 归一化后的 Markdown 送入语义切块器
5. 切块结果增加 `heading_path` metadata（存入 Qdrant payload）

## 文件变更清单

| 文件 | 动作 | 说明 |
|------|------|------|
| `services/parser_interface.py` | 新建 | 解析器抽象基类 + 统一输出 schema |
| `services/normalizer.py` | 新建 | Markdown 归一化引擎 |
| `services/parsing.py` | 重写 | 路由器：PDF 探测 → 分发到各分支 |
| `services/parsing_docling.py` | 重写 | Docling 集成，实现 BaseDocumentParser |
| `services/mineru.py` | 重写 | V4 API 迁移，实现 BaseDocumentParser |
| `services/chunking.py` | 重写 | LangChain 语义感知切块 |
| `services/retrieval.py` | 修改 | 统一语义评分，删除 Jaccard |
| `services/pipeline.py` | 修改 | 适配 UnifiedParserOutput |
| `services/embedding.py` | 修改 | 增加重试和错误恢复 |
| `services/vectorstore.py` | 修改 | chunk payload 增加 heading_path |
| `db/sqlite_store.py` | 修改 | 新增 extracted_assets 表 |
| `core/config.py` | 修改 | 新增 MinerU V4 配置项 |
| `api/materials.py` | 修改 | 适配新的解析流程 |
| `pyproject.toml` | 修改 | 新增 docling、langchain-text-splitters |

## 新增依赖

```
docling                    # IBM 文档解析（电子版 PDF）
langchain-text-splitters   # 语义感知切块
requests                   # MinerU V4 HTTP 客户端（已在依赖中）
```

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| Docling 首次加载慢（模型下载） | 首次解析延迟 | 启动时预加载 converter 单例 |
| MinerU V4 网络抖动 | 扫描件解析失败 | 指数退避重试 3 次 + 降级到 pdfplumber |
| LangChain 引入体积大 | 启动变慢 | 只安装 `langchain-text-splitters`，不装全套 |
| 表格 HTML 在 chunk 中过长 | embedding 质量下降 | 表格单独 chunk + 上下文标题 prepend |
| VLM API 成本 | 图片解析费用 | 限制单课程图片数量（如最多 50 张） |

## 验证计划

1. **单元测试**：每个新模块（normalizer、chunker、pdf_detector）独立测试
2. **集成测试**：上传真实课件 PDF → 验证切块质量 → 验证检索准确性
3. **对比测试**：同一份 PDF，新旧管线的切块结果对比
4. **端到端测试**：上传材料 → 问课程问题 → 对比回答质量和引用准确性
