from app.utils.chunking import TranscriptSegment, chunk_segments_by_minutes, join_segment_text


def test_chunk_by_minutes() -> None:
    segments = [
        TranscriptSegment(start=0, end=100, text="part1"),
        TranscriptSegment(start=101, end=400, text="part2"),
        TranscriptSegment(start=800, end=900, text="part3"),
    ]

    chunks = chunk_segments_by_minutes(segments, minutes=5)
    assert len(chunks) == 2
    assert len(chunks[0]) == 2
    assert len(chunks[1]) == 1


def test_join_segment_text() -> None:
    segments = [TranscriptSegment(start=0, end=1, text=" hello "), TranscriptSegment(start=2, end=3, text="world")]
    assert join_segment_text(segments) == "hello world"
