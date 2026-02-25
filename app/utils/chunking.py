from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


def chunk_segments_by_minutes(segments: list[TranscriptSegment], minutes: int = 10) -> list[list[TranscriptSegment]]:
    if not segments:
        return []

    max_seconds = minutes * 60
    chunks: list[list[TranscriptSegment]] = []
    current: list[TranscriptSegment] = []
    chunk_start = segments[0].start

    for segment in segments:
        if current and (segment.end - chunk_start) > max_seconds:
            chunks.append(current)
            current = [segment]
            chunk_start = segment.start
        else:
            current.append(segment)

    if current:
        chunks.append(current)

    return chunks


def join_segment_text(segments: list[TranscriptSegment]) -> str:
    return " ".join(item.text.strip() for item in segments if item.text.strip())
