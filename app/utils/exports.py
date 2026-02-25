from __future__ import annotations

from datetime import timedelta

from app.utils.chunking import TranscriptSegment


def build_summary_markdown(task_id: int, summary: str) -> str:
    return f"# Краткое резюме\n\nTask ID: {task_id}\n\n{summary.strip()}\n"


def build_outline_markdown(task_id: int, outline: str) -> str:
    return f"# Конспект лекции\n\nTask ID: {task_id}\n\n{outline.strip()}\n"


def build_transcript_markdown(task_id: int, transcript_text: str) -> str:
    body = transcript_text.strip() or "(Пустая транскрипция)"
    return f"# Полная транскрипция\n\nTask ID: {task_id}\n\n{body}\n"


def _format_srt_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    delta = timedelta(seconds=float(seconds))
    total_ms = int(delta.total_seconds() * 1000)
    hours = total_ms // 3_600_000
    minutes = (total_ms % 3_600_000) // 60_000
    secs = (total_ms % 60_000) // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(segments: list[TranscriptSegment]) -> str:
    if not segments:
        return ""

    lines: list[str] = []
    for idx, seg in enumerate(segments, start=1):
        text = seg.text.strip()
        if not text:
            continue
        lines.append(str(idx))
        lines.append(f"{_format_srt_ts(seg.start)} --> {_format_srt_ts(seg.end)}")
        lines.append(text)
        lines.append("")

    return "\n".join(lines).strip() + "\n"
