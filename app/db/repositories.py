from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Result, Task

TERMINAL_STATUSES = {"completed", "failed"}


class TaskRepository:
    @staticmethod
    def create_task(session: Session, user_id: int, video_url: str) -> Task:
        task = Task(user_id=user_id, video_url=video_url, status="created")
        session.add(task)
        session.commit()
        session.refresh(task)
        return task

    @staticmethod
    def get_task(session: Session, task_id: int) -> Task | None:
        return session.get(Task, task_id)

    @staticmethod
    def set_status(
        session: Session,
        task_id: int,
        status: str,
        *,
        error: str | None = None,
        language: str | None = None,
        duration_sec: int | None = None,
    ) -> Task | None:
        task = session.get(Task, task_id)
        if not task:
            return None

        if task.status in TERMINAL_STATUSES and status not in TERMINAL_STATUSES:
            return task

        task.status = status
        if error is not None:
            task.error = error
        if language is not None:
            task.language = language
        if duration_sec is not None:
            task.duration_sec = duration_sec
        session.commit()
        session.refresh(task)
        return task

    @staticmethod
    def upsert_result(
        session: Session,
        task_id: int,
        transcript_text: str,
        summary: str,
        outline: str,
        subtitles_srt: str | None = None,
    ) -> Result:
        result = session.get(Result, task_id)
        if result:
            result.transcript_text = transcript_text
            result.summary = summary
            result.outline = outline
            result.subtitles_srt = subtitles_srt
        else:
            result = Result(
                task_id=task_id,
                transcript_text=transcript_text,
                summary=summary,
                outline=outline,
                subtitles_srt=subtitles_srt,
            )
            session.add(result)
        session.commit()
        session.refresh(result)
        return result

    @staticmethod
    def get_task_with_result(session: Session, task_id: int) -> Task | None:
        query = select(Task).options(selectinload(Task.result)).where(Task.id == task_id)
        return session.scalars(query).first()
