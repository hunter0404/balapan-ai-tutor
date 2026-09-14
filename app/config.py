"""Настройки приложения на базе Pydantic Settings."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация читается из переменных окружения / файла .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Anthropic
    anthropic_api_key: str = "sk-ant-placeholder"
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    anthropic_max_tokens: int = 1024
    anthropic_temperature: float = 0.6

    # База данных
    database_url: str = "sqlite:///./data/kazakh_tutor.db"

    # TTS (Piper / ISSAI)
    tts_enabled: bool = True
    tts_engine: str = "piper"  # piper | issai | stub
    piper_binary_path: str = "piper"
    piper_model_path: str = "./models/kk_KZ-issai-medium.onnx"
    tts_output_dir: str = "./data/audio_cache"

    # Приложение
    app_name: str = "Kazakh AI Tutor"
    app_env: str = "development"
    cors_origins: list[str] = ["*"]
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Возвращает закэшированный синглтон настроек."""
    return Settings()
