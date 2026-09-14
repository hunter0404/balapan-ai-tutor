"""Базовые юнит-тесты для инструментов агента и цикла Tool Use.

Тесты не обращаются к реальному Anthropic API — вызовы `messages.create`
мокаются, чтобы проверить логику диспетчеризации инструментов и работу с БД
без сетевых запросов и затрат.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.database import Student, WordProgress
from app.skills.handlers import (
    VALID_TOPICS,
    execute_tool,
    handle_generate_game_challenge,
    handle_get_student_progress,
    handle_synthesize_voice_response,
    handle_update_vocabulary_mastery,
)


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------
@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture()
def student(session: Session) -> Student:
    s = Student(name="Айым", age=7, class_name="1А")
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


# ---------------------------------------------------------------------------
# Tool: get_student_progress
# ---------------------------------------------------------------------------
def test_get_student_progress_unknown_student_returns_error(session: Session) -> None:
    result = handle_get_student_progress(session, student_id=999)
    assert "error" in result


def test_get_student_progress_empty_history(session: Session, student: Student) -> None:
    result = handle_get_student_progress(session, student_id=student.id)
    assert result["student_id"] == student.id
    assert result["total_words_seen"] == 0
    assert result["mastered_words"] == []
    assert result["weak_spots"] == []


def test_get_student_progress_classifies_mastery_buckets(session: Session, student: Student) -> None:
    session.add_all(
        [
            WordProgress(student_id=student.id, word_kazakh="қызыл", topic="colors", mastery_level=85),
            WordProgress(student_id=student.id, word_kazakh="көк", topic="colors", mastery_level=50),
            WordProgress(student_id=student.id, word_kazakh="сары", topic="colors", mastery_level=10),
        ]
    )
    session.commit()

    result = handle_get_student_progress(session, student_id=student.id)
    assert result["mastered_words"] == ["қызыл"]
    assert result["words_in_progress"] == ["көк"]
    assert [w["word"] for w in result["weak_spots"]] == ["сары"]


# ---------------------------------------------------------------------------
# Tool: update_vocabulary_mastery
# ---------------------------------------------------------------------------
def test_update_vocabulary_mastery_creates_new_entry(session: Session, student: Student) -> None:
    result = handle_update_vocabulary_mastery(
        session, student_id=student.id, word="қызыл", is_correct=True, topic="colors"
    )
    assert result["new_mastery_level"] == 15
    assert result["times_correct"] == 1
    assert result["is_mastered"] is False


def test_update_vocabulary_mastery_incorrect_lowers_score(session: Session, student: Student) -> None:
    handle_update_vocabulary_mastery(session, student_id=student.id, word="көк", is_correct=True)
    result = handle_update_vocabulary_mastery(session, student_id=student.id, word="көк", is_correct=False)
    assert result["new_mastery_level"] == 10  # 15 - 5
    assert result["times_incorrect"] == 1


def test_update_vocabulary_mastery_score_is_clamped_between_0_and_100(
    session: Session, student: Student
) -> None:
    for _ in range(10):
        handle_update_vocabulary_mastery(session, student_id=student.id, word="бір", is_correct=True)
    result = handle_update_vocabulary_mastery(session, student_id=student.id, word="бір", is_correct=True)
    assert result["new_mastery_level"] == 100

    for _ in range(25):
        result = handle_update_vocabulary_mastery(
            session, student_id=student.id, word="бір", is_correct=False
        )
    assert result["new_mastery_level"] == 0


def test_update_vocabulary_mastery_unknown_student(session: Session) -> None:
    result = handle_update_vocabulary_mastery(session, student_id=999, word="қызыл", is_correct=True)
    assert "error" in result


# ---------------------------------------------------------------------------
# Tool: generate_game_challenge
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("topic", VALID_TOPICS)
def test_generate_game_challenge_valid_topics(topic: str) -> None:
    result = handle_generate_game_challenge(topic=topic, difficulty_level="easy")
    assert result["topic"] == topic
    assert result["game_type"] == "pick_the_picture"
    assert "correct_answer" in result
    assert len(result["options"]) >= 2


def test_generate_game_challenge_invalid_topic() -> None:
    result = handle_generate_game_challenge(topic="space", difficulty_level="easy")
    assert "error" in result


def test_generate_game_challenge_invalid_difficulty() -> None:
    result = handle_generate_game_challenge(topic="colors", difficulty_level="impossible")
    assert "error" in result


def test_generate_game_challenge_hard_can_produce_build_the_word() -> None:
    seen_types = {
        handle_generate_game_challenge(topic="numbers", difficulty_level="hard")["game_type"]
        for _ in range(30)
    }
    assert seen_types.issubset({"guess_by_sound", "build_the_word"})


# ---------------------------------------------------------------------------
# Tool: synthesize_voice_response
# ---------------------------------------------------------------------------
def test_synthesize_voice_response_returns_audio_metadata() -> None:
    result = handle_synthesize_voice_response(text_kazakh="Сәлем!", emotional_tone="friendly")
    assert result["text"] == "Сәлем!"
    assert result["tone"] == "friendly"
    assert "audio_path" in result
    assert "is_stub" in result


# ---------------------------------------------------------------------------
# Диспетчер execute_tool
# ---------------------------------------------------------------------------
def test_execute_tool_dispatches_known_tools(session: Session, student: Student) -> None:
    result = execute_tool(
        "update_vocabulary_mastery",
        {"student_id": student.id, "word": "апа", "is_correct": True, "topic": "family"},
        session,
    )
    assert result["new_mastery_level"] == 15


def test_execute_tool_unknown_tool_returns_error(session: Session) -> None:
    result = execute_tool("do_something_unsupported", {}, session)
    assert "error" in result


# ---------------------------------------------------------------------------
# TutorAgent: цикл Tool Use с мокнутым Anthropic-клиентом
# ---------------------------------------------------------------------------
class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text

    def model_dump(self) -> dict:
        return {"type": "text", "text": self.text}


class _FakeToolUseBlock:
    def __init__(self, block_id: str, name: str, tool_input: dict) -> None:
        self.type = "tool_use"
        self.id = block_id
        self.name = name
        self.input = tool_input

    def model_dump(self) -> dict:
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}


class _FakeResponse:
    def __init__(self, content: list, stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason


def test_tutor_agent_tool_use_loop(session: Session, student: Student) -> None:
    with patch("app.agent.tutor_agent.anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        tool_call_response = _FakeResponse(
            content=[
                _FakeToolUseBlock(
                    "toolu_1", "update_vocabulary_mastery",
                    {"student_id": student.id, "word": "қызыл", "is_correct": True, "topic": "colors"},
                )
            ],
            stop_reason="tool_use",
        )
        final_response = _FakeResponse(
            content=[_FakeTextBlock("Жарайсың! 🎉")],
            stop_reason="end_turn",
        )
        mock_client.messages.create.side_effect = [tool_call_response, final_response]

        from app.agent.tutor_agent import TutorAgent

        agent = TutorAgent(api_key="test-key", model="claude-3-5-sonnet-20241022")
        result = agent.send_message(
            session=session,
            conversation_id="conv-test",
            student_id=student.id,
            user_text="қызыл",
        )

        assert result.reply_text == "Жарайсың! 🎉"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "update_vocabulary_mastery"
        assert mock_client.messages.create.call_count == 2

        # Прогресс действительно сохранился в БД внутри цикла tool use.
        progress = handle_get_student_progress(session, student_id=student.id)
        assert progress["total_words_seen"] == 1


def test_tutor_agent_reset_conversation_clears_history(student: Student) -> None:
    with patch("app.agent.tutor_agent.anthropic.Anthropic"):
        from app.agent.tutor_agent import TutorAgent

        agent = TutorAgent(api_key="test-key")
        agent._conversations["conv-a"] = [{"role": "user", "content": "сәлем"}]
        agent.reset_conversation("conv-a")
        assert "conv-a" not in agent._conversations
