import html
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Callable

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .config import ANY, Business, Service, Settings, Staff, pick
from .db import Database, Row
from .slots import free_slots
from .texts import WEEKDAYS, fmt_day, fmt_dt, fmt_minutes, money, t

log = logging.getLogger("bookbot")

Button = tuple[str, str]
NOOP = "noop"


def kb(rows: list[list[Button]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=data) for text, data in row] for row in rows if row]
    )


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


def parse_ymd(text: str) -> date:
    return datetime.strptime(text, "%Y%m%d").date()


def hm(moment: datetime | time) -> str:
    return moment.strftime("%H%M")


def parse_moment(day_text: str, time_text: str, biz: Business) -> datetime:
    return datetime.combine(parse_ymd(day_text), datetime.strptime(time_text, "%H%M").time(), biz.tz)


def ts(moment: datetime) -> int:
    return int(moment.timestamp())


def from_ts(value: int, biz: Business) -> datetime:
    return datetime.fromtimestamp(value, biz.tz)


def now(biz: Business) -> datetime:
    return datetime.now(biz.tz)


def day_bounds(day: date, biz: Business) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, biz.tz)
    return start, start + timedelta(days=1)


async def show(target: CallbackQuery | Message, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    if isinstance(target, Message):
        await target.answer(text, reply_markup=markup)
        return
    message = target.message
    if isinstance(message, Message):
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except TelegramBadRequest as e:
            if "not modified" in str(e):
                return
    if target.bot is not None:
        await target.bot.send_message(target.from_user.id, text, reply_markup=markup)


def menu_view(biz: Business, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    rows = [
        [(t(lang, "btn_book"), "b")],
        [(t(lang, "btn_my"), "my")],
        [(t(lang, "btn_services"), "info:svc"), (t(lang, "btn_address"), "info:addr")],
        [(t(lang, "btn_support"), "sup")],
        [(t(lang, "btn_lang"), "lang")],
    ]
    return t(lang, "menu", name=esc(biz.name)), kb(rows)


def service_line(biz: Business, lang: str, service: Service) -> str:
    return f"{pick(service.names, lang)} · {fmt_minutes(lang, service.minutes)} · {money(service.price, biz.currency)}"


def booking_card(biz: Business, lang: str, service_id: str, staff_id: str, start: datetime) -> str:
    service = biz.services.get(service_id)
    lines = [f"📅 <b>{fmt_dt(lang, start)}</b>"]
    if service is not None:
        lines.append(f"✂️ {esc(service_line(biz, lang, service))}")
    else:
        lines.append(f"✂️ {esc(service_id)}")
    lines.append(f"👤 {t(lang, 'master')}: {esc(biz.staff_name(staff_id, lang))}")
    return "\n".join(lines)


def row_card(biz: Business, lang: str, row: Row) -> str:
    return booking_card(biz, lang, row["service_id"], row["staff_id"], from_ts(row["start_ts"], biz))


def client_line(row: Row) -> str:
    name = esc(row["client_name"] or "—")
    phone = esc(row["client_phone"] or "")
    if row["client_tg"]:
        name = f'<a href="tg://user?id={row["client_tg"]}">{name}</a>'
    return f"🙍 {name} {phone}".rstrip()


def admin_card(biz: Business, lang: str, row: Row) -> str:
    return row_card(biz, lang, row) + "\n" + client_line(row)


def calendar(prefix: str, days: dict[date, bool], lang: str, extra: list[list[Button]]) -> InlineKeyboardMarkup:
    names = WEEKDAYS.get(lang, WEEKDAYS["ru"])
    rows: list[list[Button]] = [[(name, NOOP) for name in names]]
    first, last = min(days), max(days)
    cursor = first - timedelta(days=first.weekday())
    while cursor <= last:
        week: list[Button] = []
        for _ in range(7):
            if days.get(cursor):
                week.append((str(cursor.day), f"{prefix}:{ymd(cursor)}"))
            elif cursor in days:
                week.append(("·", NOOP))
            else:
                week.append((" ", NOOP))
            cursor += timedelta(days=1)
        rows.append(week)
    return kb(rows + extra)


def time_grid(prefix: str, moments: list[datetime], extra: list[list[Button]], width: int = 4) -> InlineKeyboardMarkup:
    buttons = [(f"{m:%H:%M}", f"{prefix}:{hm(m)}") for m in moments]
    rows = [buttons[i : i + width] for i in range(0, len(buttons), width)]
    return kb(rows + extra)


def date_range_title(lang: str, days: dict[date, bool]) -> str:
    return f"{fmt_day(lang, min(days))} – {fmt_day(lang, max(days))}"


def candidates(biz: Business, service_id: str, staff_key: str) -> list[Staff]:
    offered = biz.staff_for(service_id)
    if staff_key == ANY:
        return offered
    return [s for s in offered if s.id == staff_key]


def horizon(biz: Business) -> list[date]:
    today = now(biz).date()
    return [today + timedelta(days=i) for i in range(biz.rules.horizon_days + 1)]


async def range_slots(
    db: Database,
    biz: Business,
    minutes: int,
    staff_list: list[Staff],
    days: list[date],
    earliest: datetime,
    exclude: int | None = None,
) -> dict[date, dict[datetime, list[str]]]:
    if not days or not staff_list:
        return {day: {} for day in days}
    low, _ = day_bounds(min(days), biz)
    _, high = day_bounds(max(days), biz)
    busy: dict[str, list[tuple[datetime, datetime]]] = {}
    for row in await db.busy([s.id for s in staff_list], ts(low), ts(high), exclude):
        busy.setdefault(row["staff_id"], []).append((from_ts(row["start_ts"], biz), from_ts(row["end_ts"], biz)))
    result: dict[date, dict[datetime, list[str]]] = {}
    for day in days:
        found: dict[datetime, list[str]] = {}
        for staff in staff_list:
            for start in free_slots(staff, minutes, day, busy.get(staff.id, []), earliest, biz.rules.slot_minutes, biz.tz):
                found.setdefault(start, []).append(staff.id)
        result[day] = dict(sorted(found.items()))
    return result


async def notify_admins(
    bot: Bot,
    settings: Settings,
    db: Database,
    biz: Business,
    key: str,
    row: Row,
    extra: Callable[[str], str] | None = None,
    skip: int | None = None,
) -> None:
    for admin_id in settings.admins:
        if admin_id == skip:
            continue
        admin = await db.client_by_tg(admin_id)
        lang = admin["lang"] if admin else "ru"
        text = f"{t(lang, key)}\n\n{admin_card(biz, lang, row)}"
        if extra is not None:
            text += "\n" + extra(lang)
        try:
            await bot.send_message(admin_id, text)
        except TelegramAPIError as e:
            log.warning("cannot notify admin %s: %s", admin_id, e)
