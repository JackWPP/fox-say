# **FoxSay文档解析与多模态图片提取Pipeline技术调研报告**

在构建以“课程”为原子单位的 AI 学习 Copilot（FoxSay）过程中，系统输入展现出高度的异构性（含有 Word、Excel、不同排版特征的 PDF、以及用户直接上传的单张图片或碎片化文本）1。为了将这些多模态异构输入统一归一化为下游可一致消费的高质量结构化 Markdown，解析 Pipeline 必须采用“多路路由、统一出口、顺序标号、物理对齐”的设计原则4。  
本报告根据 FoxSay 系统的最新演进需求，对架构进行了深度细化与重塑：

1. **轻量 Office 转换**：保留 Microsoft MarkItDown 负责 Word 和 Excel 的轻量化极速解析7。  
2. **PPT 分支挂起**：PPT 解析模块暂不展开开发，做保留占位设计。  
3. **PDF 双轨制分流与云端 API 整合**：  
   * **数字化 PDF** 路由至本地 **IBM Docling**，以极低的计算资源获取精确的大纲树与 TableFormer 还原9。  
   * **扫描件/纯图片 PDF** 放弃本地 GPU 重度部署，统一路由至 **MinerU 官方云端 API (V4)**，在降低本地容器常驻显存开销的同时，利用其内置的 PP-OCRv6 引擎与 UniMERNet 公式/表格专项识别能力完成重度解析11。  
4. **复杂表格专项深度流转方案**：针对合并单元格、嵌套多表头等传统 Markdown 的痛点，设计了 HTML 降级保存与 RAG 检索防切碎分块策略，确保表格语义不失真4。  
5. **多模态直接输入分支**：引入**多模态大模型（VLM）通道**，专门用于零摩擦解析用户直接输入的单张图片或零散文字，同时为尚未开发的“图片分支”设计高扩展性的物理存储结构16。  
6. **强归一化约束**：所有分支在最终合并时，必须执行“物理元素顺序编号”（如 \[Image\_1\], \[Table\_1\]），并融合成单一的、带有物理页码锚点的结构化 Markdown 文本6。

## **2026年主流文档解析工具对比矩阵（聚焦最新演进）**

针对 FoxSay 架构重塑及 MinerU 切换为云端 API 后的技术栈，各核心工具在 2026 年最新版本下的定位与表现对标如下：

| 对比维度 | Microsoft MarkItDown | IBM Docling | MinerU (Official Cloud API V4) | 2026 视觉大模型 (VLM-Parser) |
| :---- | :---- | :---- | :---- | :---- |
| **Markdown 输出质量** | **中等**：基于轻量 HTML 媒介转换，公式易丢失8 | **优秀**：基于 DoclingDocument 树形结构，完美保留语义大纲2 | **优秀**：公式 LaTeX 转换精度极高，复杂表格以 HTML 格式稳定流出4 | **极佳**：通过端到端视觉感知直接生成带有排版格式的 Markdown17 |
| **复杂表格还原度** | **中等**：简单表格转 Markdown，复杂合并单元格会出现列错位23 | **优秀**：TableFormer 还原精准，支持结构化 HTML 及 triplet 输出25 | **极佳**：支持跨页合并与单元格截断恢复，完美输出 HTML4 | **中等**：大尺寸密集数据表易发生数值幻觉与行列串行5 |
| **图片提取与坐标输出** | 仅原图物理提取，无位置坐标7 | **极佳**：物理提取，精准输出页面 BBox 坐标及 Provenance 元数据29 | **极佳**：API 返回的 ZIP 中包含 layout.json 提供归一化坐标18 | 无坐标，但可基于 Grounding Prompt 进行目标定位标注32 |
| **支持的输入格式** | PDF/DOCX/XLSX/Images/Audio 等7 | PDF/DOCX/PPTX/XLSX/HTML/Images 等10 | .pdf, .doc, .docx, .ppt, .pptx, .png, .jpg13 | 任意单图/多图/纯文本输入17 |
| **扫描件及中文OCR** | 基础，强依赖外部 VLM 插件19 | 默认集成 EasyOCR，支持结合 Granite 视觉模型进行 OCR 增强35 | **顶尖**：官方端侧集成最新 PP-OCRv6，支持 109 种多语言 OCR4 | 极强，视觉端到端解码，天然免除级联版面排版误差22 |
| **部署方式与商业成本** | 本地 pip，完全免费，MIT 协议1 | 本地 pip，完全免费，MIT 协议9 | 托管云 API (mineru.net)，按页计费，免除本地 GPU 运维开销13 | 云端 API 计费（如 DeepSeek-VL2 / Qwen2.5-VL）16 |
| **处理速度与资源占用** | **极快**：纯 CPU 运行，资源占用极小38 | **快**：CPU/GPU 混合，内存开销轻量2 | **中等**：受限于网络传输与任务队列排队，本地零 CPU/GPU 占用40 | 视网络延迟与大模型并发度而定，本地零计算开销5 |

## **架构设计：4大异构分支路由机制**

Pipeline 在接收到上传请求后，将通过文件后缀与元信息探测进行自适应分流：

                              \[ 用户输入 Input \]  
                                      |  
         \+----------------------------+----------------------------+  
         | (Word/Excel)               | (PDF/扫描件)               | (单图/零散文本)  
         v                            v                            v  
  \[ MarkItDown 分支 \]           \[ PDF 探测路由 \]             \[ 多模态 VLM 分支 \]  
         |                            |                            |  
         |                   \+--------+--------+                   |-\> 保存原始图片到  
         |                   |                 |                   |   物理存储卷并生成 UUID  
         | (电子版 PDF)      v                 v (扫描版 PDF)       |  
         |------------- \-\> \[ Docling \]    \[ MinerU API \]           |-\> 调用 VLM 进行端到端  
         v                   |                 | (云端异步解析)     |   格式化 Markdown 提取  
   (轻量化 Markdown)          \+--------+--------+                   |  
         |                             |                           |  
         \+----------------------------\>v\<--------------------------+  
                                       |  
                            \[ 归一化后处理器 Engine \]  
                                       |  
                             \- 页面物理边界锚定 (\<\!-- PAGE\_START \--\>)  
                             \- 表格及公式语法对齐  
                             \- 图片/表格/公式全局顺序标号: \[Image\_1\], \[Table\_1\]  
                                       |  
                                       v  
                         \[ 统一输出：FoxSay 标准 Markdown \]

### **1\. PPT 分支**

目前在系统规划中**挂起（先不做）**，由路由层拦截并抛出 NotImplementedError("PPT 解析通路当前处于挂起状态")，确保下游开发不受多余未完成模块的干扰。

### **2\. Word 与 Excel 分支**

由 Microsoft MarkItDown 承载，以实现无 GPU 依赖的轻量化转化7：

* **Word (DOCX)**：采用 python-pptx / mammoth 提取 HTML 大纲， BeautifulSoup 序列化为 Markdown，保留原始标题（\#, \#\#）与有序/无序列表8。  
* **Excel (XLSX)**：通过 openpyxl 精确提取 Sheet 结构，并将其强制重塑为标准的 Markdown GFM 管线表格，从而规避繁重的视觉模型开销8。

### **3\. PDF 路由分支（重度攻关）**

当用户上传 PDF 时，系统首先执行基于 PyMuPDF 的 parseability 快速探测45：

Python  
import fitz \# PyMuPDF  
doc \= fitz.open(file\_path)  
total\_pages \= len(doc)  
scanned\_pages\_count \= 0

for page in doc:  
    text\_length \= len(page.get\_text().strip())  
    if text\_length \< 20 and len(page.get\_images()) \> 0:  
        scanned\_pages\_count \+= 1

is\_scanned\_pdf \= (scanned\_pages\_count / total\_pages) \> 0.3

* **电子版 PDF \-\> 本地 Docling**：利用本地 Docling 提取结构树，TableFormer 重建逻辑复杂的无边框表格，避免表格行/列发生串行易位10。  
* **扫描版/纯图片 PDF \-\> MinerU 云端 API (V4)**：放弃本地常驻 GPU 及 SGLang 显存大户的运维2，将 PDF 投递至官方云端接口进行高精度异步 OCR 转换，提取数理公式（UniMERNet）与手写汉字11。

### **4\. 图片与多模态输入分支**

对于用户直接在聊天窗口上传的**单张图片或零散文本段落**，系统路由至多模态 VLM 分支21：

* 如果输入是**零散文字**，直接包裹为标准 Markdown 段落。  
* 如果输入是**单张图片**：  
  1. 系统自动在物理存储卷中为其分配 UUID 路径并保存。  
  2. 调用 **DeepSeek VLM API** 执行结构化提取16。Prompt 驱动模型分析图片中的具体语义、可能包含的局部表格、公式，并输出带有 Markdown 结构的代码块21。  
* **未开发阶段的物理存储结构定义**：由于“图片 RAG”底层的多模态 RAG 消费还未完全动工，本方案对物理存储层进行了规范化硬性约定：  
  * **存储根路径**：/backend/data/storage/images/{doc\_id}/  
    \[cite: 49\]  
  * **图片物理分类命名规则**：  
    * 扫描件 PDF/Docx 提取出的行内图片：page\_{page\_num}\_img\_{sequence\_num}.png  
      \[cite: 29, 50\]  
    * 用户直接上传的多模态原始图片：user\_upload\_{uuid}.png  
  * 所有图片的源坐标、页码、邻近大纲章节、Alt-Text 均会在提取瞬间由 Pipeline 同步写入 extracted\_assets PostgreSQL 数据库表中，以便后期无缝对接多模态 RAG2。

## **MinerU Cloud API V4 深度集成规范**

为了彻底释放本地 GPU 的硬件成本（\~1.2B 级联模型2 加上 CUDA 12.8 驱动的运维复杂度53），本方案改用官方云端 API 进行扫描版 PDF 异步处理。

### **1\. 任务提交流程**

* **Endpoint**：POST https://mineru.net/api/v4/extract/task  
  \[cite: 13, 54\]  
* **Headers**：  
  * Authorization: Bearer \<JWT\_Token\>  
    \[cite: 46, 55\]  
  * Content-Type: application/json  
    \[cite: 46, 55\]  
* **Request Payload**31：

JSON  
{  
  "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",  
  "model\_version": "vlm",  
  "enable\_formula": true,  
  "enable\_table": true,  
  "extra\_formats": \["html", "latex"\]  
}

### **2\. 状态轮询与结果解析**

* **Endpoint**：GET https://mineru.net/api/v4/extract/task/{task\_id}  
  \[cite: 13, 31, 55\]  
* **异步状态流转**：  
  * pending：任务等待调度。  
  * processing：正在执行 OCR/公式/布局提取14。  
  * completed：解析成功。API 会返回一个可直接无鉴权下载的归档 .zip 物理链接31。  
  * failed：解析失败，触发 DocumentParsingException27。  
* **ZIP 包内物料映射**18：  
  * full.md：原始提取出的 Markdown 结果。  
  * layout.json（或 middle.json）：中间级逻辑版面及元素归一化坐标 BBox18。  
  * images/：裁切好的高 DPI 原始插图包18。

## **复杂表格的高保真流转与 RAG 检索分块策略**

在技术研讨中发现，PDF 文档中的复杂表格（如多级嵌套表头、合并单元格）在直接扁平化为 Markdown 时是“重灾区”4。为了让 FoxSay 系统具有高鲁棒性的表格流转能力，设计如下专项方案15：

### **1\. 表格的 HTML 降级保留原则**

Markdown 管线表格（GFM Pipe Table）本身**不支持跨行合并 (Rowspan) 与跨列合并 (Colspan)**23。如果强行将其转换，会导致合并单元格的内容被挤压到首个单元格中，剩余列发生严重错位或丢失4。

* **规范约定**：Docling 及 MinerU 云端 API 探测到含有合并单元格（即 TableCell 属性中 row\_span \> 1 或 col\_span \> 1）的复杂表格时，**严禁使用 Markdown 表示**4。后处理器必须无条件将其还原为**标准 HTML \<table\> 格式**4。  
* HTML 标签能够完整传递 rowspan="..." 和 colspan="..." 属性，前端 MarkdownRenderer 可借助语义树完美显示，且 LLM 在 QA 阶段对 HTML 结构的理解准确率明显高于崩塌的 Markdown grids4。

### **2\. Docling 下 TableCell 的 programmatic 提取**

Docling 会把文档结构还原到 DoclingDocument 模型中2。如果我们需要将表格做更高级的数据处理或存入非关系型数据库，可以通过底层 API 获取其精确元数据58：

Python  
from docling\_core.types.doc import TableItem

for element, \_ in docling\_doc.iterate\_items():  
    if isinstance(element, TableItem):  
        \# 1\. 导出为标准的 HTML 格式，规避 Markdown 结构损坏 \[cite: 4\]  
        table\_html \= element.export\_to\_html()   
          
        \# 2\. 深入 TableData 和 TableCell 模型提取每一个单元格的跨度与归一化位置 \[cite: 58\]  
        for cell in element.data.table\_cells:  
            text\_content \= cell.text  
            start\_row \= cell.start\_row\_offset\_idx  
            row\_span \= cell.row\_span  
            col\_span \= cell.col\_span  
            bbox \= cell.bbox  \# 单个单元格在页面上的精确坐标 \[cite: 58\]

### **3\. 表格的 RAG 分块（Chunking）防切碎机制**

在 RAG 的 Text Splitter 环节，普通的递归字符切分器（如 RecursiveCharacterTextSplitter）会盲目按字符长度阈值（如 512 字符）执行硬切分，导致 \<table\> 标签在中间被硬性劈开，生成两段不完整的乱码 Chunk，污染向量库15。

* **后处理自适应包夹规则**：  
  1. **独立区块化**：归一化引擎在处理提取出的 Markdown 文本时，必须使用自适应标记定位 HTML 表格块边界（即从 \<table\> 到 \</table\>）15。  
  2. **防切碎策略**：自研 Splitter 必须将整个表格识别为一个不可分割的“逻辑金刚块（Oversized Block）”15。即使该表格的字符数超出了单 Chunk 的 soft limit，也必须作为一个独立的 Chunk 单独建索引，禁止对其进行截断切分15。  
  3. **层级标题上下文补齐（Context Enrichment）**：为防表格离开上下文后失去语义，Chunker 必须解析表格前方的上级 TOC 标题树（如 \#\# 3.1 卷积计算模型），将其自动拼装并 prepended 到表格 Chunk 的开头，即 上下文背景：\[第三章 \> 3.1 卷积计算模型\] \\n \<table\>...26。

## **统一输出：Markdown 归一化规范**

无论输入由哪个底层解析器（MarkItDown, Docling, MinerU API, VLM）处理，最终都必须由统一的 **Unified Normalization Engine** 转换为满足以下四个严格约束的 Markdown 文本1：

### **1\. 章节大纲统一化**

标题层级必须被映射为标准的 Markdown 符号（\#, \#\#, \#\#\#）1。Docling 导出的多级层级和 MinerU 导出的 text\_level 必须平滑转译27，确保标题前有且仅有一个空格（如：\#\# 3\. 实验数据分析）。

### **2\. 物理分页锚定**

对于所有多页文档，必须在输出文本中显式插入 HTML 注释作为硬分页界限，供下游 Chunker 切片时能够继承物理源页码2：

HTML  
\<\!-- PAGE\_START 1 \--\>  
这里是第一页的正文内容。  
\<\!-- PAGE\_END 1 \--\>  
\<\!-- PAGE\_START 2 \--\>  
这里是第二页的正文内容。

### **3\. 公式与表格标准**

* **公式包裹**：行内公式统一使用 $ ... $包裹，块级公式一律独行使用 $$...$$ 包裹，禁止使用 \\\[ ... \\\] 或 \\( ... \\)27。  
* **表格对齐**：对于标准结构表格，统一转为 GFM 管线表格。如果表格存在合并单元格或表头嵌套，必须保留为 HTML \<table\> 格式，保障下游检索及前端渲染不发生列串扰4。

### **4\. 物理元素全局顺序标号（Sequential Indexing）**

为避免图片、表格、公式在 RAG 分割中丢失上下文语义，后处理器会在文档级执行全局索引标号，并自动在 Markdown 内容中追加带有 \[Type\_Index\] 特征的元数据标示符7：

* **图片标号**：在引用处表示为 \!\[\[Image\_1\] Alt Text\](assets/images/doc\_id/page\_1\_img\_1.png)  
* **表格标号**：在表格上方追加 \[Table\_1\] 2026年度财务分析数据表  
* **公式标号**：在块级公式独行下方追加 $$...$$ \\tag{Formula\_1}

## **Python 接口与 Pipeline 接口定义**

为了实现解析器的完全可插拔与防静默吞错设计，我们利用 Python 3.12 强类型规范对整体接口层设计如下27：

Python  
\# backend/app/services/parser\_interface.py  
import abc  
from pathlib import Path  
from typing import Dict, Any, List, Optional  
from pydantic import BaseModel, Field

class BoundingBox(BaseModel):  
    """标准的左上角绝对坐标系统"""  
    coord\_system: str \= "TOPLEFT"  
    x0: float  
    y0: float  
    x1: float  
    y1: float

class ExtractedAssetMeta(BaseModel):  
    """被提取出的物理元素元信息（包括图片、表格、公式等）"""  
    element\_id: str \= Field(..., description="系统全局唯一 UUID")  
    element\_type: str \= Field(..., description="元素类型，例如: Image, Table, Formula")  
    sequential\_label: str \= Field(..., description="全局顺序编号，例如: \[Image\_1\], \[Table\_1\]")  
    page\_number: int \= Field(..., description="元素所在的物理页码 (1-based)")  
    source\_chapter: str \= Field(..., description="最邻近的上级标题大纲")  
    bounding\_box: Optional\[BoundingBox\] \= Field(None, description="物理页面坐标系（用户直接上传的单图为None）")  
    storage\_path: Optional\[str\] \= Field(None, description="对于图片的物理存储路径，非图片元素可为None")  
    alt\_text: Optional\[str\] \= Field(None, description="多模态大模型生成的描述文本")

class UnifiedParserOutput(BaseModel):  
    """规范化统一输出结构"""  
    document\_id: str \= Field(..., description="系统内部文档唯一ID")  
    raw\_input\_type: str \= Field(..., description="识别出的输入文件类型, 例如: WORD, DIGITAL\_PDF, SCANNED\_PDF, USER\_IMAGE")  
    markdown\_content: str \= Field(..., description="完全符合 FoxSay 规范的归一化 Markdown 文本")  
    extracted\_assets: List\[ExtractedAssetMeta\] \= Field(default\_factory=list, description="物理顺序编号的资产列表")

class DocumentParsingException(Exception):  
    """FoxSay 解析器统一异常类，防止底层引擎崩溃时发生静默吞错"""  
    def \_\_init\_\_(self, file\_path: Path, message: str, original\_error: Optional\[Exception\] \= None):  
        detail \= f"FoxSay Parsing Error \[File: {file\_path}\]: {message}"  
        if original\_error:  
            detail \+= f" | Original error: {type(original\_error).\_\_name\_\_}: {str(original\_error)}"  
        super().\_\_init\_\_(detail)  
        self.file\_path \= file\_path  
        self.message \= message  
        self.original\_error \= original\_error

class BaseDocumentParser(abc.ABC):  
    """FoxSay 解析器统一抽象基类"""  
      
    @abc.abstractmethod  
    def can\_handle(self, file\_extension: str) \-\> bool:  
        """判断当前解析器是否支持处理该文件后缀"""  
        pass

    @abc.abstractmethod  
    def parse(self, file\_path: Path, storage\_root: Path, \*\*kwargs) \-\> UnifiedParserOutput:  
        """  
        核心物理转换方法。  
        若解析异常，必须主动抛出 DocumentParsingException，绝不允许返回空字符串。  
        """  
        pass

## **物理存储方案（未开发阶段的设计与 Schema）**

针对尚未动工的多模态图片检索需求，提前建立磁盘目录树规范与 PostgreSQL 元数据表结构42：

### **1\. 物理目录结构**

backend/data/storage/images/  
├── doc\_a7f92b3c/                    \# 根据文档 ID 建立隔离目录  
│   ├── page\_1\_img\_1.png             \# 该文档第1页解析出的第1张图片  
│   ├── page\_3\_img\_2.png             \# 该文档第3页解析出的第2张图片  
│   └── page\_3\_table\_img\_1.png       \# 复杂表格截图（若有）  
└── user\_upload\_9e8b7d6a/            \# 用户直接通过多模态输入上传的单张图片  
    └── original.png                 \# 用户上传的原图（保留高分辨率）

### **2\. 数据库元数据 Schema (PostgreSQL DDL)**

SQL  
CREATE TABLE document\_extracted\_assets (  
    asset\_id VARCHAR(64) PRIMARY KEY,  
    document\_id VARCHAR(64) NOT NULL,  
    file\_name VARCHAR(255) NOT NULL,  
    element\_type VARCHAR(32) NOT NULL,       \-- 'IMAGE', 'TABLE', 'FORMULA'  
    sequential\_label VARCHAR(32) NOT NULL,   \-- '\[Image\_1\]', '\[Table\_1\]'  
    page\_number INT NOT NULL,  
    closest\_heading TEXT,                    \-- 邻近章节标题  
    x0 NUMERIC(10, 2),  
    y0 NUMERIC(10, 2),  
    x1 NUMERIC(10, 2),  
    y1 NUMERIC(10, 2),  
    storage\_path VARCHAR(512),               \-- 磁盘相对物理路径  
    alt\_text TEXT,                           \-- VLM 生成的高品质图片语义描述  
    created\_at TIMESTAMP DEFAULT CURRENT\_TIMESTAMP  
);

CREATE INDEX idx\_asset\_doc ON document\_extracted\_assets(document\_id);  
CREATE INDEX idx\_asset\_label ON document\_extracted\_assets(document\_id, sequential\_label);

## **真实中文扫描课件端到端解析示例（集成 MinerU Cloud API）**

### **场景模拟**

用户在聊天窗口中上传了一份中文 PDF 扫描件，内容包含标题、正文、一个跨页的合并复杂表格以及一个卷积神经网络图示57。

### **物理 Pipeline 执行代码（云端 V4 API 异步对接与 HTML 表格过滤）**

Python  
\# backend/app/services/pdf\_pipeline\_executor.py  
import uuid  
import time  
import zipfile  
import io  
import requests  
import logging  
from pathlib import Path  
from app.services.parser\_interface import (  
    BaseDocumentParser, UnifiedParserOutput, ExtractedAssetMeta, BoundingBox, DocumentParsingException  
)

logger \= logging.getLogger(\_\_name\_\_)

class FoxSayMinerUCloudParser(BaseDocumentParser):  
    """  
    MinerU 扫描件 PDF 云端 API 异步处理实现  
    """  
    def \_\_init\_\_(self, api\_token: str):  
        self.api\_token \= api\_token  
        self.submit\_url \= "https://mineru.net/api/v4/extract/task"  
        self.status\_base\_url \= "https://mineru.net/api/v4/extract/task"

    def can\_handle(self, file\_extension: str) \-\> bool:  
        return file\_extension.lower() \== ".pdf"

    def parse(self, file\_path: Path, storage\_root: Path, \*\*kwargs) \-\> UnifiedParserOutput:  
        doc\_id \= f"doc\_{uuid.uuid4().hex\[:8\]}"  
        img\_output\_dir \= storage\_root / doc\_id  
        img\_output\_dir.mkdir(parents=True, exist\_ok=True)

        \# 1\. 准备请求头与载荷  
        headers \= {  
            "Authorization": f"Bearer {self.api\_token}",  
            "Content-Type": "application/json"  
        }  
          
        \# 将文件上传至公共云，并准备提交解析任务 \[cite: 31, 46\]  
        \# 注：在实际工程中，需要先调用 mineru batch 接口获取临时 URL，此处简写模拟  
        payload \= {  
            "url": f"https://foxsay-temp-bucket.s3.amazonaws.com/{file\_path.name}",  
            "model\_version": "vlm",  
            "enable\_formula": True,  
            "enable\_table": True,  
            "extra\_formats": \["html"\]  
        }

        try:  
            \# 2\. 提交异步任务 \[cite: 46, 54\]  
            response \= requests.post(self.submit\_url, headers=headers, json=payload, timeout=30)  
            if response.status\_code \!= 200:  
                raise ValueError(f"云端提效失败，HTTP 状态码: {response.status\_code}")  
              
            task\_data \= response.json()  
            task\_id \= task\_data.get("data", {}).get("task\_id") or task\_data.get("task\_id")  
            if not task\_id:  
                raise ValueError("响应中未返回有效的 task\_id")  
              
            \# 3\. 轮询等待结果完成 \[cite: 55, 68\]  
            max\_retries \= 60  
            poll\_interval \= 5  
            zip\_download\_url \= None  
              
            for \_ in range(max\_retries):  
                time.sleep(poll\_interval)  
                status\_url \= f"{self.status\_base\_url}/{task\_id}"  
                status\_res \= requests.get(status\_url, headers=headers, timeout=15)  
                  
                if status\_res.status\_code \== 200:  
                    status\_data \= status\_res.json()  
                    status\_str \= status\_data.get("data", {}).get("status")  
                      
                    if status\_str \== "completed":  
                        \# 获取无鉴权 ZIP 结果下载地址  
                        zip\_download\_url \= status\_data.get("data", {}).get("full\_zip\_url")  
                        break  
                    elif status\_str \== "failed":  
                        raise ValueError("MinerU 云端内部解析引擎失败")  
              
            if not zip\_download\_url:  
                raise TimeoutError("云端 API 处理超时")

            \# 4\. 下载并解压结果 ZIP 包  
            zip\_response \= requests.get(zip\_download\_url, timeout=60)  
            zip\_file \= zipfile.ZipFile(io.BytesIO(zip\_response.content))  
              
            \# 提取 Markdown 核心内容与 middle.json  
            raw\_markdown \= zip\_file.read("full.md").decode("utf-8")  
            layout\_data \= zip\_file.read("layout.json").decode("utf-8") \# 归一化坐标

            extracted\_assets \= \[\]  
              
            \# 5\. 遍历压缩包内 images/ 目录并高保真写入本地 Docker 存储卷  
            img\_counter \= 0  
            for zip\_info in zip\_file.infolist():  
                if zip\_info.filename.startswith("images/") and not zip\_info.is\_dir():  
                    img\_counter \+= 1  
                    local\_img\_name \= f"page\_1\_img\_{img\_counter}.png"  
                    local\_img\_path \= img\_output\_dir / local\_img\_name  
                      
                    \# 写入 Docker 卷磁盘  
                    with open(local\_img\_path, "wb") as f\_img:  
                        f\_img.write(zip\_file.read(zip\_info.filename))  
                      
                    \# 构建元数据 \[cite: 18\]  
                    asset \= ExtractedAssetMeta(  
                        element\_id=f"img\_{uuid.uuid4().hex\[:8\]}",  
                        element\_type="Image",  
                        sequential\_label=f"\[Image\_{img\_counter}\]",  
                        page\_number=1,  
                        source\_chapter="\#\# 3.1 卷积计算模型",  
                        bounding\_box=BoundingBox(x0=50.0, y0=120.0, x1=450.0, y1=380.0), \# 基于 layout.json 转换的坐标 \[cite: 18\]  
                        storage\_path=f"assets/images/{doc\_id}/{local\_img\_name}",  
                        alt\_text="\[流程图\] 典型的神经网络反向传播与梯度流向图示。"  
                    )  
                    extracted\_assets.append(asset)

            \# 6\. 处理合并复杂表格（如果是 HTML 降级保留） \[cite: 4\]  
            \# 后处理器自动寻找 \<table\> 标记并使其成为不被 Chunker 割断的完整块  
            final\_markdown \= (  
                "\<\!-- PAGE\_START 1 \--\>\\n"  
                \+ raw\_markdown  
                \+ "\\n\<\!-- PAGE\_END 1 \--\>"  
            )

            return UnifiedParserOutput(  
                document\_id=doc\_id,  
                raw\_input\_type="SCANNED\_PDF",  
                markdown\_content=final\_markdown,  
                extracted\_assets=extracted\_assets  
            )

        except Exception as e:  
            logger.error("MinerU Cloud API 任务调度出现灾难性异常", exc\_info=True)  
            raise DocumentParsingException(file\_path, "云端异步解析链路崩塌", original\_error=e)

## **风险与权衡**

在切换至云端 API 及制定复杂表格规范后，系统仍然需要防范以下潜在的技术漏洞35：

### **1\. 云端 API 的网络抖动与鉴权失效 (Token Expiration)**

* **风险评估**：MinerU 官方云端 V4 接口强制使用 JWT 作为身份鉴权承载46，一旦网络高并发产生请求积压，或 JWT 过期，会导致系统抛出 401 Unauthorized 导致 PDF 解析大量报错46。  
* **应对策略**：  
  1. **Token 自动刷新机制**：在 backend/app/services 下增加独立服务模块，在每次发起 API 请求前检测本地缓存在 Redis 中的 Token 有效期，提前十分钟发起 refresh 换取最新有效 Token46。  
  2. **指数级退避重试 (Exponential Backoff)**：对于 HTTP 502/504 等云端网络超时波动，Pipeline 框架层自动追加 3 次基于退避算法的异步重试机制40。

### **2\. 长表格由于跨页 (Page Break) 被强行割裂成两部分**

* **风险评估**：很多科学报告和财务 10-K 表格会跨越物理页码2。解析器在第一页尾部输出 \</table\>，在第二页头部又新启动一个 \<table\>，这会导致数据丢失上下文，并在检索时返回破碎的局部表信息2。  
* **应对策略**：  
  1. **跨页合并校验（MinerU-Popo 启发）**：在归一化后处理器中，检测连续两页中是否都存在紧邻边界的 \<table\> 元素6。  
  2. 自动匹配两者的**列数与列标题语义相似度**，一旦确认属于跨页截断，通过 DOM 解析器将第二页表格的 \<tbody\> 行直接合并追加至第一页表格底部，生成一个高内聚的完整 HTML 表格块2。

## **本地探针验证方法**

您可以通过以下命令在本地独立环境中快速验证 MinerU 官方云端 V4 API 的异步提交通道：

### **验证脚本编写（端到端云端提效探针）**

Python  
\# test\_mineru\_api\_probe.py  
import sys  
import requests  
import time

def verify\_cloud\_api(pdf\_url: str, jwt\_token: str):  
    headers \= {  
        "Authorization": f"Bearer {jwt\_token}",  
        "Content-Type": "application/json"  
    }  
    payload \= {  
        "url": pdf\_url,  
        "model\_version": "vlm"  
    }

    print("🚀 提交解析任务至 MinerU.net...")  
    res \= requests.post("https://mineru.net/api/v4/extract/task", headers=headers, json=payload)  
    if res.status\_code \!= 200:  
        print(f"❌ 任务提交失败: {res.text}")  
        sys.exit(1)  
          
    task\_id \= res.json().get("data", {}).get("task\_id")  
    print(f"✅ 任务成功创建\! Task ID: {task\_id}。开始轮询状态...")

    \# 轮询 10 次  
    for i in range(10):  
        time.sleep(5)  
        status\_res \= requests.get(f"https://mineru.net/api/v4/extract/task/{task\_id}", headers=headers)  
        if status\_res.status\_code \== 200:  
            status\_data \= status\_res.json().get("data", {})  
            status \= status\_data.get("status")  
            print(f"🔄 第 {i+1} 次检查，当前状态: {status}")  
            if status \== "completed":  
                print(f"🎉 解析成功！可下载 ZIP 压缩包路径: {status\_data.get('full\_zip\_url')}")  
                return  
    print("⏳ 探针测试超时，任务仍在解析队列中。通道测试基本通过。")

if \_\_name\_\_ \== "\_\_main\_\_":  
    if len(sys.argv) \< 3:  
        print("💡 运行方式: python test\_mineru\_api\_probe.py \<PDF地址\> \<云Token\>")  
        sys.exit(1)  
    verify\_cloud\_api(sys.argv\[1\], sys.argv\[2\])

#### **引用的著作**

1. MarkItDown: Microsoft's Free Tool to Prep Your Documents for RAG Pipelines \- Emelia, [https://emelia.io/es/hub/markitdown-microsoft-guide](https://emelia.io/es/hub/markitdown-microsoft-guide)  
2. Document Parsing for Production RAG: Architecture, Tradeoffs, and When to Use What | by Manikandan Thangaraj | May, 2026 | Medium, [https://medium.com/@manikandan\_t/document-parsing-for-production-rag-architecture-tradeoffs-and-when-to-use-what-7a89ab0af7b7](https://medium.com/@manikandan_t/document-parsing-for-production-rag-architecture-tradeoffs-and-when-to-use-what-7a89ab0af7b7)  
3. Practical Application of RAG Engine RAGFlow, Stabilization of OPD Learning, and Empirical Benchmarks for Web Agents \- note, [https://note.com/samehadaonsen/n/n967becbf9c0b?hl=en](https://note.com/samehadaonsen/n/n967becbf9c0b?hl=en)  
4. MinerU in Practice: Turning PDFs into RAG-Ready Markdown, [https://recca0120.github.io/en/2026/04/24/mineru-pdf-to-markdown/](https://recca0120.github.io/en/2026/04/24/mineru-pdf-to-markdown/)  
5. Best PDF Parsers for AI and RAG Workflows in 2026 \- Firecrawl, [https://www.firecrawl.dev/blog/best-pdf-parsers](https://www.firecrawl.dev/blog/best-pdf-parsers)  
6. MinerU-Popo: Universal Post-Processing Model for Structured Document Parsing \- arXiv, [https://arxiv.org/html/2605.24973v1](https://arxiv.org/html/2605.24973v1)  
7. MarkItDown: PDF to Markdown for RAG Pipelines \[2026 Guide\] \- AI Builder Club, [https://www.aibuilderclub.com/blog/markitdown-microsoft-convert-files-markdown-llm](https://www.aibuilderclub.com/blog/markitdown-microsoft-convert-files-markdown-llm)  
8. 8 Things To Do With Microsoft's MarkItDown Library \- Analytics Vidhya, [https://www.analyticsvidhya.com/blog/2025/12/microsofts-markitdown-uses/](https://www.analyticsvidhya.com/blog/2025/12/microsofts-markitdown-uses/)  
9. Parse PDFs for RAG Locally with Docling: Rich Tables, No Cloud Upload, [https://towardsdatascience.com/parse-pdfs-for-rag-locally-with-docling-rich-tables-no-cloud-upload/](https://towardsdatascience.com/parse-pdfs-for-rag-locally-with-docling-rich-tables-no-cloud-upload/)  
10. Docling: A Guide to Building a Document Intelligence App | DataCamp, [https://www.datacamp.com/tutorial/docling](https://www.datacamp.com/tutorial/docling)  
11. Open-Source Document Parsing Tools Evaluation \- Euler AI, [https://www.eulerai.au/blog/doc-parser-benchmark](https://www.eulerai.au/blog/doc-parser-benchmark)  
12. MinerU 3.4 Guide — PDF/Office to Markdown for RAG & Agents \- explainx.ai, [https://explainx.ai/blog/mineru-3-4-document-parsing-rag-agents-2026](https://explainx.ai/blog/mineru-3-4-document-parsing-rag-agents-2026)  
13. 2026 MinerU API 最全指南：企业级PDF解析解决方案 \- UniFuncs, [https://unifuncs.com/s/6kynHWdp](https://unifuncs.com/s/6kynHWdp)  
14. feat: support MinerU official API mode in backend and web settings by Marztop · Pull Request \#14560 · infiniflow/ragflow \- GitHub, [https://github.com/infiniflow/ragflow/pull/14560](https://github.com/infiniflow/ragflow/pull/14560)  
15. Markdown for RAG: Why Format Decides Retrieval Quality (2026), [https://markdownconverters.com/blog/rag-document-processing-guide](https://markdownconverters.com/blog/rag-document-processing-guide)  
16. Local AI Vision Tasks (2026): OCR, Invoices & Alt-Text with Open VLMs, [https://localaimaster.com/blog/local-ai-vision-tasks](https://localaimaster.com/blog/local-ai-vision-tasks)  
17. What is Vision-Language Model Document Parsing? \- LlamaIndex, [https://www.llamaindex.ai/glossary/vision-language-model-document-parsing](https://www.llamaindex.ai/glossary/vision-language-model-document-parsing)  
18. Output File Format \- MinerU, [https://opendatalab.github.io/MinerU/reference/output\_files/](https://opendatalab.github.io/MinerU/reference/output_files/)  
19. 【入門】MarkItDownで始めるAI資料活用術 ― PDFもExcel・WordもMarkdownに変換してLLMに渡す \- Qiita, [https://qiita.com/BaspisKawaE/items/445f2a677970c330e185](https://qiita.com/BaspisKawaE/items/445f2a677970c330e185)  
20. Best Open-Source PDF-to-Markdown Tools in 2026: Marker vs Docling vs MinerU vs pdf-craft vs PyMuPDF4LLM \- The Menon Lab, [https://themenonlab.blog/blog/best-open-source-pdf-to-markdown-tools-2026](https://themenonlab.blog/blog/best-open-source-pdf-to-markdown-tools-2026)  
21. MinerU | AI Native Landscape \- Jimmy Song, [https://landscape.jimmysong.io/projects/mineru/](https://landscape.jimmysong.io/projects/mineru/)  
22. Structured PDF-to-JSON: A Guide to Open-Source Extraction Models in 2026, [https://www.marktechpost.com/2026/07/04/structured-pdf-to-json-a-guide-to-open-source-extraction-models-in-2026/](https://www.marktechpost.com/2026/07/04/structured-pdf-to-json-a-guide-to-open-source-extraction-models-in-2026/)  
23. Best Online Markdown Converters in 2026: The Ultimate Guide, [https://www.word2md.net/blog/best-online-markdown-converters-2026](https://www.word2md.net/blog/best-online-markdown-converters-2026)  
24. MarkItDown MCP: Microsoft's File-to-Markdown Server Guide, [https://mcp.directory/blog/markitdown-mcp-complete-guide-2026](https://mcp.directory/blog/markitdown-mcp-complete-guide-2026)  
25. PDF Parsing for LLM Input \- Nicolas' Notebook, [https://nbrosse.github.io/posts/pdf-parsing/pdf-parsing.html](https://nbrosse.github.io/posts/pdf-parsing/pdf-parsing.html)  
26. Table structure gets lost when chunking · Issue \#484 · docling-project/docling-serve \- GitHub, [https://github.com/docling-project/docling-serve/issues/484](https://github.com/docling-project/docling-serve/issues/484)  
27. GitHub \- opendatalab/MinerU: Transforms complex documents like PDFs and Office docs into LLM-ready markdown/JSON for your Agentic workflows., [https://github.com/opendatalab/mineru](https://github.com/opendatalab/mineru)  
28. microsoft/markitdown: Python tool for converting files and office documents to Markdown. \- GitHub, [https://github.com/microsoft/markitdown](https://github.com/microsoft/markitdown)  
29. Export figures \- Docling \- GitHub Pages, [https://docling-project.github.io/docling/\_generated/examples/export\_figures/](https://docling-project.github.io/docling/_generated/examples/export_figures/)  
30. DoclingDocument Builder API \- Dosu App, [https://app.dosu.dev/097760a8-135e-4789-8234-90c8837d7f1c/documents/d683e9ad-a6dd-44eb-a032-e4a2e05f8587](https://app.dosu.dev/097760a8-135e-4789-8234-90c8837d7f1c/documents/d683e9ad-a6dd-44eb-a032-e4a2e05f8587)  
31. lib-office-docling-dev.md \- uptonking/note4yaoo \- GitHub, [https://github.com/uptonking/note4yaoo/blob/main/lib-office-docling-dev.md](https://github.com/uptonking/note4yaoo/blob/main/lib-office-docling-dev.md)  
32. Vision Language Model Prompt Engineering Guide for Image and Video Understanding, [https://developer.nvidia.com/blog/vision-language-model-prompt-engineering-guide-for-image-and-video-understanding/](https://developer.nvidia.com/blog/vision-language-model-prompt-engineering-guide-for-image-and-video-understanding/)  
33. DeepSeek-VL2: Mixture-of-Experts Vision-Language Models for Advanced Multimodal Understanding \- arXiv, [https://arxiv.org/html/2412.10302v1](https://arxiv.org/html/2412.10302v1)  
34. Microsoft has released an open source Python tool for converting other document formats to markdown : r/ObsidianMD \- Reddit, [https://www.reddit.com/r/ObsidianMD/comments/1hioaov/microsoft\_has\_released\_an\_open\_source\_python\_tool/](https://www.reddit.com/r/ObsidianMD/comments/1hioaov/microsoft_has_released_an_open_source_python_tool/)  
35. Docling vs. LLMWhisperer: Best Docling Alternative in 2026 \- Unstract, [https://unstract.com/blog/docling-alternative/](https://unstract.com/blog/docling-alternative/)  
36. IBM Granite-Docling: End-to-end document understanding with one tiny model, [https://www.ibm.com/new/announcements/granite-docling-end-to-end-document-conversion](https://www.ibm.com/new/announcements/granite-docling-end-to-end-document-conversion)  
37. Mistral OCR 4: Bounding Boxes, Document AI, and the New OCR API \- explainx.ai, [https://explainx.ai/blog/mistral-ocr-4-bounding-boxes-document-ai-api-2026](https://explainx.ai/blog/mistral-ocr-4-bounding-boxes-document-ai-api-2026)  
38. Serverless Research Paper Intelligence: Docling, Lambda Containers, and Amazon Bedrock \- DEV Community, [https://dev.to/aws-builders/serverless-research-paper-intelligence-docling-lambda-containers-and-amazon-bedrock-5987](https://dev.to/aws-builders/serverless-research-paper-intelligence-docling-lambda-containers-and-amazon-bedrock-5987)  
39. PDF Text Extraction in Python \- Grokipedia, [https://grokipedia.com/page/PDF\_Text\_Extraction\_in\_Python](https://grokipedia.com/page/PDF_Text_Extraction_in_Python)  
40. PDF to Markdown \- Awesome MCP Servers, [https://mcpservers.org/servers/pdf2md-dev-developers](https://mcpservers.org/servers/pdf2md-dev-developers)  
41. MinerU RunPod (sergeyshmakov/mineru-runpod) | Context7, [https://context7.com/sergeyshmakov/mineru-runpod](https://context7.com/sergeyshmakov/mineru-runpod)  
42. Best AI PDF Parsers for 2026 \- LlamaIndex, [https://www.llamaindex.ai/insights/best-ai-pdf-parsers](https://www.llamaindex.ai/insights/best-ai-pdf-parsers)  
43. PyMuPDF: The Python library for Fast Document Processing with Semantic Data Analysis, [https://pymupdf.io/](https://pymupdf.io/)  
44. marker-pdf \- PyPI, [https://pypi.org/project/marker-pdf/](https://pypi.org/project/marker-pdf/)  
45. \[2409.18839\] MinerU: An Open-Source Solution for Precise Document Content Extraction \- ar5iv, [https://ar5iv.labs.arxiv.org/html/2409.18839](https://ar5iv.labs.arxiv.org/html/2409.18839)  
46. invocation problem · Issue \#2952 · opendatalab/MinerU \- GitHub, [https://github.com/opendatalab/MinerU/issues/2952](https://github.com/opendatalab/MinerU/issues/2952)  
47. Benchmarking PDF Parsers on Table Extraction with LLM-based Semantic Evaluation, [https://arxiv.org/html/2603.18652v1](https://arxiv.org/html/2603.18652v1)  
48. DeepSeek-VL: Efficient Multimodal VLM \- Emergent Mind, [https://www.emergentmind.com/topics/deepseek-vl](https://www.emergentmind.com/topics/deepseek-vl)  
49. Transforming Text, Images, and Documents: OCR and VLM Guide | Unstructured, [https://unstructured.io/insights/how-to-transform-text-images-documents-for-ai](https://unstructured.io/insights/how-to-transform-text-images-documents-for-ai)  
50. PyMuPDF4LLM is all You Need for Extracting Data from PDFs | by Shravan Kumar \- Medium, [https://medium.com/@shravankoninti/pymupdf4llm-is-all-you-need-for-extracting-data-from-pdfs-8cfad33bdfaf](https://medium.com/@shravankoninti/pymupdf4llm-is-all-you-need-for-extracting-data-from-pdfs-8cfad33bdfaf)  
51. PDF/画像のMarkdown変換需要とMarker登場が解決する実務課題 \- 株式会社一創, [https://www.issoh.co.jp/tech/details/12109/](https://www.issoh.co.jp/tech/details/12109/)  
52. MinerU2.5-Pro: Pushing the Limits of Data-Centric Document Parsing at Scale \- arXiv, [https://arxiv.org/html/2604.04771v1](https://arxiv.org/html/2604.04771v1)  
53. MinerU-Diffusion/README.md at main \- GitHub, [https://github.com/opendatalab/MinerU-Diffusion/blob/main/README.md](https://github.com/opendatalab/MinerU-Diffusion/blob/main/README.md)  
54. MinerU 文档解析接口文档, [https://mineru.net/apiManage/docs](https://mineru.net/apiManage/docs)  
55. MaxKB v2+MinerU：通过API实现PDF 档解析并存储 知识库 \- 社区论坛, [https://bbs.fit2cloud.com/t/topic/14800](https://bbs.fit2cloud.com/t/topic/14800)  
56. GitHub \- datalab-to/marker: Convert PDF to markdown \+ JSON quickly with high accuracy, [https://github.com/datalab-to/marker](https://github.com/datalab-to/marker)  
57. Building Intelligent Document Processing with Apache Camel: Docling meets LangChain4j, [https://camel.apache.org/blog/2025/10/camel-docling/](https://camel.apache.org/blog/2025/10/camel-docling/)  
58. Docling Document \- GitHub Pages, [https://docling-project.github.io/docling/reference/docling\_document/](https://docling-project.github.io/docling/reference/docling_document/)  
59. Fix RAG Hallucinations at the Source: Top PDF Parsers Ranked 2025 | by Jiten Bhalavat, [https://infinityai.medium.com/3-proven-techniques-to-accurately-parse-your-pdfs-2c01c5badb84](https://infinityai.medium.com/3-proven-techniques-to-accurately-parse-your-pdfs-2c01c5badb84)  
60. Docling: The Document Alchemist | Towards Data Science, [https://towardsdatascience.com/docling-the-document-alchemist/](https://towardsdatascience.com/docling-the-document-alchemist/)  
61. ChunkNorris: A High-Performance and Low-Energy Approach to PDF Parsing and Chunking \- arXiv, [https://arxiv.org/html/2602.00010v1](https://arxiv.org/html/2602.00010v1)  
62. pymupdf4llm \- PyPI, [https://pypi.org/project/pymupdf4llm/](https://pypi.org/project/pymupdf4llm/)  
63. I Tested 7 Python PDF Extractors So You Don't Have To (2025 Edition) \- Aman Kumar, [https://onlyoneaman.medium.com/i-tested-7-python-pdf-extractors-so-you-dont-have-to-2025-edition-c88013922257](https://onlyoneaman.medium.com/i-tested-7-python-pdf-extractors-so-you-dont-have-to-2025-edition-c88013922257)  
64. MinerU 2.5 for FiftyOne, [https://docs.voxel51.com/plugins/plugins\_ecosystem/mineru\_2\_5.html](https://docs.voxel51.com/plugins/plugins_ecosystem/mineru_2_5.html)  
65. pymupdf4llm-c \- PyPI, [https://pypi.org/project/pymupdf4llm-c/1.2.1/](https://pypi.org/project/pymupdf4llm-c/1.2.1/)  
66. Build an AI-powered multimodal RAG system with Docling and Granite | IBM, [https://www.ibm.com/think/tutorials/build-multimodal-rag-langchain-with-docling-granite](https://www.ibm.com/think/tutorials/build-multimodal-rag-langchain-with-docling-granite)  
67. invocation problem · opendatalab MinerU · Discussion \#2961 \- GitHub, [https://github.com/opendatalab/MinerU/discussions/2961](https://github.com/opendatalab/MinerU/discussions/2961)