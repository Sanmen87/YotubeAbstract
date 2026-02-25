from app.utils.validators import is_valid_youtube_url


def test_valid_watch_url() -> None:
    assert is_valid_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_valid_short_url() -> None:
    assert is_valid_youtube_url("https://youtu.be/dQw4w9WgXcQ")


def test_invalid_domain() -> None:
    assert not is_valid_youtube_url("https://example.com/watch?v=dQw4w9WgXcQ")


def test_invalid_missing_video_id() -> None:
    assert not is_valid_youtube_url("https://www.youtube.com/watch")
