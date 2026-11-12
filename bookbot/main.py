import asyncio
import logging
import os
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat, CallbackQuery, ErrorEvent, TelegramObject

from . import reminders
from .config import LANGS, Business, ConfigError, Settings, load_business, load_settings
from .db import Database
from .handlers import admin, client
from .texts import guess_lang
from .ui import log

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

CLIENT_COMMANDS = {
    "ru": [("start", "меню"), ("lang", "язык")],
    "kk": [("start", "мәзір"), ("lang", "тіл")],
    "en": [("start", "menu"), ("lang", "language")],
}
ADMIN_COMMANDS = [
    ("start", "menu"),
    ("today", "bookings for today"),
    ("tomorrow", "bookings for tomorrow"),
    ("week", "bookings for 7 days"),
    ("add", "book a client by hand"),
    ("block", "close a specialist's time"),
    ("blocks", "closed time"),
    ("export", "CSV export"),
    ("stats", "statistics"),
    ("admin", "admin help"),
    ("lang", "language"),
]


class ClientMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if user is None or user.is_bot:
            return None
        row = await data["db"].ensure_client(user.id, guess_lang(user.language_code))
        data["client"] = row
        data["lang"] = row["lang"]
        return await handler(event, data)


class AnswerMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        try:
            return await handler(event, data)
        finally:
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer()
                except TelegramAPIError:
                    pass


def commands(pairs: list[tuple[str, str]]) -> list[BotCommand]:
    return [BotCommand(command=name, description=text) for name, text in pairs]


async def set_commands(bot: Bot, settings: Settings) -> None:
    await bot.set_my_commands(commands(CLIENT_COMMANDS["ru"]))
    for lang in LANGS:
        await bot.set_my_commands(commands(CLIENT_COMMANDS[lang]), language_code=lang)
    for admin_id in settings.admins:
        try:
            await bot.set_my_commands(commands(ADMIN_COMMANDS), scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramAPIError as e:
            log.warning("cannot set admin commands for %s: %s", admin_id, e)


async def on_error(event: ErrorEvent) -> bool:
    log.exception("update failed", exc_info=event.exception)
    return True


def build_dispatcher(db: Database, biz: Business, settings: Settings) -> Dispatcher:
    dp = Dispatcher(db=db, biz=biz, settings=settings)
    dp.message.outer_middleware(ClientMiddleware())
    dp.callback_query.outer_middleware(ClientMiddleware())
    dp.callback_query.middleware(AnswerMiddleware())
    dp.include_router(admin.router)
    dp.include_router(client.router)
    dp.errors.register(on_error)
    return dp


async def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings()
        biz: Business = load_business(settings.business_file)
    except ConfigError as e:
        log.error("%s", e)
        raise SystemExit(2) from None
    db = await Database.open(settings.db_file)
    bot = Bot(
        settings.token,
        session=AiohttpSession(proxy=settings.proxy) if settings.proxy else None,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    dp = build_dispatcher(db, biz, settings)

    tasks: list[asyncio.Task] = []

    async def on_startup() -> None:
        await set_commands(bot, settings)
        tasks.append(asyncio.create_task(reminders.run(bot, db, biz)))
        me = await bot.me()
        log.info("started as @%s for %s", me.username, biz.name)

    async def on_shutdown() -> None:
        for task in tasks:
            task.cancel()
        await db.close()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
