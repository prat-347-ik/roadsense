from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "RoadSense API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/v1"

    # Database & Storage
    DATABASE_URL: str = "postgresql+asyncpg://roadsense:roadsense@postgres:5432/roadsense"
    REDIS_URL: str = "redis://redis:6379/0"
    MINIO_ENDPOINT_URL: str = "http://minio:9000"
    MINIO_ROOT_USER: str = "roadsense-admin"
    MINIO_ROOT_PASSWORD: str = "use-a-long-random-password"
    MINIO_BUCKET: str = "evidence"

    # Security & Hashing
    JWT_SECRET: str = "change-me-in-development"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    PLATE_HASH_KEY: str = "change-me-to-a-random-secret"

    # Business Logic Configs (Step 5 configurable)
    CLUSTER_RADIUS_METERS: float = 100.0
    GEOHASH_PRECISION: int = 7
    CORROBORATION_TIME_WINDOW_SECONDS: int = 300
    EVIDENCE_TTL_DAYS: int = 30

    SENTRY_DSN: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
