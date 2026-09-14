"""Сервис синтеза речи (TTS) для озвучки реплик персонажа на казахском языке.

Поддерживает локальный движок Piper (https://github.com/rhasspy/piper) с
моделью ISSAI kk_KZ. Если бинарник/модель Piper недоступны в окружении,
сервис прозрачно переключается в режим заглушки (`stub`): пишет подробный
лог и возвращает путь к пустому placeholder-файлу, не прерывая работу
агента. Это позволяет разрабатывать и тестировать диалоговую логику без
установленной модели синтеза речи.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import wave
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


class TTSService:
    """Обёртка над локальным TTS-движком с безопасным fallback-режимом."""

    def __init__(
        self,
        engine: str,
        binary_path: str,
        model_path: str,
        output_dir: str,
        enabled: bool,
    ) -> None:
        self.engine = engine
        self.binary_path = binary_path
        self.model_path = model_path
        self.output_dir = Path(output_dir)
        self.enabled = enabled
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._piper_available = self._detect_piper()
        if not self._piper_available:
            logger.warning(
                "TTS движок '%s' недоступен (binary=%s, model=%s). "
                "Переключаюсь в режим заглушки: аудио не будет синтезировано по-настоящему, "
                "но API продолжит работать и логировать все запросы.",
                self.engine,
                self.binary_path,
                self.model_path,
            )

    def _detect_piper(self) -> bool:
        if self.engine != "piper":
            return False
        has_binary = shutil.which(self.binary_path) is not None
        has_model = Path(self.model_path).exists()
        return has_binary and has_model

    def _cache_key(self, text: str, tone: str) -> str:
        digest = hashlib.sha256(f"{tone}::{text}".encode("utf-8")).hexdigest()[:16]
        return f"{digest}.wav"

    def synthesize(self, text: str, tone: str) -> dict[str, Any]:
        """Синтезирует речь и возвращает метаданные аудиофайла.

        Возвращаемый словарь всегда содержит ключи `audio_path`, `engine`,
        `is_stub` и `cached`, чтобы клиент/агент мог единообразно
        обработать результат независимо от наличия реального TTS-движка.
        """
        if not self.enabled:
            logger.info("TTS отключён настройками (TTS_ENABLED=false). Текст: %s", text)
            return {
                "audio_path": None,
                "engine": "disabled",
                "is_stub": True,
                "cached": False,
                "text": text,
                "tone": tone,
            }

        filename = self._cache_key(text, tone)
        output_path = self.output_dir / filename

        if output_path.exists():
            logger.info("TTS cache hit: %s", output_path)
            return {
                "audio_path": str(output_path),
                "engine": self.engine if self._piper_available else "stub",
                "is_stub": not self._piper_available,
                "cached": True,
                "text": text,
                "tone": tone,
            }

        if self._piper_available:
            try:
                self._synthesize_with_piper(text=text, output_path=output_path)
                logger.info("Piper синтезировал речь -> %s", output_path)
                return {
                    "audio_path": str(output_path),
                    "engine": self.engine,
                    "is_stub": False,
                    "cached": False,
                    "text": text,
                    "tone": tone,
                }
            except (subprocess.SubprocessError, OSError) as exc:
                logger.error("Ошибка синтеза Piper: %s. Использую заглушку.", exc)

        self._write_stub_wav(output_path)
        logger.info(
            "[STUB TTS] tone=%s text='%s' -> заглушка сохранена в %s", tone, text, output_path
        )
        return {
            "audio_path": str(output_path),
            "engine": "stub",
            "is_stub": True,
            "cached": False,
            "text": text,
            "tone": tone,
        }

    def _synthesize_with_piper(self, text: str, output_path: Path) -> None:
        command = [
            self.binary_path,
            "--model",
            self.model_path,
            "--output_file",
            str(output_path),
        ]
        subprocess.run(
            command,
            input=text.encode("utf-8"),
            check=True,
            capture_output=True,
            timeout=30,
        )

    @staticmethod
    def _write_stub_wav(output_path: Path) -> None:
        """Создаёт минимальный валидный (тихий) WAV-файл как плейсхолдер."""
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(b"\x00\x00" * 1600)  # 0.1 секунды тишины


@lru_cache
def get_tts_service() -> TTSService:
    """Возвращает закэшированный синглтон TTS-сервиса, сконфигурированный из настроек."""
    settings = get_settings()
    return TTSService(
        engine=settings.tts_engine,
        binary_path=settings.piper_binary_path,
        model_path=settings.piper_model_path,
        output_dir=settings.tts_output_dir,
        enabled=settings.tts_enabled,
    )
