from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    deepseek_api_key: str = ""
    deepseek_api_base: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    qdrant_url: str = "http://localhost:6333"
    foxsay_env: str = "development"

    model_config = {"env_prefix": "", "case_sensitive": False}
