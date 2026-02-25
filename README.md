# YouTube Transcript Telegram Bot (Docker, Python 3.11)

Production-ready MVP scaffold for Telegram bot:
- User sends YouTube URL
- Worker downloads audio (`yt-dlp` + `ffmpeg`)
- ASR with `faster-whisper` on CPU (`int8`)
- LLM summarization + lecture outline via OpenAI API
- Stores tasks/results in PostgreSQL
- Uses Celery + Redis queues
- Input can be RU/EN/AR, final LLM output is always in Russian
- Result is delivered as files (`.md`) plus optional subtitles file (`.srt` with timestamps)

## Stack
- Python 3.11
- aiogram (polling)
- Celery + Redis
- PostgreSQL + SQLAlchemy + Alembic
- yt-dlp + ffmpeg
- faster-whisper (CPU)
- OpenAI SDK

## File Map
- `docker-compose.yml`: services (`bot`, `worker`, `migrate`, `postgres`, `redis`)
- `Dockerfile`: base runtime image for bot/worker
- `.env.example`: all configuration variables with descriptions
- `app/bot/main.py`: Telegram handlers (`/start`, `/help`, `/status`, URL intake)
- `app/worker/celery_app.py`: Celery config and queue routing
- `app/worker/tasks.py`: async pipeline (download -> ASR -> LLM -> finalize)
- `app/services/youtube.py`: YouTube metadata/audio download with fallbacks
- `app/services/asr.py`: ffmpeg conversion + faster-whisper transcription
- `app/services/llm.py`: OpenAI map-reduce summarization
- `app/services/telegram_notify.py`: Telegram sendMessage/sendDocument helpers
- `app/db/models.py`: SQLAlchemy models (`Task`, `Result`)
- `app/db/repositories.py`: DB operations (create/update/upsert/status)
- `alembic/versions/*.py`: DB migrations
- `app/utils/exports.py`: markdown and subtitles (`.srt`) builders
- `tests/*`: minimal tests for URL validation and chunking

## Environment Variables
Use `.env` (copy from `.env.example`):

```env
TELEGRAM_BOT_TOKEN=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/app
REDIS_URL=redis://redis:6379/0
MAX_VIDEO_MINUTES=60
WHISPER_MODEL_SIZE=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
LOG_LEVEL=INFO
ALLOWED_TELEGRAM_USER_IDS=123456789,987654321
YTDLP_COOKIES_FILE=/data/cookies.txt
```

## Run
```bash
cp .env.example .env
# fill TELEGRAM_BOT_TOKEN + OPENAI_API_KEY
docker compose up --build
```

Services:
- `bot`: Telegram polling bot
- `worker`: Celery worker (queues: asr/llm/default), preloads Whisper model at startup
- `postgres`
- `redis`

Persistent model cache:
- Whisper/Hugging Face cache is mounted to `./data/hf_cache` (host) -> `/root/.cache/huggingface` (worker)
- This avoids re-downloading model files after container restarts/rebuilds

## Bot Commands
- `/start`
- `/help`
- `/status <task_id>`

## Pipeline
1. Bot validates URL and creates `Task`
2. Celery chain:
   - `download_audio_task`
   - `transcribe_audio_task`
   - `summarize_transcript_task`
   - `finalize_task`
3. Result saved to `Result`, user notified by Telegram
4. Bot sends result files:
   - `task_<id>_summary.md`
   - `task_<id>_outline.md`
   - `task_<id>_transcript.md`
   - `task_<id>_subtitles.srt` (if segments available)
5. Temp files removed from `/tmp/youtube_lmm/<task_id>`

## Limits and Behavior
- Max video duration enforced by `MAX_VIDEO_MINUTES` (default 60)
- Input language can be RU / EN / AR, but summary and outline are always generated in Russian
- Basic retries configured for download/transcribe/summarize tasks
- Bot access is restricted to IDs from `ALLOWED_TELEGRAM_USER_IDS` (comma-separated Telegram user IDs)
- Idempotency:
  - completed tasks are not re-processed
  - result uses upsert by `task_id`

## Database
Alembic migration is executed on container startup:
- `alembic upgrade head`

Models:
- `Task(id, user_id, video_url, status, created_at, updated_at, error, language, duration_sec)`
- `Result(task_id, transcript_text, subtitles_srt, summary, outline, created_at, updated_at)`

## Tests
Run locally:
```bash
pytest -q
```

Included minimal tests:
- YouTube URL validation
- transcript chunking utility

## Notes
- This is MVP polling mode, no web UI.
- For heavy production load, split workers by queue into separate services.
- On worker startup, Whisper model is preloaded (and downloaded on first run), reducing latency of the first ASR task.
- Whisper device is configurable via `WHISPER_DEVICE` (`cpu` by default, `cuda` for GPU).
- If YouTube returns `403 Forbidden` for some videos, provide browser-exported cookies via `YTDLP_COOKIES_FILE` mounted into container.
  The project mounts `./data` (host) to `/data` (container), so default path is `/data/cookies.txt`.
  For `403`, task is marked as `failed` immediately with a clear error message (without useless retries).
- If `WHISPER_DEVICE=cuda` is set but CUDA is unavailable, worker falls back to CPU automatically.

### How To Add cookies.txt (recommended for 403 issues)
1. Install a browser extension that exports cookies in Netscape format (e.g. `Get cookies.txt` for Chrome/Firefox).
2. Sign in to your YouTube account in browser.
3. Export cookies to `cookies.txt` (Netscape format).
4. Put the file into project folder `./data/cookies.txt`.
5. Set env variable in `.env`:
   - `YTDLP_COOKIES_FILE=/data/cookies.txt`

---

# YouTube Telegram-бот с транскрипцией (Docker, Python 3.11)

Production-ready MVP каркас для Telegram-бота:
- Пользователь отправляет ссылку YouTube
- Воркер скачивает аудио (`yt-dlp` + `ffmpeg`)
- ASR через `faster-whisper` на CPU (`int8`)
- LLM делает краткое резюме и структурированный конспект через OpenAI API
- Задачи и результаты сохраняются в PostgreSQL
- Очереди через Celery + Redis
- Вход может быть RU/EN/AR, итоговый текст всегда на русском
- Результат отправляется файлами (`.md`) и опциональным файлом субтитров (`.srt` с таймкодами)

## Стек
- Python 3.11
- aiogram (polling)
- Celery + Redis
- PostgreSQL + SQLAlchemy + Alembic
- yt-dlp + ffmpeg
- faster-whisper (CPU)
- OpenAI SDK

## Карта файлов
- `docker-compose.yml`: сервисы (`bot`, `worker`, `migrate`, `postgres`, `redis`)
- `Dockerfile`: базовый runtime-образ для bot/worker
- `.env.example`: все переменные конфигурации с комментариями
- `app/bot/main.py`: обработчики Telegram (`/start`, `/help`, `/status`, приём URL)
- `app/worker/celery_app.py`: конфиг Celery и роутинг очередей
- `app/worker/tasks.py`: асинхронный pipeline (download -> ASR -> LLM -> finalize)
- `app/services/youtube.py`: получение метаданных/скачивание аудио с fallback-логикой
- `app/services/asr.py`: конвертация ffmpeg + транскрибация faster-whisper
- `app/services/llm.py`: map-reduce суммаризация через OpenAI
- `app/services/telegram_notify.py`: отправка сообщений/файлов в Telegram
- `app/db/models.py`: SQLAlchemy-модели (`Task`, `Result`)
- `app/db/repositories.py`: операции с БД (create/update/upsert/status)
- `alembic/versions/*.py`: миграции БД
- `app/utils/exports.py`: генерация markdown и субтитров (`.srt`)
- `tests/*`: минимальные тесты валидации URL и чанкинга

## Переменные окружения
Используйте `.env` (скопируйте из `.env.example`):

```env
TELEGRAM_BOT_TOKEN=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/app
REDIS_URL=redis://redis:6379/0
MAX_VIDEO_MINUTES=60
WHISPER_MODEL_SIZE=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
LOG_LEVEL=INFO
ALLOWED_TELEGRAM_USER_IDS=123456789,987654321
YTDLP_COOKIES_FILE=/data/cookies.txt
```

## Запуск
```bash
cp .env.example .env
# заполните TELEGRAM_BOT_TOKEN и OPENAI_API_KEY
docker compose up --build
```

Сервисы:
- `bot`: Telegram-бот (polling)
- `worker`: Celery worker (очереди: asr/llm/default), preload Whisper-модели при старте
- `postgres`
- `redis`

Постоянный кэш модели:
- Кэш Whisper/Hugging Face смонтирован `./data/hf_cache` (host) -> `/root/.cache/huggingface` (worker)
- Это предотвращает повторную загрузку модели после перезапуска/пересборки контейнеров

## Команды бота
- `/start`
- `/help`
- `/status <task_id>`

## Pipeline
1. Бот валидирует URL и создаёт `Task`
2. Celery chain:
   - `download_audio_task`
   - `transcribe_audio_task`
   - `summarize_transcript_task`
   - `finalize_task`
3. Результат сохраняется в `Result`, пользователю отправляется сообщение в Telegram
4. Бот отправляет файлы результата:
   - `task_<id>_summary.md`
   - `task_<id>_outline.md`
   - `task_<id>_transcript.md`
   - `task_<id>_subtitles.srt` (если есть сегменты)
5. Временные файлы удаляются из `/tmp/youtube_lmm/<task_id>`

## Ограничения и поведение
- Лимит длительности видео задаётся `MAX_VIDEO_MINUTES` (по умолчанию 60)
- Входной язык может быть RU / EN / AR, но резюме и конспект всегда генерируются на русском
- Для download/transcribe/summarize включены базовые ретраи
- Доступ к боту ограничен списком ID в `ALLOWED_TELEGRAM_USER_IDS` (через запятую)
- Идемпотентность:
  - completed-задачи не перерабатываются повторно
  - результат сохраняется через upsert по `task_id`

## База данных
Миграции Alembic выполняются при старте контейнера:
- `alembic upgrade head`

Модели:
- `Task(id, user_id, video_url, status, created_at, updated_at, error, language, duration_sec)`
- `Result(task_id, transcript_text, subtitles_srt, summary, outline, created_at, updated_at)`

## Тесты
Локальный запуск:
```bash
pytest -q
```

Минимальные тесты включают:
- валидацию YouTube URL
- разбиение транскрипта на чанки

## Примечания
- Это MVP в polling-режиме, без web UI.
- Для высокой нагрузки лучше разнести воркеры по очередям в отдельные сервисы.
- При старте worker делается preload Whisper-модели (и загрузка модели при первом запуске).
- Устройство Whisper настраивается через `WHISPER_DEVICE` (`cpu` по умолчанию, `cuda` для GPU).
- Если YouTube отдаёт `403 Forbidden` для части видео, используйте экспорт cookies через `YTDLP_COOKIES_FILE`.
  В проекте уже есть mount `./data` (host) -> `/data` (container), поэтому путь по умолчанию `/data/cookies.txt`.
  Для `403` задача переводится в `failed` с понятной ошибкой без бесполезных ретраев.
- Если указан `WHISPER_DEVICE=cuda`, но CUDA недоступна, worker автоматически переключится на CPU.

### Как добавить cookies.txt (рекомендуется при 403)
1. Установите расширение браузера для экспорта cookies в Netscape-формате (например, `Get cookies.txt` для Chrome/Firefox).
2. Войдите в YouTube в браузере.
3. Экспортируйте cookies в файл `cookies.txt` (формат Netscape).
4. Положите файл в `./data/cookies.txt`.
5. Укажите в `.env`:
   - `YTDLP_COOKIES_FILE=/data/cookies.txt`
