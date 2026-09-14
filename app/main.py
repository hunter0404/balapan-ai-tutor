"""FastAPI-приложение: REST API, WebSocket и веб-фронтенд ИИ-репетитора."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.agent.tutor_agent import AgentTurnResult, TutorAgent, get_tutor_agent
from app.config import get_settings
from app.database import Student, get_session, init_db
from app.skills.handlers import VALID_TOPICS, handle_get_student_progress

settings = get_settings()

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
os.makedirs(settings.tts_output_dir, exist_ok=True)

app = FastAPI(
    title=settings.app_name,
    description="Интерактивный ИИ-репетитор казахского языка для первоклассников.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Статика фронтенда (HTML/CSS/JS) и кэш озвученных реплик персонажа.
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/audio", StaticFiles(directory=settings.tts_output_dir), name="audio")


@app.get("/", include_in_schema=False)
def serve_frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info("%s запущен. Доступные темы: %s", settings.app_name, VALID_TOPICS)


# ---------------------------------------------------------------------------
# Pydantic-схемы запросов/ответов
# ---------------------------------------------------------------------------
class StudentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Имя ученика")
    age: int = Field(default=7, ge=6, le=8)
    class_name: str = Field(default="1")
    preferred_topic: str | None = Field(default=None)


class StudentResponse(BaseModel):
    id: int
    name: str
    age: int
    class_name: str
    preferred_topic: str | None


class ChatRequest(BaseModel):
    student_id: int
    message: str = Field(..., min_length=1, max_length=500)
    conversation_id: str | None = Field(
        default=None, description="Если не указан, используется 'student-{student_id}'."
    )


class LessonStartRequest(BaseModel):
    student_id: int
    topic: str | None = Field(default=None, description="colors|animals|family|numbers|greetings|sounds")


class ChatResponse(BaseModel):
    reply_text: str
    audio_path: str | None
    tool_calls: list[dict]


def _conversation_id_for(student_id: int, explicit: str | None) -> str:
    return explicit or f"student-{student_id}"


# ---------------------------------------------------------------------------
# REST: ученики
# ---------------------------------------------------------------------------
@app.post("/students", response_model=StudentResponse, status_code=201)
def create_student(payload: StudentCreateRequest, session: Session = Depends(get_session)) -> Student:
    student = Student(
        name=payload.name,
        age=payload.age,
        class_name=payload.class_name,
        preferred_topic=payload.preferred_topic,
    )
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


@app.get("/students/{student_id}", response_model=StudentResponse)
def get_student(student_id: int, session: Session = Depends(get_session)) -> Student:
    student = session.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Ученик не найден")
    return student


@app.get("/students")
def list_students(session: Session = Depends(get_session)) -> list[Student]:
    return list(session.exec(select(Student)).all())


@app.get("/students/{student_id}/progress")
def get_progress(student_id: int, session: Session = Depends(get_session)) -> dict:
    result = handle_get_student_progress(session, student_id=student_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# REST: диалог с агентом
# ---------------------------------------------------------------------------
@app.post("/lessons/start", response_model=ChatResponse)
def start_lesson(
    payload: LessonStartRequest,
    session: Session = Depends(get_session),
    agent: TutorAgent = Depends(get_tutor_agent),
) -> ChatResponse:
    student = session.get(Student, payload.student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Ученик не найден")

    conversation_id = _conversation_id_for(payload.student_id, None)
    agent.reset_conversation(conversation_id)
    result: AgentTurnResult = agent.start_lesson(
        session=session,
        conversation_id=conversation_id,
        student_id=payload.student_id,
        student_name=student.name,
        topic=payload.topic,
    )
    return ChatResponse(
        reply_text=result.reply_text, audio_path=result.audio_path, tool_calls=result.tool_calls
    )


@app.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    session: Session = Depends(get_session),
    agent: TutorAgent = Depends(get_tutor_agent),
) -> ChatResponse:
    student = session.get(Student, payload.student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Ученик не найден")

    conversation_id = _conversation_id_for(payload.student_id, payload.conversation_id)
    result: AgentTurnResult = agent.send_message(
        session=session,
        conversation_id=conversation_id,
        student_id=payload.student_id,
        user_text=payload.message,
    )
    return ChatResponse(
        reply_text=result.reply_text, audio_path=result.audio_path, tool_calls=result.tool_calls
    )


# ---------------------------------------------------------------------------
# WebSocket: реалтайм-диалог
# ---------------------------------------------------------------------------
@app.websocket("/ws/tutor/{student_id}")
async def websocket_tutor(websocket: WebSocket, student_id: int) -> None:
    """Реалтайм-канал диалога. Клиент шлёт `{"message": "..."}`,
    сервер отвечает `{"reply_text": ..., "audio_path": ..., "tool_calls": [...]}`.
    """
    await websocket.accept()
    agent = get_tutor_agent()
    conversation_id = _conversation_id_for(student_id, None)

    try:
        with _session_scope() as session:
            student = session.get(Student, student_id)
            if student is None:
                await websocket.send_json({"error": "Ученик не найден"})
                await websocket.close(code=4404)
                return

            while True:
                payload = await websocket.receive_json()
                user_text = str(payload.get("message", "")).strip()
                if not user_text:
                    await websocket.send_json({"error": "Пустое сообщение"})
                    continue

                result = agent.send_message(
                    session=session,
                    conversation_id=conversation_id,
                    student_id=student_id,
                    user_text=user_text,
                )
                await websocket.send_json(
                    {
                        "reply_text": result.reply_text,
                        "audio_path": result.audio_path,
                        "tool_calls": result.tool_calls,
                    }
                )
    except WebSocketDisconnect:
        logger.info("WebSocket отключён: student_id=%s", student_id)


def _session_scope() -> Session:
    from app.database import engine

    return Session(engine)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok", "app": settings.app_name}
