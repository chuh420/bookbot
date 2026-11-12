import csv
import io
import re
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..config import Business, Settings, pick
from ..db import Database, Row
from ..texts import fmt_day, money, t
from ..ui import (
    Button,
    admin_card,
    calendar,
    date_range_title,
    day_bounds,
    esc,
    from_ts,
    horizon,
    kb,
    log,
    now,
    parse_moment,
    parse_ymd,
    row_card,
    show,
    time_grid,
    ts,
)
from .client import clean_phone, pre, show_services

router = Router()
router.message.filter(F.chat.type == "private")

WHO_RE = re.compile(r"^(.*?)[\s,;]*(\+?\d[\d\s\-()]{5,}\d)\s*$", re.S)


class IsAdmin(Filter):
    async def __call__(self, event: Message | CallbackQuery, settings: Settings) -> bool:
        user = event.from_user
        return user is not None and user.id in settings.admins


class RelayReply(Filter):
    async def __call__(self, m: Message, db: Database) -> bool | dict[str, int]:
        if m.reply_to_message is None:
            return False
        target = await db.relay_target(m.chat.id, m.reply_to_message.message_id)
        return {"target": target} if target else False


class Manual(StatesGroup):
    who = State()


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def status_key(row: Row, now_value: int) -> str:
    if row["status"] == "active" and row["end_ts"] <= now_value:
        return "status_done"
    return f"status_{row['status']}"


async def day_text(db: Database, biz: Business, lang: str, day: date) -> tuple[str, list[Row]]:
    low, high = day_bounds(day, biz)
    bookings = await db.bookings_between(ts(low), ts(high))
    offs = await db.time_off_between(ts(low), ts(high))
    lines = [f"<b>{fmt_day(lang, day)}</b>"]
    staff_ids = list(biz.staff) + sorted({r["staff_id"] for r in bookings} - set(biz.staff))
    for staff_id in staff_ids:
        items: list[tuple[int, str]] = []
        for r in bookings:
            if r["staff_id"] != staff_id:
                continue
            start, end = from_ts(r["start_ts"], biz), from_ts(r["end_ts"], biz)
            marks = (" ✓" if r["confirmed"] else "") + (" ✍" if r["source"] == "admin" else "")
            who = f"{esc(r['client_name'] or '—')} {esc(r['client_phone'] or '')}".strip()
            items.append((r["start_ts"], f"{start:%H:%M}–{end:%H:%M} {esc(biz.service_name(r['service_id'], lang))} · {who}{marks}"))
        for off in offs:
            if off["staff_id"] != staff_id:
                continue
            start = max(from_ts(off["start_ts"], biz), low)
            end = min(from_ts(off["end_ts"], biz), high)
            end_label = "24:00" if end == high else f"{end:%H:%M}"
            items.append((off["start_ts"], f"🔒 {start:%H:%M}–{end_label} {t(lang, 'adm_closed')}"))
        if items:
            lines.append(f"\n<u>{esc(biz.staff_name(staff_id, lang))}</u>")
            lines += [text for _, text in sorted(items)]
    if len(lines) == 1:
        lines.append(t(lang, "adm_day_empty"))
    return "\n".join(lines), bookings


async def send_day(m: Message, db: Database, biz: Business, lang: str, day: date) -> None:
    text, bookings = await day_text(db, biz, lang, day)
    rows: list[list[Button]] = []
    for r in bookings:
        label = f"{from_ts(r['start_ts'], biz):%H:%M} {biz.staff_name(r['staff_id'], lang)} · {r['client_name'] or '—'}"
        rows.append([(label[:60], f"ab:{r['id']}")])
    if rows:
        text += "\n\n" + t(lang, "adm_pick")
    await m.answer(text, reply_markup=kb(rows) if rows else None)


@router.message(RelayReply())
async def on_reply(m: Message, bot: Bot, db: Database, lang: str, target: int) -> None:
    client = await db.client_by_tg(target)
    client_lang = client["lang"] if client else "ru"
    try:
        await bot.send_message(target, t(client_lang, "support_reply"))
        await m.copy_to(target)
    except TelegramAPIError as e:
        log.warning("cannot deliver reply to %s: %s", target, e)
        await m.reply(t(lang, "adm_reply_failed"))
        return
    await m.reply(t(lang, "adm_reply_sent"))


@router.message(Command("admin"))
async def cmd_admin(m: Message, lang: str) -> None:
    await m.answer(t(lang, "adm_help"))


@router.message(Command("today"))
async def cmd_today(m: Message, db: Database, biz: Business, lang: str) -> None:
    await send_day(m, db, biz, lang, now(biz).date())


@router.message(Command("tomorrow"))
async def cmd_tomorrow(m: Message, db: Database, biz: Business, lang: str) -> None:
    await send_day(m, db, biz, lang, now(biz).date() + timedelta(days=1))


@router.message(Command("week"))
async def cmd_week(m: Message, db: Database, biz: Business, lang: str) -> None:
    today = now(biz).date()
    parts = [(await day_text(db, biz, lang, today + timedelta(days=i)))[0] for i in range(7)]
    text = "\n\n".join(parts)
    for start in range(0, len(text), 3800):
        await m.answer(text[start : start + 3800])


@router.callback_query(pre("ab", "ax", "an"))
async def on_booking(cb: CallbackQuery, bot: Bot, db: Database, biz: Business, lang: str) -> None:
    action, _, raw_id = (cb.data or "").partition(":")
    row = await db.booking(int(raw_id)) if raw_id.isdigit() else None
    if row is None:
        await cb.answer(t(lang, "not_found"), show_alert=True)
        return
    card = admin_card(biz, lang, row)
    if action == "ab":
        text = f"{card}\n{t(lang, status_key(row, ts(now(biz))))}"
        rows = []
        if row["status"] == "active":
            rows.append([(t(lang, "adm_btn_cancel"), f"ax:{row['id']}"), (t(lang, "adm_btn_noshow"), f"an:{row['id']}")])
        await show(cb, text, kb(rows) if rows else None)
        return
    if row["status"] != "active":
        await cb.answer(t(lang, "not_found"), show_alert=True)
        return
    if action == "an":
        await db.set_status(row["id"], "noshow")
        await show(cb, f"{card}\n\n{t(lang, 'adm_done_noshow')}")
        return
    await db.set_status(row["id"], "cancelled")
    await show(cb, f"{card}\n\n{t(lang, 'adm_done_cancel')}")
    if row["client_tg"]:
        client_lang = row["client_lang"]
        try:
            await bot.send_message(row["client_tg"], f"{t(client_lang, 'admin_cancelled')}\n\n{row_card(biz, client_lang, row)}")
        except TelegramAPIError as e:
            log.warning("cannot notify client %s: %s", row["client_tg"], e)


@router.message(Command("add"))
async def cmd_add(m: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await state.set_state(Manual.who)
    await m.answer(t(lang, "adm_add_ask"))


@router.message(Manual.who, F.text, ~F.text.startswith("/"))
async def on_who(m: Message, state: FSMContext, biz: Business, lang: str) -> None:
    match = WHO_RE.match(m.text or "")
    phone = clean_phone(match.group(2)) if match else None
    name = match.group(1).strip() if match else ""
    if not phone or not name:
        await m.answer(t(lang, "adm_add_bad"))
        return
    await state.set_state(None)
    await state.update_data(manual={"name": name[:60], "phone": phone})
    await show_services(m, "a", biz, lang, head=t(lang, "adm_add_for", name=esc(name[:60]), phone=esc(phone)) + "\n\n")


@router.message(Command("block"))
async def cmd_block(m: Message, biz: Business, lang: str) -> None:
    rows = [[(pick(s.names, lang), f"k:{s.id}")] for s in biz.staff.values()]
    await m.answer(t(lang, "adm_block_staff"), reply_markup=kb(rows))


def work_moments(biz: Business, staff_id: str, day: date) -> list[datetime]:
    hours = biz.staff[staff_id].hours.get(day.weekday())
    if hours is None:
        return []
    moment = datetime.combine(day, hours[0], biz.tz)
    end = datetime.combine(day, hours[1], biz.tz)
    result = []
    while moment <= end:
        result.append(moment)
        moment += timedelta(minutes=biz.rules.slot_minutes)
    if result[-1] != end:
        result.append(end)
    return result


@router.callback_query(pre("k"))
async def on_block(cb: CallbackQuery, db: Database, biz: Business, lang: str) -> None:
    parts = (cb.data or "").split(":")
    if len(parts) == 2:
        staff_id, step = parts[1], ""
    else:
        step, staff_id = parts[1], parts[2]
    if staff_id not in biz.staff:
        await cb.answer(t(lang, "not_found"), show_alert=True)
        return
    name = esc(biz.staff_name(staff_id, lang))
    if step == "":
        days = {day: day.weekday() in biz.staff[staff_id].hours for day in horizon(biz)}
        await show(cb, t(lang, "adm_block_date", staff=name) + "\n" + date_range_title(lang, days), calendar(f"k:d:{staff_id}", days, lang, []))
        return
    day = parse_ymd(parts[3])
    moments = work_moments(biz, staff_id, day)
    if not moments:
        await cb.answer(t(lang, "adm_day_off"), show_alert=True)
        return
    back = [[(t(lang, "btn_back"), f"k:{staff_id}")]]
    if step == "d":
        extra = [[(t(lang, "adm_block_whole"), f"k:s:{staff_id}:{parts[3]}:all")]] + back
        text = t(lang, "adm_block_start", staff=name, day=fmt_day(lang, day))
        await show(cb, text, time_grid(f"k:s:{staff_id}:{parts[3]}", moments[:-1], extra))
        return
    if step == "s" and parts[4] != "all":
        start = parse_moment(parts[3], parts[4], biz)
        later = [m for m in moments if m > start]
        text = t(lang, "adm_block_end", staff=name, day=fmt_day(lang, day), start=f"{start:%H:%M}")
        await show(cb, text, time_grid(f"k:e:{staff_id}:{parts[3]}:{parts[4]}", later, back))
        return
    if step == "s":
        start, end = day_bounds(day, biz)
        when = fmt_day(lang, day)
    elif step == "e" and len(parts) == 6:
        start = parse_moment(parts[3], parts[4], biz)
        end = parse_moment(parts[3], parts[5], biz)
        when = f"{fmt_day(lang, day)}, {start:%H:%M}–{end:%H:%M}"
    else:
        return
    if end <= start:
        return
    await db.add_time_off(staff_id, ts(start), ts(end))
    text = t(lang, "adm_block_done", staff=name, when=when)
    clash = await db.count_bookings(staff_id, ts(start), ts(end))
    if clash:
        text += "\n\n" + t(lang, "adm_block_warn", n=clash)
    await show(cb, text)


async def blocks_view(db: Database, biz: Business, lang: str) -> tuple[str, list[list[Button]]]:
    current = now(biz)
    offs = await db.time_off_between(ts(current), ts(current + timedelta(days=90)))
    if not offs:
        return t(lang, "adm_blocks_empty"), []
    rows = []
    for off in offs:
        start, end = from_ts(off["start_ts"], biz), from_ts(off["end_ts"], biz)
        whole = end - start >= timedelta(days=1)
        span = fmt_day(lang, start.date()) if whole else f"{fmt_day(lang, start.date())} {start:%H:%M}–{end:%H:%M}"
        rows.append([(f"🔓 {biz.staff_name(off['staff_id'], lang)} · {span}", f"kd:{off['id']}")])
    return t(lang, "adm_blocks_title"), rows


@router.message(Command("blocks"))
async def cmd_blocks(m: Message, db: Database, biz: Business, lang: str) -> None:
    text, rows = await blocks_view(db, biz, lang)
    await m.answer(text, reply_markup=kb(rows) if rows else None)


@router.callback_query(pre("kd"))
async def on_block_delete(cb: CallbackQuery, db: Database, biz: Business, lang: str) -> None:
    raw_id = (cb.data or "").partition(":")[2]
    if raw_id.isdigit():
        await db.delete_time_off(int(raw_id))
        await cb.answer(t(lang, "adm_block_deleted"))
    text, rows = await blocks_view(db, biz, lang)
    await show(cb, text, kb(rows) if rows else None)


@router.message(Command("export"))
async def cmd_export(m: Message, command: CommandObject, db: Database, biz: Business, lang: str) -> None:
    days = int(command.args) if command.args and command.args.strip().isdigit() else 30
    current = now(biz)
    start = current - timedelta(days=min(days, 3650))
    end = current + timedelta(days=biz.rules.horizon_days + 1)
    rows = await db.bookings_between(ts(start), ts(end), active_only=False)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "date", "start", "end", "staff", "service", "price", "client", "phone", "status", "confirmed", "source", "created"])
    for r in rows:
        begin, finish = from_ts(r["start_ts"], biz), from_ts(r["end_ts"], biz)
        service = biz.services.get(r["service_id"])
        writer.writerow(
            [
                r["id"],
                f"{begin:%Y-%m-%d}",
                f"{begin:%H:%M}",
                f"{finish:%H:%M}",
                biz.staff_name(r["staff_id"], lang),
                biz.service_name(r["service_id"], lang),
                service.price if service else "",
                r["client_name"] or "",
                r["client_phone"] or "",
                t(lang, status_key(r, ts(current))),
                int(r["confirmed"]),
                r["source"],
                f"{from_ts(r['created_ts'], biz):%Y-%m-%d %H:%M}",
            ]
        )
    data = buffer.getvalue().encode("utf-8-sig")
    caption = t(lang, "adm_export", start=f"{start:%d.%m.%Y}", end=f"{end:%d.%m.%Y}", n=len(rows))
    await m.answer_document(BufferedInputFile(data, f"bookings-{current:%Y%m%d}.csv"), caption=caption)


@router.message(Command("stats"))
async def cmd_stats(m: Message, db: Database, biz: Business, lang: str) -> None:
    current = now(biz)
    now_value = ts(current)

    async def period(days: int) -> tuple[dict[str, int], int, dict[str, int]]:
        rows = await db.bookings_between(ts(current - timedelta(days=days)), now_value, active_only=False)
        counts = {"status_done": 0, "status_cancelled": 0, "status_noshow": 0, "status_active": 0}
        revenue = 0
        by_staff: dict[str, int] = {}
        for r in rows:
            key = status_key(r, now_value)
            counts[key] = counts.get(key, 0) + 1
            if key == "status_done":
                service = biz.services.get(r["service_id"])
                revenue += service.price if service else 0
                by_staff[r["staff_id"]] = by_staff.get(r["staff_id"], 0) + 1
        return counts, revenue, by_staff

    week, week_money, _ = await period(7)
    month, month_money, by_staff = await period(30)
    upcoming = await db.upcoming_active(now_value, ts(current + timedelta(days=365)))
    staff_lines = [f"{esc(biz.staff_name(sid, lang))}: {n}" for sid, n in sorted(by_staff.items(), key=lambda kv: -kv[1])]
    await m.answer(
        t(
            lang,
            "adm_stats",
            w_done=week["status_done"],
            w_cancel=week["status_cancelled"],
            w_noshow=week["status_noshow"],
            w_money=money(week_money, biz.currency),
            m_done=month["status_done"],
            m_cancel=month["status_cancelled"],
            m_noshow=month["status_noshow"],
            m_money=money(month_money, biz.currency),
            upcoming=len(upcoming),
            by_staff="\n".join(staff_lines) or "—",
        )
    )
