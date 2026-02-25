from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5", alias="OPENAI_MODEL")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    max_video_minutes: int = Field(default=60, alias="MAX_VIDEO_MINUTES")
    whisper_model_size: str = Field(default="small", alias="WHISPER_MODEL_SIZE")
    whisper_device: str = Field(default="cpu", alias="WHISPER_DEVICE")
    whisper_compute_type: str = Field(default="int8", alias="WHISPER_COMPUTE_TYPE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    allowed_telegram_user_ids_raw: str = Field(default="", alias="ALLOWED_TELEGRAM_USER_IDS")
    ytdlp_cookies_file: str = Field(default="", alias="YTDLP_COOKIES_FILE")

    @property
    def max_video_seconds(self) -> int:
        return self.max_video_minutes * 60

    @property
    def allowed_telegram_user_ids(self) -> set[int]:
        raw = self.allowed_telegram_user_ids_raw.strip()
        if not raw:
            return set()
        return {int(item.strip()) for item in raw.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
