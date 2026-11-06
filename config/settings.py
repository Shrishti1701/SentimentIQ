"""Environment-backed application settings."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True, slots=True)
class Settings:
    """Non-secret runtime settings loaded from environment variables."""

    database_url: str | None = os.getenv("DATABASE_URL")
    redis_url: str | None = os.getenv("REDIS_URL")
    news_api_key: str | None = os.getenv("NEWS_API_KEY")
    app_name: str = "SentimentIQ"
    api_version: str = "0.1.0"


settings = Settings()
