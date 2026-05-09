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
    qdrant_url: str = "http://localhost:6333"
    sqlite_path: str = str(_PROJECT_ROOT / "data" / "foxsay.db")
    foxsay_env: str = "development"

    model_config = {
        "env_prefix": "",
        "case_sensitive": False,
        "env_file": str(_PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()
