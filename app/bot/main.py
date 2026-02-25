from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from celery import chain

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.repositories import TaskRepository
from app.db.session import get_session
from app.utils.exports import build_outline_markdown, build_summary_markdown, build_transcript_markdown
from app.utils.validators import is_valid_youtube_url
from app.worker.tasks import (
    download_audio_task,
    finalize_task,
    summarize_transcript_task,
    transcribe_audio_task,
)

setup_logging()
logger = logging.getLogger(__name__)
router = Router()


def is_user_allowed(user_id: int) -> bool:
    """Strict whitelist access: empty whitelist means deny all."""
    allowed = settings.allowed_telegram_user_ids
    return bool(allowed) and user_id in allowed


async def reject_unauthorized_message(message: Message) -> None:
    await message.answer("Access denied.")


async def reject_unauthorized_callback(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer("Access denied.")
    await callback.answer()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else message.chat.id
    if not is_user_allowed(user_id):
        await reject_unauthorized_message(message)
        return

    text = (
        "Send a YouTube URL.\n"
        "I will download audio, transcribe it, and return summary + lecture outline.\n"
        "Supported languages: RU / EN / AR."
    )
    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else message.chat.id
    if not is_user_allowed(user_id):
        await reject_unauthorized_message(message)
        return

    await message.answer(
        "Commands:\n"
        "/start\n"
        "/help\n"
        "/status <task_id>\n\n"
        "Restrictions:\n"
        f"- Max video length: {settings.max_video_minutes} minutes"
    )


@router.message(Command("status"))
async def cmd_status(message: Message, command: CommandObject) -> None:
    """Return current task status and send result files when completed."""
    requester_id = message.from_user.id if message.from_user else message.chat.id
    if not is_user_allowed(requester_id):
        await reject_unauthorized_message(message)
        return

    if not command.args:
        await message.answer("Usage: /status <task_id>")
        return

    try:
        task_id = int(command.args.strip())
    except ValueError:
        await message.answer("task_id must be an integer.")
        return

    with get_session() as session:
        task = TaskRepository.get_task_with_result(session, task_id)

    if not task:
        await message.answer(f"Task {task_id} not found.")
        return

    if task.user_id != requester_id:
        await message.answer("This task does not belong to you.")
        return

    if task.status != "completed":
        await message.answer(f"Task {task.id} status: {task.status}")
        return

    result = task.result
    if not result:
        await message.answer(f"Task {task.id} completed but result missing.")
        return

    await message.answer(f"Task {task.id} status: completed. Sending files.")
    await message.answer_document(
        BufferedInputFile(
            build_summary_markdown(task.id, result.summary).encode("utf-8"),
            filename=f"task_{task.id}_summary.md",
        )
    )
    await message.answer_document(
        BufferedInputFile(
            build_outline_markdown(task.id, result.outline).encode("utf-8"),
            filename=f"task_{task.id}_outline.md",
        )
    )
    await message.answer_document(
        BufferedInputFile(
            build_transcript_markdown(task.id, result.transcript_text).encode("utf-8"),
            filename=f"task_{task.id}_transcript.md",
        )
    )
    if result.subtitles_srt:
        await message.answer_document(
            BufferedInputFile(result.subtitles_srt.encode("utf-8"), filename=f"task_{task.id}_subtitles.srt")
        )


@router.callback_query(F.data.startswith("status:"))
async def status_callback(callback: CallbackQuery) -> None:
    requester_id = callback.from_user.id if callback.from_user else 0
    if not is_user_allowed(requester_id):
        await reject_unauthorized_callback(callback)
        return

    if not callback.data:
        return
    task_id = int(callback.data.split(":", 1)[1])

    with get_session() as session:
        task = TaskRepository.get_task_with_result(session, task_id)

    if not task:
        await callback.message.answer(f"Task {task_id} not found.")
        await callback.answer()
        return

    if task.user_id != requester_id:
        await callback.message.answer("This task does not belong to you.")
        await callback.answer()
        return

    await callback.message.answer(f"Task {task.id} status: {task.status}")
    await callback.answer()


@router.message(F.text)
async def handle_message(message: Message) -> None:
    """Accept YouTube URL, create task, enqueue Celery chain."""
    user_id = message.from_user.id if message.from_user else message.chat.id
    if not is_user_allowed(user_id):
        await reject_unauthorized_message(message)
        return

    raw = (message.text or "").strip()
    if not is_valid_youtube_url(raw):
        await message.answer("Please send a valid YouTube URL.")
        return

    with get_session() as session:
        task = TaskRepository.create_task(session, user_id=user_id, video_url=raw)

    workflow = chain(
        download_audio_task.s(task.id),
        transcribe_audio_task.s(),
        summarize_transcript_task.s(),
        finalize_task.s(),
    )
    workflow.apply_async()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Check status", callback_data=f"status:{task.id}")]]
    )

    await message.answer(
        f"Accepted. Task ID: {task.id}.\nUse /status {task.id} to check progress.",
        reply_markup=keyboard,
    )


async def main() -> None:
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    logger.info("Bot started in polling mode")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
