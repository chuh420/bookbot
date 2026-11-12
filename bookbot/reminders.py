import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from .config import Business
from .db import Database
from .texts import fmt_minutes, t
from .ui import kb, log, now, row_card, ts

INTERVAL = 30


def due_reminders(start_ts: int, created_ts: int, reminded: int, hours: tuple[int, ...], now_value: int) -> tuple[int, int | None]:
    bits = 0
    send = None
    for index, hour in enumerate(hours):
        bit = 1 << index
        due = start_ts - hour * 3600
        if reminded & bit or now_value < due:
            continue
        bits |= bit
        if created_ts <= due:
            send = index
    return bits, send


async def tick(bot: Bot, db: Database, biz: Business) -> None:
    hours = biz.rules.remind_hours
    if not hours:
        return
    now_value = ts(now(biz))
    for row in await db.upcoming_active(now_value, now_value + max(hours) * 3600):
        bits, send = due_reminders(row["start_ts"], row["created_ts"], row["reminded"], hours, now_value)
        if not bits:
            continue
        await db.mark_reminded(row["id"], bits)
        if send is None or not row["client_tg"]:
            continue
        lang = row["client_lang"]
        card = row_card(biz, lang, row)
        minutes_left = max(1, round((row["start_ts"] - now_value) / 60))
        can_cancel = minutes_left > biz.rules.cancel_minutes
        markup = None
        if send == 0 and can_cancel:
            text = f"{t(lang, 'remind_first')}\n\n{card}"
            if not row["confirmed"]:
                text += f"\n\n{t(lang, 'remind_ask')}"
                markup = kb([[(t(lang, "btn_coming"), f"rc:{row['id']}"), (t(lang, "btn_cancel_booking"), f"c:{row['id']}")]])
        else:
            planned = hours[send] * 60
            shown = planned if abs(minutes_left - planned) <= 10 else minutes_left
            text = f"{t(lang, 'remind_second', time=fmt_minutes(lang, shown))}\n\n{card}"
        try:
            await bot.send_message(row["client_tg"], text, reply_markup=markup)
        except TelegramAPIError as e:
            log.warning("cannot remind client %s: %s", row["client_tg"], e)


async def run(bot: Bot, db: Database, biz: Business) -> None:
    while True:
        try:
            await tick(bot, db, biz)
        except Exception:
            log.exception("reminder tick failed")
        await asyncio.sleep(INTERVAL)
