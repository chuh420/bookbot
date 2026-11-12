import re
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from ..config import ANY, LANGS, Business, Settings, pick
from ..db import Database, LimitReached, Row, SlotTaken
from ..slots import pick_staff
from ..texts import LANG_NAMES, fmt_day, fmt_dt, fmt_minutes, t
from ..ui import (
    NOOP,
    Button,
    admin_card,
    booking_card,
    calendar,
    candidates,
    date_range_title,
    day_bounds,
    esc,
    from_ts,
    horizon,
    kb,
    log,
    menu_view,
    notify_admins,
    now,
    parse_moment,
    parse_ymd,
    range_slots,
    row_card,
    service_line,
    show,
    time_grid,
    ts,
    ymd,
)

router = Router()
router.message.filter(F.chat.type == "private")

PHONE_RE = re.compile(r"^\+?\d{7,15}$")


class Contact(StatesGroup):
    name = State()
    phone = State()


class Support(StatesGroup):
    message = State()


def pre(*names: str):
    return lambda event: (event.data or "").split(":")[0] in names


def clean_phone(text: str) -> str | None:
    phone = re.sub(r"[\s\-()]", "", text)
    return phone if PHONE_RE.match(phone) else None


def menu_row(lang: str) -> list[Button]:
    return [(t(lang, "btn_menu"), "menu")]


def staff_label(biz: Business, lang: str, staff_key: str) -> str:
    return t(lang, "any_staff") if staff_key == ANY else esc(biz.staff_name(staff_key, lang))


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(m: Message, state: FSMContext, biz: Business, lang: str) -> None:
    await state.clear()
    text, markup = menu_view(biz, lang)
    await m.answer(text, reply_markup=markup)


@router.message(Command("lang"))
async def cmd_lang(m: Message, lang: str) -> None:
    await m.answer(t(lang, "lang_choose"), reply_markup=lang_keyboard())


def lang_keyboard() -> InlineKeyboardMarkup:
    return kb([[(LANG_NAMES[code], f"lang:{code}")] for code in LANGS])


@router.callback_query(F.data == NOOP)
async def on_noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data == "menu")
async def on_menu(cb: CallbackQuery, state: FSMContext, biz: Business, lang: str) -> None:
    await state.clear()
    await show(cb, *menu_view(biz, lang))


@router.callback_query(pre("lang"))
async def on_lang(cb: CallbackQuery, db: Database, biz: Business, client: Row, lang: str) -> None:
    code = (cb.data or "").partition(":")[2]
    if code not in LANGS:
        await show(cb, t(lang, "lang_choose"), lang_keyboard())
        return
    await db.set_lang(client["id"], code)
    await show(cb, *menu_view(biz, code))


@router.callback_query(pre("info"))
async def on_info(cb: CallbackQuery, biz: Business, lang: str) -> None:
    if cb.data == "info:svc":
        lines = [t(lang, "services_title"), ""]
        lines += [f"• {esc(service_line(biz, lang, s))}" for s in biz.services.values()]
        rows = [[(t(lang, "btn_book"), "b")], menu_row(lang)]
    else:
        lines = [f"<b>{esc(biz.name)}</b>", ""]
        if pick(biz.address, lang):
            lines.append(f"📍 {esc(pick(biz.address, lang))}")
        if biz.phone:
            lines.append(f"📞 {esc(biz.phone)}")
        if pick(biz.about, lang):
            lines += ["", esc(pick(biz.about, lang))]
        rows = [menu_row(lang)]
    await show(cb, "\n".join(lines), kb(rows))


async def show_services(cb: CallbackQuery | Message, kind: str, biz: Business, lang: str, head: str = "") -> None:
    rows = [[(service_line(biz, lang, s), f"{kind}:s:{s.id}")] for s in biz.services.values()]
    await show(cb, head + t(lang, "choose_service"), kb(rows + [menu_row(lang)]))


async def show_staff(cb: CallbackQuery, kind: str, service_id: str, db: Database, biz: Business, lang: str, lead: int) -> None:
    offered = biz.staff_for(service_id)
    if len(offered) == 1:
        await show_dates(cb, kind, service_id, offered[0].id, db, biz, lang, lead)
        return
    rows = [[(t(lang, "any_staff"), f"{kind}:m:{service_id}:{ANY}")]]
    rows += [[(pick(s.names, lang), f"{kind}:m:{service_id}:{s.id}")] for s in offered]
    rows.append([(t(lang, "btn_back"), kind)])
    await show(cb, t(lang, "choose_staff", service=esc(biz.service_name(service_id, lang))), kb(rows))


async def show_dates(
    cb: CallbackQuery, kind: str, service_id: str, staff_key: str, db: Database, biz: Business, lang: str, lead: int
) -> None:
    service = biz.services[service_id]
    back = f"{kind}:s:{service_id}" if len(biz.staff_for(service_id)) > 1 else kind
    slots = await range_slots(
        db, biz, service.minutes, candidates(biz, service_id, staff_key), horizon(biz), now(biz) + timedelta(minutes=lead)
    )
    days = {day: bool(found) for day, found in slots.items()}
    back_row = [[(t(lang, "btn_back"), back), (t(lang, "btn_menu"), "menu")]]
    if not any(days.values()):
        await show(cb, t(lang, "no_days", days=biz.rules.horizon_days), kb(back_row))
        return
    text = t(lang, "choose_date", service=esc(pick(service.names, lang)), staff=staff_label(biz, lang, staff_key))
    text += "\n" + date_range_title(lang, days)
    await show(cb, text, calendar(f"{kind}:d:{service_id}:{staff_key}", days, lang, back_row))


async def show_times(
    cb: CallbackQuery,
    kind: str,
    service_id: str,
    staff_key: str,
    day_text: str,
    db: Database,
    biz: Business,
    lang: str,
    lead: int,
) -> None:
    service = biz.services[service_id]
    day = parse_ymd(day_text)
    slots = await range_slots(
        db, biz, service.minutes, candidates(biz, service_id, staff_key), [day], now(biz) + timedelta(minutes=lead)
    )
    moments = list(slots[day])
    if not moments:
        await cb.answer(t(lang, "no_times"), show_alert=True)
        await show_dates(cb, kind, service_id, staff_key, db, biz, lang, lead)
        return
    text = t(
        lang,
        "choose_time",
        service=esc(pick(service.names, lang)),
        staff=staff_label(biz, lang, staff_key),
        day=fmt_day(lang, day),
    )
    back_row = [[(t(lang, "btn_back"), f"{kind}:m:{service_id}:{staff_key}"), (t(lang, "btn_menu"), "menu")]]
    await show(cb, text, time_grid(f"{kind}:t:{service_id}:{staff_key}:{day_text}", moments, back_row))


def confirm_view(
    kind: str, service_id: str, staff_id: str, start: datetime, biz: Business, lang: str, manual: dict | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    tail = f"{service_id}:{staff_id}:{ymd(start)}:{start:%H%M}"
    text = t(lang, "confirm_title") + "\n\n" + booking_card(biz, lang, service_id, staff_id, start)
    if manual:
        text += "\n\n" + t(lang, "adm_add_for", name=esc(manual["name"]), phone=esc(manual["phone"]))
    rows = [
        [(t(lang, "btn_confirm"), f"{kind}:ok:{tail}")],
        [(t(lang, "btn_back"), f"{kind}:d:{service_id}:{staff_id}:{ymd(start)}"), (t(lang, "btn_menu"), "menu")],
    ]
    return text, kb(rows)


@router.callback_query(pre("b", "a"))
async def on_wizard(
    cb: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db: Database,
    biz: Business,
    settings: Settings,
    client: Row,
    lang: str,
) -> None:
    parts = (cb.data or "").split(":")
    kind = parts[0]
    manual = kind == "a"
    if manual and cb.from_user.id not in settings.admins:
        return
    lead = 0 if manual else biz.rules.min_lead_minutes
    step = parts[1] if len(parts) > 1 else ""
    if step == "":
        await show_services(cb, kind, biz, lang)
        return
    service_id = parts[2] if len(parts) > 2 else ""
    staff_key = parts[3] if len(parts) > 3 else ""
    if service_id not in biz.services or (staff_key and not candidates(biz, service_id, staff_key)):
        await show_services(cb, kind, biz, lang)
        return
    if step == "s" and len(parts) == 3:
        await show_staff(cb, kind, service_id, db, biz, lang, lead)
    elif step == "m" and len(parts) == 4:
        await show_dates(cb, kind, service_id, staff_key, db, biz, lang, lead)
    elif step == "d" and len(parts) == 5:
        await show_times(cb, kind, service_id, staff_key, parts[4], db, biz, lang, lead)
    elif step in ("t", "ok") and len(parts) == 6:
        await on_slot(cb, state, bot, db, biz, settings, client, lang, kind, step, service_id, staff_key, parts[4], parts[5], lead)
    else:
        await show_services(cb, kind, biz, lang)


async def on_slot(
    cb: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db: Database,
    biz: Business,
    settings: Settings,
    client: Row,
    lang: str,
    kind: str,
    step: str,
    service_id: str,
    staff_key: str,
    day_text: str,
    time_text: str,
    lead: int,
) -> None:
    manual = kind == "a"
    service = biz.services[service_id]
    start = parse_moment(day_text, time_text, biz)
    slots = await range_slots(
        db, biz, service.minutes, candidates(biz, service_id, staff_key), [start.date()], now(biz) + timedelta(minutes=lead)
    )
    free = slots[start.date()].get(start)
    if not free:
        await cb.answer(t(lang, "slot_taken"), show_alert=True)
        await show_times(cb, kind, service_id, staff_key, day_text, db, biz, lang, lead)
        return
    staff_id = staff_key
    if staff_key == ANY:
        low, high = day_bounds(start.date(), biz)
        staff_id = pick_staff(free, await db.loads(ts(low), ts(high)))
    manual_data = (await state.get_data()).get("manual") if manual else None
    if manual and not manual_data:
        await show(cb, t(lang, "adm_add_ask"))
        return

    if step == "t":
        if not manual and not (client["name"] and client["phone"]):
            await state.update_data(draft=[service_id, staff_id, day_text, time_text])
            if client["name"]:
                await state.set_state(Contact.phone)
                await ask_phone(cb, lang)
            else:
                await state.set_state(Contact.name)
                if isinstance(cb.message, Message):
                    await state.update_data(prompt=cb.message.message_id)
                await ask_name(cb, lang)
            return
        await show(cb, *confirm_view(kind, service_id, staff_id, start, biz, lang, manual_data))
        return

    end = start + timedelta(minutes=service.minutes)
    try:
        if manual_data:
            client_id = await db.manual_client(manual_data["name"], manual_data["phone"])
            booking_id = await db.create_booking(client_id, service_id, staff_id, ts(start), ts(end), source="admin")
        else:
            booking_id = await db.create_booking(
                client["id"], service_id, staff_id, ts(start), ts(end), max_active=biz.rules.max_active
            )
    except SlotTaken:
        await cb.answer(t(lang, "slot_taken"), show_alert=True)
        await show_times(cb, kind, service_id, staff_key, day_text, db, biz, lang, lead)
        return
    except LimitReached:
        rows = [[(t(lang, "btn_my"), "my")], menu_row(lang)]
        await show(cb, t(lang, "limit_reached", n=biz.rules.max_active), kb(rows))
        return

    row = await db.booking(booking_id)
    assert row is not None
    if manual_data:
        await state.clear()
        await show(cb, t(lang, "adm_new_manual") + "\n\n" + admin_card(biz, lang, row))
        await notify_admins(bot, settings, db, biz, "adm_new_manual", row, skip=cb.from_user.id)
        return
    text = f"{t(lang, 'booked')}\n\n{row_card(biz, lang, row)}\n\n{t(lang, 'booked_hint')}"
    await show(cb, text, kb([[(t(lang, "btn_my"), "my")], menu_row(lang)]))
    await notify_admins(bot, settings, db, biz, "adm_new", row)


async def ask_name(cb: CallbackQuery, lang: str) -> None:
    rows = []
    if any(ch.isalpha() for ch in cb.from_user.first_name or ""):
        rows.append([(t(lang, "use_name", name=cb.from_user.first_name[:40]), "nm")])
    rows.append(menu_row(lang))
    await show(cb, t(lang, "ask_name"), kb(rows))


async def ask_phone(target: CallbackQuery | Message, lang: str) -> None:
    markup = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "send_contact"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    message = target.message if isinstance(target, CallbackQuery) else target
    if isinstance(target, CallbackQuery) and isinstance(message, Message):
        try:
            await message.delete()
        except TelegramAPIError:
            pass
    if isinstance(message, Message):
        await message.answer(t(lang, "ask_phone"), reply_markup=markup)


async def after_name(target: CallbackQuery | Message, state: FSMContext, client: Row, lang: str, biz: Business) -> None:
    if client["phone"]:
        await finish_contact(target, state, lang, biz)
        return
    await state.set_state(Contact.phone)
    await ask_phone(target, lang)


@router.callback_query(F.data == "nm", Contact.name)
async def on_use_name(cb: CallbackQuery, state: FSMContext, db: Database, biz: Business, client: Row, lang: str) -> None:
    await db.set_contact(client["id"], name=(cb.from_user.first_name or "")[:60])
    await after_name(cb, state, client, lang, biz)


@router.message(Contact.name)
async def on_name(m: Message, state: FSMContext, db: Database, biz: Business, client: Row, lang: str) -> None:
    name = (m.text or "").strip()
    if not name or len(name) > 60 or name.startswith("/"):
        await m.answer(t(lang, "bad_name"))
        return
    await db.set_contact(client["id"], name=name)
    prompt = (await state.get_data()).get("prompt")
    if prompt and m.bot is not None:
        try:
            await m.bot.edit_message_reply_markup(chat_id=m.chat.id, message_id=prompt, reply_markup=None)
        except TelegramAPIError:
            pass
    await after_name(m, state, client, lang, biz)


@router.message(Contact.phone)
async def on_phone(m: Message, state: FSMContext, db: Database, biz: Business, client: Row, lang: str) -> None:
    raw = m.contact.phone_number if m.contact else (m.text or "")
    phone = clean_phone(raw)
    if phone is None:
        await m.answer(t(lang, "bad_phone"))
        return
    if not phone.startswith("+") and m.contact:
        phone = "+" + phone
    await db.set_contact(client["id"], phone=phone)
    fresh = await db.client_by_tg(m.chat.id)
    name = fresh["name"] if fresh else ""
    await m.answer(t(lang, "contact_saved", name=esc(name)), reply_markup=ReplyKeyboardRemove())
    await finish_contact(m, state, lang, biz)


async def finish_contact(target: CallbackQuery | Message, state: FSMContext, lang: str, biz: Business) -> None:
    draft = (await state.get_data()).get("draft")
    await state.clear()
    if not draft or draft[0] not in biz.services:
        text, markup = menu_view(biz, lang)
    else:
        service_id, staff_id, day_text, time_text = draft
        text, markup = confirm_view("b", service_id, staff_id, parse_moment(day_text, time_text, biz), biz, lang)
    message = target.message if isinstance(target, CallbackQuery) else target
    if isinstance(message, Message):
        await message.answer(text, reply_markup=markup)


async def owned(cb: CallbackQuery, booking_id: str, db: Database, biz: Business, client: Row, lang: str) -> Row | None:
    row = await db.booking(int(booking_id)) if booking_id.isdigit() else None
    if row is None or row["client_id"] != client["id"] or row["status"] != "active" or row["end_ts"] <= ts(now(biz)):
        await cb.answer(t(lang, "not_found"), show_alert=True)
        await show_my(cb, db, biz, client, lang)
        return None
    return row


async def changeable(cb: CallbackQuery, row: Row, biz: Business, lang: str) -> bool:
    left = from_ts(row["start_ts"], biz) - now(biz)
    if left < timedelta(minutes=biz.rules.cancel_minutes):
        await cb.answer(t(lang, "too_late", time=fmt_minutes(lang, biz.rules.cancel_minutes)), show_alert=True)
        return False
    return True


async def show_my(cb: CallbackQuery, db: Database, biz: Business, client: Row, lang: str) -> None:
    rows_db = await db.client_bookings(client["id"], ts(now(biz)))
    if not rows_db:
        await show(cb, t(lang, "my_empty"), kb([[(t(lang, "btn_book"), "b")], menu_row(lang)]))
        return
    rows = [
        [(f"{fmt_dt(lang, from_ts(r['start_ts'], biz))} · {biz.service_name(r['service_id'], lang)}", f"v:{r['id']}")]
        for r in rows_db
    ]
    await show(cb, t(lang, "my_title"), kb(rows + [menu_row(lang)]))


@router.callback_query(F.data == "my")
async def on_my(cb: CallbackQuery, db: Database, biz: Business, client: Row, lang: str) -> None:
    await show_my(cb, db, biz, client, lang)


@router.callback_query(pre("v"))
async def on_view(cb: CallbackQuery, db: Database, biz: Business, client: Row, lang: str) -> None:
    row = await owned(cb, (cb.data or "").partition(":")[2], db, biz, client, lang)
    if row is None:
        return
    rows = [
        [(t(lang, "btn_reschedule"), f"r:{row['id']}")],
        [(t(lang, "btn_cancel_booking"), f"c:{row['id']}")],
        [(t(lang, "btn_back"), "my"), (t(lang, "btn_menu"), "menu")],
    ]
    await show(cb, row_card(biz, lang, row), kb(rows))


@router.callback_query(pre("c"))
async def on_cancel(cb: CallbackQuery, bot: Bot, db: Database, biz: Business, settings: Settings, client: Row, lang: str) -> None:
    parts = (cb.data or "").split(":")
    row = await owned(cb, parts[-1], db, biz, client, lang)
    if row is None or not await changeable(cb, row, biz, lang):
        return
    if len(parts) == 2:
        rows = [[(t(lang, "btn_yes_cancel"), f"c:ok:{row['id']}")], [(t(lang, "btn_back"), f"v:{row['id']}")]]
        await show(cb, f"{t(lang, 'cancel_ask')}\n\n{row_card(biz, lang, row)}", kb(rows))
        return
    await db.set_status(row["id"], "cancelled")
    await show(cb, t(lang, "cancelled"), kb([[(t(lang, "btn_book"), "b")], menu_row(lang)]))
    await notify_admins(bot, settings, db, biz, "adm_cancelled", row)


@router.callback_query(pre("rc"))
async def on_coming(cb: CallbackQuery, db: Database, biz: Business, client: Row, lang: str) -> None:
    row = await owned(cb, (cb.data or "").partition(":")[2], db, biz, client, lang)
    if row is None:
        return
    await db.confirm(row["id"])
    await show(cb, f"{row_card(biz, lang, row)}\n\n{t(lang, 'confirmed_thanks')}")


@router.callback_query(pre("r"))
async def on_reschedule(
    cb: CallbackQuery, bot: Bot, db: Database, biz: Business, settings: Settings, client: Row, lang: str
) -> None:
    parts = (cb.data or "").split(":")
    step = parts[1] if len(parts) > 2 else ""
    booking_id = parts[2] if len(parts) > 2 else parts[-1]
    row = await owned(cb, booking_id, db, biz, client, lang)
    if row is None or not await changeable(cb, row, biz, lang):
        return
    service = biz.services.get(row["service_id"])
    staff_list = candidates(biz, row["service_id"], row["staff_id"]) if service else []
    if service is None or not staff_list:
        await cb.answer(t(lang, "not_found"), show_alert=True)
        return
    earliest = now(biz) + timedelta(minutes=biz.rules.min_lead_minutes)
    bid = row["id"]

    async def dates() -> None:
        slots = await range_slots(db, biz, service.minutes, staff_list, horizon(biz), earliest, exclude=bid)
        days = {day: bool(found) for day, found in slots.items()}
        back_row = [[(t(lang, "btn_back"), f"v:{bid}")]]
        if not any(days.values()):
            await show(cb, t(lang, "no_days", days=biz.rules.horizon_days), kb(back_row))
            return
        await show(cb, t(lang, "resched_date") + "\n" + date_range_title(lang, days), calendar(f"r:d:{bid}", days, lang, back_row))

    async def times(day_text: str) -> None:
        day = parse_ymd(day_text)
        slots = await range_slots(db, biz, service.minutes, staff_list, [day], earliest, exclude=bid)
        moments = list(slots[day])
        if not moments:
            await cb.answer(t(lang, "no_times"), show_alert=True)
            await dates()
            return
        back_row = [[(t(lang, "btn_back"), f"r:{bid}")]]
        await show(cb, t(lang, "resched_time", day=fmt_day(lang, day)), time_grid(f"r:t:{bid}:{day_text}", moments, back_row))

    if step == "":
        await dates()
        return
    if step == "d" and len(parts) == 4:
        await times(parts[3])
        return
    if step not in ("t", "ok") or len(parts) != 5:
        await dates()
        return

    start = parse_moment(parts[3], parts[4], biz)
    slots = await range_slots(db, biz, service.minutes, staff_list, [start.date()], earliest, exclude=bid)
    if start not in slots[start.date()]:
        await cb.answer(t(lang, "slot_taken"), show_alert=True)
        await times(parts[3])
        return
    if step == "t":
        text = f"{t(lang, 'resched_confirm')}\n\n{booking_card(biz, lang, row['service_id'], row['staff_id'], start)}"
        rows = [[(t(lang, "btn_resched_ok"), f"r:ok:{bid}:{parts[3]}:{parts[4]}")], [(t(lang, "btn_back"), f"r:d:{bid}:{parts[3]}")]]
        await show(cb, text, kb(rows))
        return
    try:
        await db.reschedule(bid, ts(start), ts(start + timedelta(minutes=service.minutes)))
    except SlotTaken:
        await cb.answer(t(lang, "slot_taken"), show_alert=True)
        await times(parts[3])
        return
    fresh = await db.booking(bid)
    assert fresh is not None
    await show(cb, f"{t(lang, 'rescheduled')}\n\n{row_card(biz, lang, fresh)}", kb([[(t(lang, "btn_my"), "my")], menu_row(lang)]))
    old = from_ts(row["start_ts"], biz)
    await notify_admins(bot, settings, db, biz, "adm_moved", fresh, extra=lambda code: t(code, "adm_was", when=fmt_dt(code, old)))


@router.callback_query(F.data == "sup")
async def on_support(cb: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.set_state(Support.message)
    await show(cb, t(lang, "support_ask"), kb([menu_row(lang)]))


@router.message(Support.message)
async def on_support_message(
    m: Message, state: FSMContext, bot: Bot, db: Database, settings: Settings, client: Row, lang: str
) -> None:
    await state.clear()
    name = client["name"] or (m.from_user.full_name if m.from_user else "")
    for admin_id in settings.admins:
        admin = await db.client_by_tg(admin_id)
        admin_lang = admin["lang"] if admin else "ru"
        link = f'<a href="tg://user?id={m.chat.id}">{esc(name)}</a>'
        try:
            head = await bot.send_message(admin_id, t(admin_lang, "adm_support_from", name=link, phone=esc(client["phone"] or "")))
            copy = await m.copy_to(admin_id)
        except TelegramAPIError as e:
            log.warning("cannot relay to admin %s: %s", admin_id, e)
            continue
        await db.add_relay(admin_id, head.message_id, m.chat.id)
        await db.add_relay(admin_id, copy.message_id, m.chat.id)
    await m.answer(t(lang, "support_sent"), reply_markup=kb([menu_row(lang)]))


@router.message()
async def on_other(m: Message, biz: Business, lang: str) -> None:
    text, markup = menu_view(biz, lang)
    await m.answer(text, reply_markup=markup)


@router.callback_query()
async def on_unknown_callback(cb: CallbackQuery, biz: Business, lang: str) -> None:
    await show(cb, *menu_view(biz, lang))
