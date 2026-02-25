from __future__ import annotations

from urllib.parse import parse_qs, urlparse

_VALID_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
}


def is_valid_youtube_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    if parsed.netloc not in _VALID_HOSTS:
        return False

    if parsed.netloc == "youtu.be":
        return bool(parsed.path.strip("/"))

    if parsed.path == "/watch":
        query = parse_qs(parsed.query)
        return bool(query.get("v"))

    return parsed.path.startswith("/shorts/") or parsed.path.startswith("/live/")
