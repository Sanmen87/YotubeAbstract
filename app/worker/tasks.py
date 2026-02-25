from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from celery import Task

from app.core.logging import setup_logging
from app.db.repositories import TaskRepository
from app.db.session import get_session
from app.services.asr import convert_to_wav_16k_mono, transcribe_audio_file
from app.services.llm import summarize_with_map_reduce
from app.services.telegram_notify import send_document_bytes, send_message
from app.services.youtube import VideoTooLongError, YouTubeForbiddenError, YouTubeInfoError, download_audio
from app.utils.chunking import TranscriptSegment
from app.utils.exports import build_outline_markdown, build_srt, build_summary_markdown, build_transcript_markdown
from app.worker.celery_app import celery_app

setup_logging()
logger = logging.getLogger(__name__)

TEMP_ROOT = Path("/tmp/youtube_lmm")


class DBTask(Task):
    """Celery task base that synchronizes failures to DB and notifies user."""
    def on_failure(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: Any) -> None:
        task_pk = _extract_task_id(args)
        if task_pk is None:
            return

        message = str(exc)
        with get_session() as session:
            task = TaskRepository.set_status(session, task_pk, "failed", error=message)
            if task:
                try:
                    send_message(task.user_id, f"Task {task_pk} failed: {message}")
                except Exception:
                    logger.exception("Failed to send failure notification", extra={"task_id": task_pk})

        cleanup_temp_dir(task_pk)


def _extract_task_id(args: tuple) -> int | None:
    if not args:
        return None

    payload = args[0]
    if isinstance(payload, int):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("task_id"), int):
        return payload["task_id"]
    return None


def task_temp_dir(task_id: int) -> Path:
    return TEMP_ROOT / str(task_id)


def cleanup_temp_dir(task_id: int) -> None:
    shutil.rmtree(task_temp_dir(task_id), ignore_errors=True)


@celery_app.task(
    bind=True,
    base=DBTask,
    name="app.worker.tasks.download_audio_task",
    autoretry_for=(RuntimeError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def download_audio_task(self, task_id: int) -> dict:
    """Stage 1: validate limits and download source audio from YouTube."""
    with get_session() as session:
        task = TaskRepository.get_task(session, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        if task.status == "completed":
            return {"task_id": task_id, "skip": True}
        TaskRepository.set_status(session, task_id, "downloading", error=None)

    tmp_dir = task_temp_dir(task_id)
    try:
        with get_session() as session:
            task = TaskRepository.get_task(session, task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            source_path, duration = download_audio(task.video_url, tmp_dir)
            TaskRepository.set_status(session, task_id, "downloaded", duration_sec=duration)
    except (VideoTooLongError, YouTubeForbiddenError, YouTubeInfoError) as exc:
        with get_session() as session:
            task = TaskRepository.set_status(session, task_id, "failed", error=str(exc))
            if task:
                try:
                    send_message(task.user_id, f"Task {task_id} rejected: {exc}")
                except Exception:
                    logger.exception("Failed to send rejection notification", extra={"task_id": task_id})
        cleanup_temp_dir(task_id)
        return {"task_id": task_id, "skip": True}

    return {"task_id": task_id, "source_path": str(source_path), "duration_sec": duration}


@celery_app.task(
    bind=True,
    base=DBTask,
    name="app.worker.tasks.transcribe_audio_task",
    autoretry_for=(RuntimeError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def transcribe_audio_task(self, payload: dict) -> dict:
    """Stage 2: convert media to WAV and run Whisper ASR with progress updates."""
    task_id = int(payload["task_id"])
    if payload.get("skip"):
        return payload

    with get_session() as session:
        TaskRepository.set_status(session, task_id, "transcribing", error=None)

    source_path = Path(payload["source_path"])
    wav_path = task_temp_dir(task_id) / "audio.wav"
    convert_to_wav_16k_mono(source_path, wav_path)

    def _progress_callback(progress: dict) -> None:
        self.update_state(
            state="PROGRESS",
            meta={
                "task_id": task_id,
                "stage": "transcribing",
                "processed_sec": int(progress["processed_sec"]),
                "total_sec": int(progress["total_sec"]),
                "percent": round(progress["percent"], 1),
                "segments": progress["segments"],
                "elapsed_sec": int(progress["elapsed_sec"]),
            },
        )
        logger.info(
            "Transcription progress: task=%d %.1f%% (%ds/%ds), segments=%d, elapsed=%ds",
            task_id,
            round(progress["percent"], 1),
            int(progress["processed_sec"]),
            int(progress["total_sec"]),
            progress["segments"],
            int(progress["elapsed_sec"]),
        )

    transcript_text, detected_language, segments = transcribe_audio_file(
        wav_path, progress_callback=_progress_callback
    )

    payload["transcript_text"] = transcript_text
    payload["language"] = detected_language
    payload["segments"] = [segment.__dict__ for segment in segments]

    with get_session() as session:
        TaskRepository.set_status(session, task_id, "transcribed", language=detected_language)

    return payload


@celery_app.task(
    bind=True,
    base=DBTask,
    name="app.worker.tasks.summarize_transcript_task",
    autoretry_for=(RuntimeError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def summarize_transcript_task(self, payload: dict) -> dict:
    """Stage 3: run OpenAI map-reduce summarization over transcript segments."""
    task_id = int(payload["task_id"])
    if payload.get("skip"):
        return payload

    with get_session() as session:
        TaskRepository.set_status(session, task_id, "summarizing", error=None)

    segments = [TranscriptSegment(**item) for item in payload.get("segments", [])]
    summary, outline = summarize_with_map_reduce(payload.get("transcript_text", ""), segments)

    payload["summary"] = summary
    payload["outline"] = outline

    return payload


@celery_app.task(bind=True, base=DBTask, name="app.worker.tasks.finalize_task")
def finalize_task(self, payload: dict) -> dict:
    """Stage 4: persist result, generate markdown/SRT files, send to Telegram, cleanup temp files."""
    task_id = int(payload["task_id"])
    if payload.get("skip"):
        return payload

    transcript_text = payload.get("transcript_text", "")
    summary = payload.get("summary", "")
    outline = payload.get("outline", "")
    segments = [TranscriptSegment(**item) for item in payload.get("segments", [])]
    subtitles_srt = build_srt(segments)

    with get_session() as session:
        task = TaskRepository.upsert_result(
            session,
            task_id,
            transcript_text,
            summary,
            outline,
            subtitles_srt=subtitles_srt or None,
        )
        task_parent = TaskRepository.set_status(session, task_id, "completed", error="")
        if task_parent:
            try:
                send_message(task_parent.user_id, f"Task {task_id} completed. Sending result files.")
                send_document_bytes(
                    task_parent.user_id,
                    filename=f"task_{task_id}_summary.md",
                    content=build_summary_markdown(task_id, task.summary).encode("utf-8"),
                    caption=f"Task {task_id}: summary",
                    content_type="text/markdown",
                )
                send_document_bytes(
                    task_parent.user_id,
                    filename=f"task_{task_id}_outline.md",
                    content=build_outline_markdown(task_id, task.outline).encode("utf-8"),
                    content_type="text/markdown",
                )
                send_document_bytes(
                    task_parent.user_id,
                    filename=f"task_{task_id}_transcript.md",
                    content=build_transcript_markdown(task_id, task.transcript_text).encode("utf-8"),
                    content_type="text/markdown",
                )
                if subtitles_srt.strip():
                    send_document_bytes(
                        task_parent.user_id,
                        filename=f"task_{task_id}_subtitles.srt",
                        content=subtitles_srt.encode("utf-8"),
                        content_type="application/x-subrip",
                    )
            except Exception:
                logger.exception("Failed to send result files", extra={"task_id": task_id})
                send_message(task_parent.user_id, f"Task {task_id} completed, but file delivery failed.")

    cleanup_temp_dir(task_id)
    return {"task_id": task_id, "status": "completed"}
