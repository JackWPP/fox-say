from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_api_base: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    embedding_api_key: str = ""
    embedding_api_base: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    # 图片 VLM 与 embedding/生成模型独立配置，避免语义和预算混用。
    vlm_api_key: str = ""
    vlm_api_base: str = "https://api.siliconflow.cn/v1"
    vlm_model: str = "Qwen/Qwen3.6-27B"
    vlm_max_tokens: int = Field(default=2048, gt=0)
    # V2-E is deliberately opt-in: a persisted visual job is visible while
    # disabled, but it must never turn an ordinary upload into an API call.
    knowledge_visual_analysis_enabled: bool = False
    knowledge_visual_max_assets_per_job: int = Field(default=3, gt=0, le=12)
    knowledge_visual_input_token_reserve: int = Field(default=6000, gt=0)
    # Qdrant 启动模式:
    #   - qdrant_url 为空字符串 → 进程内 local mode (文件持久化, 无需 Docker, 默认)
    #   - qdrant_url = "http://host:port" → 远程模式 (Qdrant 单独容器/服务器)
    qdrant_url: str = ""
    qdrant_local_path: str = str(_PROJECT_ROOT / "data" / "qdrant_storage")
    upload_root: str = str(_PROJECT_ROOT / "uploads")
    sqlite_path: str = str(_PROJECT_ROOT / "data" / "foxsay.db")
    foxsay_env: str = "development"
    pdf_parser: str = "auto"  # "auto" = PDF 探测路由(电子版→Docling, 扫描件→MinerU)
    # MinerU V4 云端 API
    mineru_api_token: str = ""
    mineru_api_base: str = "https://mineru.net/api/v4"
    mineru_poll_interval: int = 5       # 轮询间隔（秒）
    mineru_max_poll_time: int = 600     # 最大轮询时间（秒）
    # 批量上传与并发控制
    max_batch_upload: int = 15  # 单次 /materials/batch 最多文件数
    max_concurrent_parsing: int = 3  # 同时解析的文件数(asyncio.Semaphore 上限)

    # V2 持久知识任务：课程级编译任务使用显式 token budget。
    knowledge_job_default_token_budget: int = 12000
    knowledge_job_default_max_attempts: int = Field(default=3, gt=0)
    # D1a locks this cap to one (course_id, source_revision) on the first
    # audited text request. It is deliberately independent from a single job.
    knowledge_course_default_token_budget: int = 36000
    knowledge_model_timeout_seconds: float = Field(default=60.0, gt=0)
    # Explicit opt-in prevents an ordinary local/test upload from unexpectedly
    # spending tokens; production can enable it once G0-like budgets are set.
    knowledge_semantic_auto_enqueue: bool = False
    # D3b is also opt-in: relation extraction is one audited text request.
    knowledge_kc_relation_auto_enqueue: bool = False
    knowledge_kc_relation_max_output_tokens: int = Field(default=1200, gt=0, le=4000)
    # SQLite MVP 只运行一个受控 worker；lease 需要覆盖较慢的文档解析并由 heartbeat 续约。
    knowledge_worker_lease_seconds: int = Field(default=900, gt=0)
    knowledge_worker_poll_interval_seconds: float = Field(default=0.5, gt=0)

    # PR0 新增:解耦 Judge 模型 (评测端 / 轻量分类端使用)
    # 必须跟 deepseek_model 不同家族,否则 self-preference bias (调研结论)。
    # 默认指向 LM Studio 本地部署的 Qwen3.5 9B (OpenAI 兼容)。
    # 用途:DeepEval Judge / 题库质检 / prereq 字符串纠偏二审 /
    #       cognitive_dimension 分类 / ChapterWiki overview 质检。
    judge_api_key: str = "lm-studio"  # LM Studio 不验证 key, 占位即可
    judge_api_base: str = "http://localhost:1234/v1"
    judge_model_name: str = "qwen/qwen3.5-9b"
    # 大批量轻活用 (非 reasoning, 快): cognitive_dim 5 选 1, JSON 格式校验
    judge_fast_model_name: str = "qwen/qwen3-4b-2507"
    # NLI 蕴含判定 (评测 v2 ALiiCE 用):
    reranker_model_name: str = "qwen3-reranker-0.6b"

    model_config = {
        "env_prefix": "",
        "case_sensitive": False,
        "env_file": str(_PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()
