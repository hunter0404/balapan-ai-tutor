"""JSON-схемы инструментов (tools) для Anthropic Tool Use.

Каждая схема описывает один навык агента-репетитора. Формат соответствует
спецификации `tools` в Anthropic Messages API.
"""
from __future__ import annotations

from typing import Any

GET_STUDENT_PROGRESS_TOOL: dict[str, Any] = {
    "name": "get_student_progress",
    "description": (
        "Получить прогресс ученика: список уже освоенных казахских слов, "
        "слабые места (слова с низким уровнем усвоения) и последнюю активную тему. "
        "Используй в начале урока, чтобы понять, с чего продолжить, и когда нужно "
        "решить, что повторить, а что изучать впервые."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "student_id": {
                "type": "integer",
                "description": "Уникальный идентификатор ученика в базе данных.",
            }
        },
        "required": ["student_id"],
    },
}

UPDATE_VOCABULARY_MASTERY_TOOL: dict[str, Any] = {
    "name": "update_vocabulary_mastery",
    "description": (
        "Зафиксировать результат попытки ученика произнести/угадать/выбрать казахское "
        "слово: правильно или неправильно. Вызывай сразу после того, как ребёнок дал "
        "ответ на игровое задание, чтобы обновить его словарный прогресс в базе данных."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "student_id": {
                "type": "integer",
                "description": "Уникальный идентификатор ученика.",
            },
            "word": {
                "type": "string",
                "description": "Казахское слово, которое отрабатывалось (например, 'қызыл').",
            },
            "is_correct": {
                "type": "boolean",
                "description": "true, если ученик ответил правильно, иначе false.",
            },
            "topic": {
                "type": "string",
                "description": (
                    "Тема слова: colors | animals | family | numbers | greetings | sounds. "
                    "Указывается, если слово встречается впервые."
                ),
            },
        },
        "required": ["student_id", "word", "is_correct"],
    },
}

GENERATE_GAME_CHALLENGE_TOOL: dict[str, Any] = {
    "name": "generate_game_challenge",
    "description": (
        "Сгенерировать мини-игру для урока: выбор правильной картинки, угадай слово по "
        "звуку или собери слово по буквам. Используй, чтобы предложить ребёнку новое "
        "игровое задание по теме урока и уровню сложности."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Тема мини-игры.",
                "enum": ["colors", "animals", "family", "numbers", "greetings", "sounds"],
            },
            "difficulty_level": {
                "type": "string",
                "description": "Уровень сложности задания.",
                "enum": ["easy", "medium", "hard"],
            },
        },
        "required": ["topic", "difficulty_level"],
    },
}

SYNTHESIZE_VOICE_RESPONSE_TOOL: dict[str, Any] = {
    "name": "synthesize_voice_response",
    "description": (
        "Озвучить реплику персонажа на казахском языке через TTS-движок (Piper/ISSAI). "
        "Вызывай для каждой финальной реплики, которую персонаж произносит вслух ребёнку, "
        "чтобы получить путь к аудиофайлу для воспроизведения на клиенте."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "text_kazakh": {
                "type": "string",
                "description": "Текст реплики на казахском языке, который нужно озвучить.",
            },
            "emotional_tone": {
                "type": "string",
                "description": "Эмоциональная окраска голоса персонажа.",
                "enum": ["friendly", "excited", "encouraging", "calm", "celebratory"],
            },
        },
        "required": ["text_kazakh", "emotional_tone"],
    },
}

ALL_TOOLS: list[dict[str, Any]] = [
    GET_STUDENT_PROGRESS_TOOL,
    UPDATE_VOCABULARY_MASTERY_TOOL,
    GENERATE_GAME_CHALLENGE_TOOL,
    SYNTHESIZE_VOICE_RESPONSE_TOOL,
]
