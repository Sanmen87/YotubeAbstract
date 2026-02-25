from __future__ import annotations

import logging
import time
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError

from app.core.config import settings

logger = logging.getLogger(__name__)


class VideoTooLongError(Exception):
    pass


class YouTubeForbiddenError(Exception):
    pass


class YouTubeInfoError(Exception):
    pass


def _base_ydl_opts() -> dict:
    """Base yt-dlp options shared by metadata and download attempts."""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 10,
        "fragment_retries": 10,
        "skip_unavailable_fragments": True,
        "extract_flat": False,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
            "Sec-Fetch-Mode": "navigate",
        },
    }
    if settings.ytdlp_cookies_file:
        opts["cookiefile"] = settings.ytdlp_cookies_file
    return opts


def fetch_video_info(video_url: str) -> dict:
    """Fetch video information with multiple fallback options."""
    client_configs = [
        {"extractor_args": {"youtube": {"player_client": ["android", "web"]}}},
        {"extractor_args": {"youtube": {"player_client": ["android"]}}},
        {"extractor_args": {"youtube": {"player_client": ["web"]}}},
        {"extractor_args": {"youtube": {"player_client": ["ios"]}}},
        {"extractor_args": {"youtube": {"player_client": ["tv_embedded"]}}},
        {},
    ]
    format_configs = [{"format": "bestaudio/best"}, {}]

    last_error: Exception | None = None

    for client_conf in client_configs:
        for format_conf in format_configs:
            try:
                ydl_opts = {
                    **_base_ydl_opts(),
                    "skip_download": True,
                    **client_conf,
                    **format_conf,
                }
                if not format_conf:
                    ydl_opts.pop("format", None)

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=False)
                    if info and info.get("title"):
                        logger.info(
                            "Successfully fetched video info",
                            extra={"title": info.get("title"), "duration": info.get("duration")},
                        )
                        return info
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Failed to fetch info",
                    extra={"error": str(exc), "client": str(client_conf), "format": str(format_conf)},
                )
                time.sleep(0.5)

    try:
        simple_opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
        with yt_dlp.YoutubeDL(simple_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if info:
                return info
    except Exception as exc:
        last_error = exc

    if last_error:
        raise YouTubeInfoError(f"Failed to fetch video info after multiple attempts: {last_error}") from last_error
    raise YouTubeInfoError(f"Failed to fetch video info for {video_url}")


def download_audio(video_url: str, output_dir: Path) -> tuple[Path, int]:
    """Download best available audio with multiple fallbacks and return (file_path, duration_sec)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    info = fetch_video_info(video_url)

    duration = int(info.get("duration") or 0)
    if duration > settings.max_video_seconds:
        raise VideoTooLongError(
            f"Video is too long ({duration // 60} min). Maximum allowed is {settings.max_video_minutes} min."
        )

    outtmpl = str(output_dir / "source.%(ext)s")
    # Ordered from preferred quality/client to broad fallback.
    attempt_options = [
        {
            **_base_ydl_opts(),
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
            "outtmpl": outtmpl,
            "extractor_args": {"youtube": {"player_client": ["android"]}},
            "geo_bypass": True,
            "geo_bypass_country": "US",
        },
        {
            **_base_ydl_opts(),
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
            "outtmpl": outtmpl,
            "extractor_args": {"youtube": {"player_client": ["web"]}},
            "geo_bypass": True,
            "geo_bypass_country": "US",
        },
        {
            **_base_ydl_opts(),
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
            "outtmpl": outtmpl,
            "geo_bypass": True,
            "geo_bypass_country": "US",
        },
        {
            **_base_ydl_opts(),
            "format": "bestaudio",
            "outtmpl": outtmpl,
            "geo_bypass": True,
            "geo_bypass_country": "US",
        },
        {
            **_base_ydl_opts(),
            "format": "bestaudio[protocol!=dash]/bestaudio",
            "outtmpl": outtmpl,
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            "geo_bypass": True,
            "geo_bypass_country": "US",
        },
    ]

    last_error: Exception | None = None
    downloaded_file: Path | None = None
    for idx, ydl_opts in enumerate(attempt_options, start=1):
        try:
            if idx > 1:
                time.sleep(2)
            logger.info(
                "Attempting audio download",
                extra={
                    "attempt": idx,
                    "format": ydl_opts.get("format"),
                    "client": ydl_opts.get("extractor_args", {}).get("youtube", {}).get("player_client", ["default"]),
                    "video_url": video_url,
                },
            )
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

            files = list(output_dir.glob("source.*"))
            if files:
                downloaded_file = files[0]
                logger.info(
                    "Successfully downloaded audio",
                    extra={"attempt": idx, "path": str(downloaded_file)},
                )
                break
            raise RuntimeError("File not found after download")
        except DownloadError as exc:
            last_error = exc
            logger.warning(
                "Audio download attempt failed",
                extra={
                    "attempt": idx,
                    "video_url": video_url,
                    "error": str(exc),
                    "format": ydl_opts.get("format"),
                },
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Unexpected error on audio download attempt",
                extra={"attempt": idx, "video_url": video_url, "error": str(exc)},
            )

    if not downloaded_file:
        error_str = str(last_error) if last_error else ""
        if "HTTP Error 403" in error_str:
            raise YouTubeForbiddenError(
                "YouTube blocked direct download (HTTP 403). "
                "Set YTDLP_COOKIES_FILE with browser-exported cookies (Netscape format)."
            ) from last_error

        if "Requested format is not available" in error_str:
            try:
                list_opts = {
                    **_base_ydl_opts(),
                    "listformats": True,
                }
                with yt_dlp.YoutubeDL(list_opts) as ydl:
                    ydl.extract_info(video_url, download=False)
            except Exception:
                pass

        raise RuntimeError(
            f"Audio download failed after {len(attempt_options)} attempts. Last error: {last_error}"
        ) from last_error

    logger.info("Audio downloaded", extra={"path": str(downloaded_file), "duration": duration})
    return downloaded_file, duration
