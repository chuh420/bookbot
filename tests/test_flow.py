import asyncio
import itertools
import time
from datetime import datetime
from pathlib import Path

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.types import Chat, Message, MessageId

from bookbot import reminders
from bookbot.config import Settings, load_business
from bookbot.db import Database
from bookbot.main import build_dispatcher

ROOT = Path(__file__).resolve().parent.parent
ADMIN = 900
BIZ = load_business(ROOT / "business.example.toml")
SETTINGS = Settings("42:TEST", frozenset({ADMIN}), ROOT / "business.example.toml", Path(":memory:"), None)
DP = build_dispatcher(None, BIZ, SETTINGS)
IDS = itertools.count(1000)


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[dict] = []

    async def close(self) -> None:
        pass

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        chat_id = getattr(method, "chat_id", None)
        record = {
            "method": name,
            "chat": chat_id,
            "text": getattr(method, "text", None) or getattr(method, "caption", None) or "",
            "markup": getattr(method, "reply_markup", None),
            "id": next(IDS),
            "document": getattr(method, "document", None),
        }
        self.sent.append(record)
        if name == "CopyMessage":
            return MessageId(message_id=record["id"])
        if name in ("SendMessage", "EditMessageText", "SendDocument"):
            return Message(message_id=record["id"], date=datetime.now(), chat=Chat(id=chat_id, type="private"), text=record["text"])
        return True


class Sim:
    def __init__(self, bot: Bot, session: FakeSession, user_id: int, lang: str = "ru", name: str = "Тест") -> None:
        self.bot, self.session, self.user_id = bot, session, user_id
        self.user = {"id": user_id, "is_bot": False, "first_name": name, "language_code": lang}

    def base(self) -> dict:
        return {"message_id": next(IDS), "date": int(time.time()), "chat": {"id": self.user_id, "type": "private"}}

    async def feed(self, key: str, payload: dict) -> None:
        await DP.feed_raw_update(self.bot, {"update_id": next(IDS), key: payload})

    async def text(self, text: str, reply_to: int | None = None) -> None:
        payload = {**self.base(), "from": self.user, "text": text}
        if text.startswith("/"):
            payload["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        if reply_to is not None:
            payload["reply_to_message"] = {**self.base(), "message_id": reply_to, "text": "x"}
        await self.feed("message", payload)

    async def contact(self, phone: str) -> None:
        await self.feed("message", {**self.base(), "from": self.user, "contact": {"phone_number": phone, "first_name": "x"}})

    async def click(self, data: str) -> None:
        await self.feed(
            "callback_query",
            {"id": str(next(IDS)), "from": self.user, "chat_instance": "x", "data": data, "message": {**self.base(), "text": "x"}},
        )

    def last(self) -> dict:
        return next(r for r in reversed(self.session.sent) if r["chat"] == self.user_id and r["method"] in ("SendMessage", "EditMessageText"))

    def buttons(self) -> list[tuple[str, str]]:
        markup = self.last()["markup"]
        rows = getattr(markup, "inline_keyboard", None) or []
        return [(b.text, b.callback_data) for row in rows for b in row]

    def find(self, prefix: str) -> str:
        return next(data for _, data in self.buttons() if data.startswith(prefix))

    async def press(self, prefix: str) -> None:
        await self.click(self.find(prefix))


async def setup() -> tuple[Database, Bot, FakeSession]:
    db = await Database.open(":memory:")
    DP["db"] = db
    session = FakeSession()
    bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode="HTML"))
    return db, bot, session


async def book(user: Sim, staff: str = "arman", service: str = "haircut") -> None:
    await user.text("/start")
    await user.press("b")
    await user.press(f"b:s:{service}")
    await user.press(f"b:m:{service}:{staff}")
    await user.press("b:d:")
    await user.press("b:t:")


def run(scenario):
    async def wrapper():
        db, bot, session = await setup()
        try:
            await scenario(db, bot, session)
        finally:
            await db.close()

    asyncio.run(wrapper())


def test_full_client_flow():
    async def scenario(db, bot, session):
        user = Sim(bot, session, 1)
        await book(user)
        assert "Как вас зовут" in user.last()["text"]
        await user.text("Айгерим")
        assert "номер" in user.last()["text"]
        await user.text("abc")
        assert "Не похоже" in user.last()["text"]
        await user.contact("77011234567")
        assert "Проверьте запись" in user.last()["text"]
        await user.press("b:ok:")
        assert "Вы записаны" in user.last()["text"]
        rows = await db.client_bookings(1, 0)
        assert len(rows) == 1 and rows[0]["client_phone"] == "+77011234567" and rows[0]["staff_id"] == "arman"
        admin_note = [r for r in session.sent if r["chat"] == ADMIN]
        assert len(admin_note) == 1 and "Новая запись" in admin_note[0]["text"] and "Айгерим" in admin_note[0]["text"]

        await book(user)
        assert "Проверьте запись" in user.last()["text"]
        await user.press("b:ok:")
        assert "Вы записаны" in user.last()["text"]
        await book(user)
        await user.press("b:ok:")
        assert "активные записи" in user.last()["text"]

    run(scenario)


def test_two_clients_cannot_take_one_slot():
    async def scenario(db, bot, session):
        first, second = Sim(bot, session, 1), Sim(bot, session, 2)
        for user in (first, second):
            await db.ensure_client(user.user_id, "ru")
            await db.set_contact(user.user_id, name="N", phone="+77010000000")
        await book(first)
        await book(second)
        assert first.find("b:ok:") == second.find("b:ok:")
        await first.press("b:ok:")
        await second.press("b:ok:")
        assert "Вы записаны" in first.last()["text"]
        assert "Выберите время" in second.last()["text"]
        assert len(await db.bookings_between(0, 4_000_000_000)) == 1

    run(scenario)


def test_any_staff_reschedule_cancel_and_languages():
    async def scenario(db, bot, session):
        user = Sim(bot, session, 5, lang="kk")
        await user.text("/start")
        assert "жазылуға" in user.last()["text"]
        await user.click("lang:en")
        assert "Book a visit" in [text for text, _ in user.buttons()][0]
        await db.set_contact((await db.client_by_tg(5))["id"], name="Tom", phone="+77010000001")
        await book(user, staff="any", service="combo")
        await user.press("b:ok:")
        row = (await db.client_bookings((await db.client_by_tg(5))["id"], 0))[0]
        assert row["staff_id"] in ("arman", "daniyar")
        if row["start_ts"] - time.time() > BIZ.rules.cancel_minutes * 60 + 60:
            await user.click("my")
            await user.press("v:")
            await user.press("r:")
            days = [d for _, d in user.buttons() if d.startswith("r:d:")]
            await user.click(days[-1])
            times = [d for _, d in user.buttons() if d.startswith("r:t:")]
            await user.click(times[-1])
            await user.press("r:ok:")
            assert "Booking moved" in user.last()["text"]
            moved = await db.booking(row["id"])
            assert moved["start_ts"] != row["start_ts"]
            assert any("moved" in r["text"] or "перенёс" in r["text"] for r in session.sent if r["chat"] == ADMIN)
            await user.click(f"c:{row['id']}")
            await user.press("c:ok:")
            assert (await db.booking(row["id"]))["status"] == "cancelled"

    run(scenario)


def test_admin_tools_and_support_relay():
    async def scenario(db, bot, session):
        admin, user = Sim(bot, session, ADMIN, name="Boss"), Sim(bot, session, 7)
        await user.text("/today")
        assert "Barber Demo" in user.last()["text"]

        await admin.text("/add")
        await admin.text("только имя")
        assert "Нужны имя и телефон" in admin.last()["text"]
        await admin.text("Марат +7 701 555 44 33")
        assert "Марат" in admin.last()["text"]
        await admin.press("a:s:haircut")
        await admin.press("a:m:haircut:arman")
        days = [d for _, d in admin.buttons() if d.startswith("a:d:")]
        await admin.click(days[-1])
        await admin.press("a:t:")
        await admin.press("a:ok:")
        assert "Марат" in admin.last()["text"]
        rows = await db.bookings_between(0, 4_000_000_000)
        assert len(rows) == 1 and rows[0]["source"] == "admin" and rows[0]["client_phone"] == "+77015554433"

        await admin.text("/week")
        assert "Марат" in "".join(r["text"] for r in session.sent if r["chat"] == ADMIN)
        await admin.click(f"ab:{rows[0]['id']}")
        await admin.press("an:")
        assert (await db.booking(rows[0]["id"]))["status"] == "noshow"

        await admin.text("/block")
        await admin.press("k:arman")
        await admin.press("k:d:")
        await admin.press("k:s:")
        await admin.press("k:e:")
        assert "Закрыто" in admin.last()["text"]
        await admin.text("/block")
        await admin.press("k:daniyar")
        await admin.press("k:d:")
        whole = next(d for _, d in admin.buttons() if d.endswith(":all"))
        await admin.click(whole)
        assert "Закрыто" in admin.last()["text"]
        await user.text("/start")
        await user.click("b:m:haircut:daniyar")
        offered = [d for _, d in user.buttons() if d.startswith("b:d:")]
        assert offered and f"b:d:haircut:daniyar:{whole.split(':')[3]}" not in offered
        await admin.text("/blocks")
        while any(d.startswith("kd:") for _, d in admin.buttons()):
            await admin.press("kd:")
        assert "нет" in admin.last()["text"]

        await admin.text("/export")
        assert any(r["method"] == "SendDocument" for r in session.sent)
        await admin.text("/stats")
        assert "Статистика" in admin.last()["text"]

        await user.click("sup")
        await user.text("Можно с собакой?")
        head = next(r for r in session.sent if r["chat"] == ADMIN and "реплаем" in r["text"])
        await admin.text("Можно", reply_to=head["id"])
        assert any(r["chat"] == 7 and r["method"] == "CopyMessage" for r in session.sent)

    run(scenario)


def test_reminder_is_sent_once():
    async def scenario(db, bot, session):
        client = await db.ensure_client(11, "ru")
        now_value = int(time.time())
        bid = await db.create_booking(client["id"], "haircut", "arman", now_value + 23 * 3600, now_value + 24 * 3600)
        await db.write("UPDATE bookings SET created_ts = ? WHERE id = ?", (now_value - 5 * 86400, bid))
        await reminders.tick(bot, db, BIZ)
        await reminders.tick(bot, db, BIZ)
        sent = [r for r in session.sent if r["chat"] == 11]
        assert len(sent) == 1 and "Напоминаем" in sent[0]["text"]
        user = Sim(bot, session, 11)
        await user.click(f"rc:{bid}")
        assert (await db.booking(bid))["confirmed"] == 1

    run(scenario)
