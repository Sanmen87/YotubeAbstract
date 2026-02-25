from __future__ import annotations

from io import BytesIO

import requests

from app.core.config import settings


def send_message(chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)


def send_document_bytes(
    chat_id: int,
    *,
    filename: str,
    content: bytes,
    caption: str | None = None,
    content_type: str = "text/plain",
) -> None:
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendDocument"
    file_obj = BytesIO(content)
    files = {"document": (filename, file_obj, content_type)}
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    requests.post(url, data=data, files=files, timeout=60)
