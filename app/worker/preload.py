from __future__ import annotations

from app.core.logging import setup_logging
from app.services.asr import preload_whisper_model


def main() -> None:
    setup_logging()
    preload_whisper_model()


if __name__ == "__main__":
    main()
