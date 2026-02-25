from __future__ import annotations

from openai import OpenAI

from app.core.config import settings
from app.utils.chunking import TranscriptSegment, chunk_segments_by_minutes, join_segment_text

_client = OpenAI(api_key=settings.openai_api_key)


def _ask_model(prompt: str) -> str:
    """SDK-compatible OpenAI call: Responses API when available, Chat Completions otherwise."""
    if hasattr(_client, "responses"):
        response = _client.responses.create(
            model=settings.openai_model,
            input=prompt,
        )
        output_text = getattr(response, "output_text", "") or ""
        return output_text.strip()

    completion = _client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
    )
    content = completion.choices[0].message.content if completion.choices else ""
    return (content or "").strip()


def summarize_with_map_reduce(transcript: str, segments: list[TranscriptSegment]) -> tuple[str, str]:
    """Chunk transcript, summarize each chunk, then build final summary and outline in Russian."""
    if not transcript.strip():
        return "No speech detected.", "No lecture outline available."

    chunks = chunk_segments_by_minutes(segments, minutes=10)
    if not chunks:
        chunks = [[TranscriptSegment(start=0, end=0, text=transcript)]]

    partial_summaries: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        chunk_text = join_segment_text(chunk)
        prompt = (
            "Ты редактор технических конспектов. Сделай плотный конспект фрагмента: 6-10 содержательных пунктов, "
            "без воды и без общих фраз. Каждый пункт должен содержать смысл (что именно, зачем, последствия, пример). "
            "Обязательно сохраняй конкретику: сервисы, параметры, ограничения, риски, шаги, решения. "
            "Пиши строго на русском языке. Формат: маркдаун-список.\n\n"
            f"Chunk #{idx}:\n{chunk_text}"
        )
        partial_summaries.append(_ask_model(prompt))

    merged = "\n\n".join(partial_summaries)

    final_summary_prompt = (
        "Сделай финальное резюме по частичным конспектам (1-2 абзаца). "
        "Только ключевой смысл, без повторов и без вводных фраз. "
        "Пиши строго на русском языке.\n\n"
        f"{merged}"
    )

    outline_prompt = (
        "Сделай структурированный конспект лекции по частичным конспектам. "
        "Это должен быть не план глав, а содержательный материал. "
        "Требования:\n"
        "1) Формат markdown.\n"
        "2) Заголовок: '# <Тема> - Краткий конспект'.\n"
        "3) Далее 5-9 разделов с названиями уровня '##'.\n"
        "4) В каждом разделе 3-6 буллетов с фактической сутью (не общие фразы).\n"
        "5) Включай: определения, зачем это нужно, практические шаги, риски/ошибки, ограничения, примеры.\n"
        "6) Избегай пустых формулировок типа 'обсуждается', 'рассматривается'.\n"
        "7) Если есть сценарий/кейс (например TinyFlix), вынеси его в отдельный раздел с выводами.\n"
        "8) Язык строго русский.\n\n"
        f"{merged}"
    )

    final_summary = _ask_model(final_summary_prompt)
    outline = _ask_model(outline_prompt)

    return final_summary, outline
