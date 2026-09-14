"""Агент-репетитор: обёртка над Anthropic API с циклом Tool Use."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic
from sqlmodel import Session

from app.agent.prompts import SYSTEM_PROMPT, build_lesson_kickoff_prompt
from app.config import get_settings
from app.skills.definitions import ALL_TOOLS
from app.skills.handlers import execute_tool

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 6


@dataclass
class AgentTurnResult:
    """Результат одного хода диалога с агентом."""

    reply_text: str
    audio_path: str | None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class TutorAgent:
    """Ведёт диалог с ребёнком, используя Claude с Tool Use.

    Хранит историю сообщений в памяти по ключу `conversation_id`
    (например, `student_id`). Для продакшн-развёртывания с несколькими
    воркерами историю следует вынести во внешнее хранилище (Redis и т.п.),
    интерфейс класса это допускает без изменений снаружи.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(api_key=api_key or settings.anthropic_api_key)
        self._model = model or settings.anthropic_model
        self._max_tokens = max_tokens or settings.anthropic_max_tokens
        self._temperature = temperature if temperature is not None else settings.anthropic_temperature
        self._conversations: dict[str, list[dict[str, Any]]] = {}

    def reset_conversation(self, conversation_id: str) -> None:
        self._conversations.pop(conversation_id, None)

    def start_lesson(
        self,
        session: Session,
        conversation_id: str,
        student_id: int,
        student_name: str,
        topic: str | None = None,
    ) -> AgentTurnResult:
        """Инициирует новый урок: агент сам проверит прогресс и поздоровается."""
        kickoff_text = build_lesson_kickoff_prompt(student_name=student_name, topic=topic)
        return self.send_message(
            session=session,
            conversation_id=conversation_id,
            student_id=student_id,
            user_text=kickoff_text,
        )

    def send_message(
        self,
        session: Session,
        conversation_id: str,
        student_id: int,
        user_text: str,
    ) -> AgentTurnResult:
        """Отправляет реплику ребёнка агенту и выполняет полный цикл Tool Use."""
        messages = self._conversations.setdefault(conversation_id, [])
        messages.append({"role": "user", "content": user_text})

        tool_calls_log: list[dict[str, Any]] = []
        last_audio_path: str | None = None
        final_text_parts: list[str] = []

        for _ in range(MAX_TOOL_ITERATIONS):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=SYSTEM_PROMPT,
                tools=ALL_TOOLS,
                messages=messages,
            )

            assistant_content = [block.model_dump() for block in response.content]
            messages.append({"role": "assistant", "content": assistant_content})

            text_blocks = [b["text"] for b in assistant_content if b.get("type") == "text"]
            final_text_parts.extend(text_blocks)

            if response.stop_reason != "tool_use":
                break

            tool_use_blocks = [b for b in assistant_content if b.get("type") == "tool_use"]
            tool_result_content: list[dict[str, Any]] = []

            for block in tool_use_blocks:
                tool_name = block["name"]
                tool_input = block["input"]
                tool_use_id = block["id"]

                result = execute_tool(tool_name, tool_input, session)
                tool_calls_log.append({"name": tool_name, "input": tool_input, "result": result})

                if tool_name == "synthesize_voice_response" and result.get("audio_path"):
                    last_audio_path = result["audio_path"]

                tool_result_content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

            messages.append({"role": "user", "content": tool_result_content})
        else:
            logger.warning(
                "Достигнут лимит итераций Tool Use (%s) для conversation_id=%s",
                MAX_TOOL_ITERATIONS,
                conversation_id,
            )

        reply_text = "\n".join(part.strip() for part in final_text_parts if part.strip())
        return AgentTurnResult(reply_text=reply_text, audio_path=last_audio_path, tool_calls=tool_calls_log)


_agent_instance: TutorAgent | None = None


def get_tutor_agent() -> TutorAgent:
    """Возвращает синглтон агента для использования в FastAPI-эндпоинтах."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = TutorAgent()
    return _agent_instance
