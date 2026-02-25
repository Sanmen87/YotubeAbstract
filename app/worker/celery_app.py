from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery("youtube_lmm", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_routes={
        "app.worker.tasks.download_audio_task": {"queue": "asr"},
        "app.worker.tasks.transcribe_audio_task": {"queue": "asr"},
        "app.worker.tasks.summarize_transcript_task": {"queue": "llm"},
        "app.worker.tasks.finalize_task": {"queue": "default"},
    },
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    timezone="UTC",
)

celery_app.autodiscover_tasks(["app.worker"])
