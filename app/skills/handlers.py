"""Бизнес-логика выполнения инструментов (tools) агента-репетитора.

Каждый handler принимает уже распарсенный `tool_input` от Claude и
возвращает JSON-совместимый словарь, который будет отправлен обратно
модели как `tool_result`.
"""
from __future__ import annotations

import logging
import random
from typing import Any

from sqlmodel import Session, select

from app.audio.tts_service import get_tts_service
from app.database import Student, WordProgress, utcnow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Банк слов для первоклассников по темам. Каждое слово содержит казахский
# специфический звук, чтобы агент мог целенаправленно его отрабатывать.
# ---------------------------------------------------------------------------
WORD_BANK: dict[str, list[dict[str, str]]] = {
    "colors": [
        {"kazakh": "қызыл", "ru": "красный", "image": "🔴", "focus_sound": "қ"},
        {"kazakh": "көк", "ru": "синий", "image": "🔵", "focus_sound": "ө"},
        {"kazakh": "сары", "ru": "жёлтый", "image": "🟡", "focus_sound": "с"},
        {"kazakh": "жасыл", "ru": "зелёный", "image": "🟢", "focus_sound": "ж"},
        {"kazakh": "қара", "ru": "чёрный", "image": "⚫", "focus_sound": "қ"},
        {"kazakh": "ақ", "ru": "белый", "image": "⚪", "focus_sound": "қ"},
        {"kazakh": "қоңыр", "ru": "коричневый", "image": "🟤", "focus_sound": "ң"},
    ],
    "animals": [
        {"kazakh": "мысық", "ru": "кошка", "image": "🐱", "focus_sound": "қ"},
        {"kazakh": "ит", "ru": "собака", "image": "🐶", "focus_sound": "и"},
        {"kazakh": "қоян", "ru": "заяц", "image": "🐰", "focus_sound": "қ"},
        {"kazakh": "түйе", "ru": "верблюд", "image": "🐫", "focus_sound": "ү"},
        {"kazakh": "жылқы", "ru": "лошадь", "image": "🐴", "focus_sound": "қ"},
        {"kazakh": "қой", "ru": "овца", "image": "🐑", "focus_sound": "қ"},
        {"kazakh": "үй құсы", "ru": "курица", "image": "🐔", "focus_sound": "ү"},
    ],
    "family": [
        {"kazakh": "апа", "ru": "мама/бабушка", "image": "👩", "focus_sound": "а"},
        {"kazakh": "әке", "ru": "папа", "image": "👨", "focus_sound": "ә"},
        {"kazakh": "әже", "ru": "бабушка", "image": "👵", "focus_sound": "ә"},
        {"kazakh": "ата", "ru": "дедушка", "image": "👴", "focus_sound": "а"},
        {"kazakh": "аға", "ru": "старший брат", "image": "🧑", "focus_sound": "ғ"},
        {"kazakh": "қарындас", "ru": "младшая сестра", "image": "👧", "focus_sound": "қ"},
        {"kazakh": "іні", "ru": "младший брат", "image": "🧒", "focus_sound": "і"},
    ],
    "numbers": [
        {"kazakh": "бір", "ru": "один", "image": "1️⃣", "focus_sound": "б"},
        {"kazakh": "екі", "ru": "два", "image": "2️⃣", "focus_sound": "і"},
        {"kazakh": "үш", "ru": "три", "image": "3️⃣", "focus_sound": "ү"},
        {"kazakh": "төрт", "ru": "четыре", "image": "4️⃣", "focus_sound": "ө"},
        {"kazakh": "бес", "ru": "пять", "image": "5️⃣", "focus_sound": "б"},
        {"kazakh": "алты", "ru": "шесть", "image": "6️⃣", "focus_sound": "а"},
        {"kazakh": "жеті", "ru": "семь", "image": "7️⃣", "focus_sound": "ж"},
        {"kazakh": "сегіз", "ru": "восемь", "image": "8️⃣", "focus_sound": "і"},
        {"kazakh": "тоғыз", "ru": "девять", "image": "9️⃣", "focus_sound": "ғ"},
        {"kazakh": "он", "ru": "десять", "image": "🔟", "focus_sound": "о"},
    ],
    "greetings": [
        {"kazakh": "сәлем", "ru": "привет", "image": "👋", "focus_sound": "ә"},
        {"kazakh": "қалайсың", "ru": "как дела", "image": "🙂", "focus_sound": "қ"},
        {"kazakh": "рахмет", "ru": "спасибо", "image": "🙏", "focus_sound": "х"},
        {"kazakh": "сау бол", "ru": "пока", "image": "👋", "focus_sound": "с"},
        {"kazakh": "жақсы", "ru": "хорошо", "image": "👍", "focus_sound": "ж"},
    ],
    "sounds": [
        {"kazakh": "әже", "ru": "бабушка (звук ә)", "image": "👵", "focus_sound": "ә"},
        {"kazakh": "іні", "ru": "младший брат (звук і)", "image": "🧒", "focus_sound": "і"},
        {"kazakh": "аң", "ru": "зверь (звук ң)", "image": "🦌", "focus_sound": "ң"},
        {"kazakh": "аға", "ru": "старший брат (звук ғ)", "image": "🧑", "focus_sound": "ғ"},
        {"kazakh": "үй", "ru": "дом (звук ү)", "image": "🏠", "focus_sound": "ү"},
        {"kazakh": "ұя", "ru": "гнездо (звук ұ)", "image": "🪺", "focus_sound": "ұ"},
        {"kazakh": "қалам", "ru": "ручка (звук қ)", "image": "✏️", "focus_sound": "қ"},
        {"kazakh": "өрік", "ru": "абрикос (звук ө)", "image": "🍑", "focus_sound": "ө"},
        {"kazakh": "һәм", "ru": "и (звук һ)", "image": "➕", "focus_sound": "һ"},
    ],
}

VALID_TOPICS = list(WORD_BANK.keys())

GAME_TYPES_BY_DIFFICULTY: dict[str, list[str]] = {
    "easy": ["pick_the_picture"],
    "medium": ["pick_the_picture", "guess_by_sound"],
    "hard": ["guess_by_sound", "build_the_word"],
}


def _mastery_delta(is_correct: bool) -> int:
    return 15 if is_correct else -5


# ---------------------------------------------------------------------------
# Tool 1: get_student_progress
# ---------------------------------------------------------------------------
def handle_get_student_progress(session: Session, student_id: int) -> dict[str, Any]:
    student = session.get(Student, student_id)
    if student is None:
        return {"error": f"Ученик с id={student_id} не найден."}

    progress_rows = session.exec(
        select(WordProgress).where(WordProgress.student_id == student_id)
    ).all()

    mastered = [p.word_kazakh for p in progress_rows if p.mastery_level >= 70]
    weak_spots = [
        {"word": p.word_kazakh, "topic": p.topic, "mastery_level": p.mastery_level}
        for p in progress_rows
        if p.mastery_level < 40
    ]
    in_progress = [
        p.word_kazakh for p in progress_rows if 40 <= p.mastery_level < 70
    ]

    return {
        "student_id": student_id,
        "student_name": student.name,
        "preferred_topic": student.preferred_topic,
        "total_words_seen": len(progress_rows),
        "mastered_words": mastered,
        "words_in_progress": in_progress,
        "weak_spots": weak_spots,
        "suggested_next_topic": student.preferred_topic or random.choice(VALID_TOPICS),
    }


# ---------------------------------------------------------------------------
# Tool 2: update_vocabulary_mastery
# ---------------------------------------------------------------------------
def handle_update_vocabulary_mastery(
    session: Session,
    student_id: int,
    word: str,
    is_correct: bool,
    topic: str | None = None,
) -> dict[str, Any]:
    student = session.get(Student, student_id)
    if student is None:
        return {"error": f"Ученик с id={student_id} не найден."}

    normalized_word = word.strip().lower()
    existing = session.exec(
        select(WordProgress).where(
            WordProgress.student_id == student_id,
            WordProgress.word_kazakh == normalized_word,
        )
    ).first()

    if existing is None:
        resolved_topic = topic or _find_topic_for_word(normalized_word) or "general"
        translation = _find_translation_for_word(normalized_word)
        existing = WordProgress(
            student_id=student_id,
            word_kazakh=normalized_word,
            translation_ru=translation,
            topic=resolved_topic,
            mastery_level=0,
        )

    if is_correct:
        existing.times_correct += 1
    else:
        existing.times_incorrect += 1

    existing.mastery_level = max(0, min(100, existing.mastery_level + _mastery_delta(is_correct)))
    existing.last_practiced = utcnow()

    session.add(existing)
    session.commit()
    session.refresh(existing)

    return {
        "student_id": student_id,
        "word": existing.word_kazakh,
        "new_mastery_level": existing.mastery_level,
        "times_correct": existing.times_correct,
        "times_incorrect": existing.times_incorrect,
        "is_mastered": existing.mastery_level >= 70,
    }


def _find_topic_for_word(word: str) -> str | None:
    for topic, words in WORD_BANK.items():
        if any(w["kazakh"] == word for w in words):
            return topic
    return None


def _find_translation_for_word(word: str) -> str:
    for words in WORD_BANK.values():
        for w in words:
            if w["kazakh"] == word:
                return w["ru"]
    return ""


# ---------------------------------------------------------------------------
# Tool 3: generate_game_challenge
# ---------------------------------------------------------------------------
def handle_generate_game_challenge(topic: str, difficulty_level: str) -> dict[str, Any]:
    if topic not in WORD_BANK:
        return {"error": f"Неизвестная тема '{topic}'. Доступные темы: {VALID_TOPICS}"}
    if difficulty_level not in GAME_TYPES_BY_DIFFICULTY:
        return {"error": "Уровень сложности должен быть easy, medium или hard."}

    pool = WORD_BANK[topic]
    game_type = random.choice(GAME_TYPES_BY_DIFFICULTY[difficulty_level])
    target = random.choice(pool)

    distractor_count = {"easy": 2, "medium": 3, "hard": 3}[difficulty_level]
    other_words = [w for w in pool if w["kazakh"] != target["kazakh"]]
    distractors = random.sample(other_words, k=min(distractor_count, len(other_words)))

    if game_type == "pick_the_picture":
        options = [target] + distractors
        random.shuffle(options)
        return {
            "game_type": game_type,
            "topic": topic,
            "difficulty_level": difficulty_level,
            "instruction_kazakh": f"'{target['kazakh']}' дегенді тап!",
            "instruction_ru": f"Найди картинку для слова '{target['kazakh']}' ({target['ru']}).",
            "correct_answer": target["kazakh"],
            "options": [
                {"word": o["kazakh"], "image": o["image"]} for o in options
            ],
        }

    if game_type == "guess_by_sound":
        return {
            "game_type": game_type,
            "topic": topic,
            "difficulty_level": difficulty_level,
            "instruction_kazakh": "Тыңда да, дұрыс сөзді тап!",
            "instruction_ru": "Послушай произношение и выбери правильное слово.",
            "focus_sound": target["focus_sound"],
            "audio_prompt_word": target["kazakh"],
            "correct_answer": target["kazakh"],
            "options": [w["kazakh"] for w in ([target] + distractors)],
        }

    # build_the_word
    letters = list(target["kazakh"].replace(" ", ""))
    scrambled = letters.copy()
    random.shuffle(scrambled)
    return {
        "game_type": game_type,
        "topic": topic,
        "difficulty_level": difficulty_level,
        "instruction_kazakh": "Әріптерден сөз құра!",
        "instruction_ru": f"Собери слово из букв: означает '{target['ru']}'.",
        "scrambled_letters": scrambled,
        "correct_answer": target["kazakh"],
        "hint_image": target["image"],
    }


# ---------------------------------------------------------------------------
# Tool 4: synthesize_voice_response
# ---------------------------------------------------------------------------
def handle_synthesize_voice_response(text_kazakh: str, emotional_tone: str) -> dict[str, Any]:
    tts_service = get_tts_service()
    result = tts_service.synthesize(text=text_kazakh, tone=emotional_tone)
    return result


# ---------------------------------------------------------------------------
# Диспетчер инструментов, используемый агентом.
# ---------------------------------------------------------------------------
def execute_tool(tool_name: str, tool_input: dict[str, Any], session: Session) -> dict[str, Any]:
    """Выполняет инструмент по имени и возвращает результат для Claude."""
    logger.info("Executing tool '%s' with input=%s", tool_name, tool_input)

    if tool_name == "get_student_progress":
        return handle_get_student_progress(session, student_id=int(tool_input["student_id"]))

    if tool_name == "update_vocabulary_mastery":
        return handle_update_vocabulary_mastery(
            session,
            student_id=int(tool_input["student_id"]),
            word=str(tool_input["word"]),
            is_correct=bool(tool_input["is_correct"]),
            topic=tool_input.get("topic"),
        )

    if tool_name == "generate_game_challenge":
        return handle_generate_game_challenge(
            topic=str(tool_input["topic"]),
            difficulty_level=str(tool_input["difficulty_level"]),
        )

    if tool_name == "synthesize_voice_response":
        return handle_synthesize_voice_response(
            text_kazakh=str(tool_input["text_kazakh"]),
            emotional_tone=str(tool_input["emotional_tone"]),
        )

    return {"error": f"Неизвестный инструмент: {tool_name}"}
