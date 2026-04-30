from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file (app/core/config.py → project root)
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://emr:emr123@localhost:5432/emr_dev"
    TEST_DATABASE_URL: str = "postgresql+asyncpg://emr:emr123@localhost:5432/emr_test"

    # Qwen
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_CHAT_MODEL: str = "qwen-max"
    QWEN_EMBEDDING_MODEL: str = "text-embedding-v3"
    QWEN_VL_MODEL: str = "qwen-vl-max"
    EMBEDDING_DIM: int = 1024

    # Security
    ENCRYPTION_KEY: str = ""
    JWT_SECRET: str = "change-me-in-production-use-strong-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_MIN: int = 60
    REFRESH_TOKEN_TTL_DAYS: int = 7

    # MinerU
    MINERU_API_KEY: str = ""
    MINERU_SINGLE_URL: str = "https://mineru.net/api/v4/extract/task"
    MINERU_BATCH_UPLOAD_URL: str = "https://mineru.net/api/v4/file-urls/batch"
    MINERU_SINGLE_POLL_URL: str = "https://mineru.net/api/v4/extract/task/{task_id}"
    MINERU_BATCH_POLL_URL: str = "https://mineru.net/api/v4/extract-results/batch/{batch_id}"
    MINERU_MODEL_VERSION: str = "vlm"
    MINERU_LANGUAGE: str = "en"
    MINERU_POLL_INTERVAL: int = 10
    MINERU_MAX_WAIT: int = 900

    # Feature flags
    IMAGE_DESCRIPTION_ENABLED: bool = True

    # Observability
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_JSON: bool = True
    LOG_REQUESTS: bool = True
    LOG_EXCLUDE_PATHS: str = "/health"
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "production"
    SENTRY_TRACES_SAMPLE_RATE: float = Field(default=0.0, ge=0.0, le=1.0)
    LOKI_URL: str = ""
    LOKI_USERNAME: str = ""
    LOKI_PASSWORD: str = ""
    LOKI_TENANT_ID: str = ""
    LOKI_TIMEOUT_SECONDS: float = Field(default=2.0, gt=0.0)


settings = Settings()
