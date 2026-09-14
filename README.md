# Balapan AI Tutor 🐤

[![Tests](https://github.com/hunter0404/balapan-ai-tutor/actions/workflows/tests.yml/badge.svg)](https://github.com/hunter0404/balapan-ai-tutor/actions/workflows/tests.yml)

Интерактивное приложение для изучения казахского языка первоклассниками
(6-7 лет) на базе агентного ИИ Claude (Anthropic) с Tool Use.

Персонаж-репетитор **«Балапан»** ведёт диалог на казахском языке короткими
и добрыми фразами, предлагает мини-игры (выбор картинки, угадай по звуку,
собери слово), отслеживает словарный прогресс ученика в базе данных и
озвучивает свои реплики через локальный TTS-движок (Piper / ISSAI).

## Возможности

- 🖥️ Веб-фронтенд для ребёнка (`/`) — выбор имени/возраста/темы, чат с
  персонажем, автопроигрывание озвучки, кликабельные мини-игры
- 🎤 Голосовой ввод ответа (Web Speech API, best-effort для `kk-KZ`) с
  автоматическим откатом на текстовое поле, если браузер его не поддерживает
- 🎙️ Диалог в реальном времени через WebSocket (`/ws/tutor/{student_id}`)
- 🧠 Агент на Claude с 4 инструментами (Tool Use / Function Calling):
  - `get_student_progress` — прогресс и слабые места ученика
  - `update_vocabulary_mastery` — фиксация результата попытки
  - `generate_game_challenge` — генерация мини-игры по теме и сложности
  - `synthesize_voice_response` — озвучка реплики персонажа
- 🗄️ Хранение прогресса в SQLite через SQLModel (SQLAlchemy + Pydantic)
- 🔊 Модуль TTS с безопасным fallback-режимом (работает и без установленного Piper)
- 🐳 Готов к запуску в Docker

## Тематика и звуки

Темы: цвета (colors), животные (animals), семья (family), счёт до 10
(numbers), приветствия (greetings), специфические казахские звуки (sounds:
ә, і, ң, ғ, ү, ұ, қ, ө, һ).

## Структура проекта

```
balapan-ai-tutor/
├── app/
│   ├── main.py              # FastAPI: REST + WebSocket + статика фронтенда
│   ├── config.py             # Настройки (Pydantic Settings)
│   ├── database.py           # SQLModel: Student, WordProgress, SessionLog
│   ├── agent/
│   │   ├── tutor_agent.py    # Класс TutorAgent + цикл Tool Use
│   │   └── prompts.py        # Системный промпт персонажа «Балапан»
│   ├── skills/
│   │   ├── definitions.py    # JSON-схемы инструментов для Claude
│   │   └── handlers.py       # Реализация инструментов + банк слов/игр
│   └── audio/
│       └── tts_service.py    # Piper/ISSAI TTS с fallback-заглушкой
├── frontend/
│   ├── index.html             # Детский интерфейс (выбор темы, чат, игры)
│   ├── style.css               # Крупные кнопки, яркие цвета, адаптивная вёрстка
│   └── app.js                  # Логика чата, озвучки и игровых заданий
├── tests/
│   └── test_agent.py         # Юнит-тесты инструментов и цикла Tool Use
├── .github/
│   └── workflows/
│       └── tests.yml         # CI: pytest на каждый push/PR в main
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── LICENSE
```

## Быстрый старт (локально)

1. Установите Python 3.11+ и создайте виртуальное окружение:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Скопируйте `.env.example` в `.env` и укажите свой ключ Anthropic:

```bash
cp .env.example .env
```

Откройте `.env` и заполните `ANTHROPIC_API_KEY` своим ключом с
[console.anthropic.com](https://console.anthropic.com/).

3. Запустите сервер разработки:

```bash
uvicorn app.main:app --reload --port 8000
```

Открой `http://localhost:8000` — там сразу детский веб-интерфейс
(фронтенд отдаётся тем же FastAPI-сервером статически). API и документация
Swagger доступны на `http://localhost:8000/docs`.

## Запуск через Docker

```bash
cp .env.example .env
docker compose up --build
```

Сервис поднимется на `http://localhost:8000`, каталоги `./data` (SQLite +
кэш аудио) и `./models` (модель Piper) монтируются как volume, чтобы данные
сохранялись между перезапусками контейнера.

## Пример использования API

Создать ученика:

```bash
curl -X POST http://localhost:8000/students \
  -H "Content-Type: application/json" \
  -d '{"name": "Айым", "age": 7, "class_name": "1А"}'
```

Начать урок (агент сам проверит прогресс и поздоровается):

```bash
curl -X POST http://localhost:8000/lessons/start \
  -H "Content-Type: application/json" \
  -d '{"student_id": 1, "topic": "colors"}'
```

Продолжить диалог:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"student_id": 1, "message": "қызыл"}'
```

Реалтайм-диалог через WebSocket: подключитесь к `ws://localhost:8000/ws/tutor/1`
и отправляйте `{"message": "текст ребёнка"}`.

## Локальный синтез речи (Piper / ISSAI)

По умолчанию сервис пытается использовать бинарник [Piper](https://github.com/rhasspy/piper)
с моделью казахского языка ISSAI (`PIPER_MODEL_PATH`). Если бинарник или
модель не найдены в окружении, сервис автоматически переключается в режим
заглушки: пишет подробный лог и возвращает путь к тихому placeholder-файлу,
не прерывая работу агента — это удобно для разработки без установленной
модели синтеза речи.

Чтобы включить настоящий синтез, установите Piper и укажите пути в `.env`:

```bash
TTS_ENGINE=piper
PIPER_BINARY_PATH=/usr/local/bin/piper
PIPER_MODEL_PATH=./models/kk_KZ-issai-medium.onnx
```

## Тесты

```bash
pytest -v
```

Тесты покрывают все 4 инструмента агента (включая граничные случаи —
неизвестный ученик, некорректная тема, ограничение шкалы mastery 0-100) и
цикл Tool Use `TutorAgent` с замоканным Anthropic API (без реальных
сетевых запросов).

## Лицензия

[MIT](LICENSE)
