from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://emr:emr123@localhost:5433/emr_dev"
    TEST_DATABASE_URL: str = "postgresql+asyncpg://emr:emr123@localhost:5433/emr_test"

    # Qwen
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_CHAT_MODEL: str = "qwen-max"
    QWEN_EMBEDDING_MODEL: str = "text-embedding-v3"
    QWEN_VL_MODEL: str = "qwen-vl-max"
    EMBEDDING_DIM: int = 1024

    # Security
    ENCRYPTION_KEY: str = ""

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


settings = Settings()
