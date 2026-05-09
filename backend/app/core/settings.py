"""Environment variable names for future runtime configuration.

Do not read secrets at import time in this structural scaffold.
"""

DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEEPSEEK_API_BASE_ENV = "DEEPSEEK_API_BASE"
DEEPSEEK_MODEL_ENV = "DEEPSEEK_MODEL"
QDRANT_URL_ENV = "QDRANT_URL"
FOXSAY_ENV_ENV = "FOXSAY_ENV"

DEFAULT_DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"

