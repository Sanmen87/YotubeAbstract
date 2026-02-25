from __future__ import annotations

import logging
import subprocess
import time
import wave
from collections.abc import Callable
from threading import Lock
from pathlib import Path

from faster_whisper import WhisperModel

from app.core.config import settings
from app.utils.chunking import TranscriptSegment

logger = logging.getLogger(__name__)
_model_lock = Lock()
_model: WhisperModel | None = None


def get_whisper_model() -> WhisperModel:
    """Lazily initialize and cache a single Whisper model instance per process."""
    global _model
    if _model is not None:
        return _model

    with _model_lock:
        if _model is None:
            logger.info(
                "Loading Whisper model",
                extra={
                    "model_size": settings.whisper_model_size,
                    "compute_type": settings.whisper_compute_type,
                    "device": settings.whisper_device,
                },
            )
            try:
                _model = WhisperModel(
                    settings.whisper_model_size,
                    device=settings.whisper_device,
                    compute_type=settings.whisper_compute_type,
                )
            except Exception:
                if settings.whisper_device != "cpu":
                    logger.exception(
                        "Failed to initialize Whisper on requested device, fallback to CPU",
                        extra={"requested_device": settings.whisper_device},
                    )
                    _model = WhisperModel(
                        settings.whisper_model_size,
                        device="cpu",
                        compute_type=settings.whisper_compute_type,
                    )
                else:
                    raise
    return _model


def preload_whisper_model() -> None:
    """Warm up model at worker startup to reduce first-task latency."""
    _ = get_whisper_model()
    logger.info("Whisper model is ready")


def convert_to_wav_16k_mono(input_path: Path, output_path: Path) -> Path:
    """Convert any input audio/video file to Whisper-friendly WAV 16k mono."""
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {completed.stderr}")
    return output_path


def _get_wav_duration_seconds(audio_path: Path) -> float:
    with wave.open(str(audio_path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        if rate <= 0:
            return 0.0
        return frames / float(rate)


def transcribe_audio_file(
    audio_path: Path,
    *,
    progress_callback: Callable[[dict], None] | None = None,
) -> tuple[str, str, list[TranscriptSegment]]:
    """Run ASR and optionally emit progress snapshots while iterating segments."""
    model = get_whisper_model()
    total_sec = _get_wav_duration_seconds(audio_path)
    started_at = time.monotonic()
    next_progress_mark_sec = 120.0
    segments, info = model.transcribe(str(audio_path), beam_size=5)

    parsed_segments: list[TranscriptSegment] = []
    transcript_parts: list[str] = []

    for segment in segments:
        text = segment.text.strip()
        parsed_segments.append(TranscriptSegment(start=segment.start, end=segment.end, text=text))
        if text:
            transcript_parts.append(text)
        processed_sec = float(segment.end)

        if processed_sec >= next_progress_mark_sec:
            elapsed_sec = time.monotonic() - started_at
            progress = {
                "processed_sec": processed_sec,
                "total_sec": total_sec,
                "percent": (processed_sec / total_sec * 100.0) if total_sec > 0 else 0.0,
                "segments": len(parsed_segments),
                "elapsed_sec": elapsed_sec,
            }
            if progress_callback:
                progress_callback(progress)
            else:
                logger.info(
                    "ASR progress: %.1f%% (%ds/%ds), segments=%d, elapsed=%ds",
                    round(progress["percent"], 1),
                    int(processed_sec),
                    int(total_sec),
                    len(parsed_segments),
                    int(elapsed_sec),
                )
            next_progress_mark_sec += 120.0

    transcript = " ".join(transcript_parts)
    detected_language = info.language if info and info.language else "unknown"
    total_elapsed = time.monotonic() - started_at

    logger.info(
        "ASR completed",
        extra={
            "audio_path": str(audio_path),
            "language": detected_language,
            "segments": len(parsed_segments),
            "elapsed_sec": int(total_elapsed),
            "audio_duration_sec": int(total_sec),
        },
    )

    return transcript, detected_language, parsed_segments
