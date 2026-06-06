from pathlib import Path

from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_api_base: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    embedding_api_key: str = ""
    embedding_api_base: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    # Qdrant 启动模式:
    #   - qdrant_url 为空字符串 → 进程内 local mode (文件持久化, 无需 Docker, 默认)
    #   - qdrant_url = "http://host:port" → 远程模式 (Qdrant 单独容器/服务器)
    qdrant_url: str = ""
    qdrant_local_path: str = str(_PROJECT_ROOT / "data" / "qdrant_storage")
    upload_root: str = str(_PROJECT_ROOT / "uploads")
    sqlite_path: str = str(_PROJECT_ROOT / "data" / "foxsay.db")
    foxsay_env: str = "development"
    pdf_parser: str = "docling"

    model_config = {
        "env_prefix": "",
        "case_sensitive": False,
        "env_file": str(_PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()
