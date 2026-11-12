import asyncio
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY,
    tg_id INTEGER UNIQUE,
    name TEXT,
    phone TEXT,
    lang TEXT NOT NULL DEFAULT 'ru',
    created_ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    service_id TEXT NOT NULL,
    staff_id TEXT NOT NULL,
    start_ts INTEGER NOT NULL,
    end_ts INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    confirmed INTEGER NOT NULL DEFAULT 0,
    reminded INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'client',
    created_ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS bookings_staff_start ON bookings(staff_id, start_ts);
CREATE INDEX IF NOT EXISTS bookings_client ON bookings(client_id, start_ts);
CREATE TABLE IF NOT EXISTS time_off (
    id INTEGER PRIMARY KEY,
    staff_id TEXT NOT NULL,
    start_ts INTEGER NOT NULL,
    end_ts INTEGER NOT NULL,
    created_ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS relay (
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    client_tg_id INTEGER NOT NULL,
    PRIMARY KEY (chat_id, message_id)
);
"""

BOOKING_SELECT = """
SELECT b.*, c.name AS client_name, c.phone AS client_phone, c.tg_id AS client_tg, c.lang AS client_lang
FROM bookings b JOIN clients c ON c.id = b.client_id
"""

Row = sqlite3.Row


class SlotTaken(Exception):
    pass


class LimitReached(Exception):
    pass


def now_ts() -> int:
    return int(time.time())


class Database:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn
        self.lock = asyncio.Lock()

    @classmethod
    async def open(cls, path: Path | str) -> "Database":
        conn = await aiosqlite.connect(path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            await conn.execute("PRAGMA journal_mode = WAL")
        await conn.executescript(SCHEMA)
        return cls(conn)

    async def close(self) -> None:
        await self.conn.close()

    async def one(self, sql: str, params: Iterable[Any] = ()) -> Row | None:
        async with self.conn.execute(sql, tuple(params)) as cur:
            return await cur.fetchone()

    async def all(self, sql: str, params: Iterable[Any] = ()) -> list[Row]:
        async with self.conn.execute(sql, tuple(params)) as cur:
            return list(await cur.fetchall())

    async def write(self, sql: str, params: Iterable[Any] = ()) -> int:
        async with self.lock:
            cur = await self.conn.execute(sql, tuple(params))
            rowid = cur.lastrowid or 0
            await cur.close()
            return rowid

    async def ensure_client(self, tg_id: int, lang: str) -> Row:
        row = await self.one("SELECT * FROM clients WHERE tg_id = ?", (tg_id,))
        if row is None:
            await self.write(
                "INSERT OR IGNORE INTO clients (tg_id, lang, created_ts) VALUES (?, ?, ?)", (tg_id, lang, now_ts())
            )
            row = await self.one("SELECT * FROM clients WHERE tg_id = ?", (tg_id,))
        assert row is not None
        return row

    async def client_by_tg(self, tg_id: int) -> Row | None:
        return await self.one("SELECT * FROM clients WHERE tg_id = ?", (tg_id,))

    async def set_lang(self, client_id: int, lang: str) -> None:
        await self.write("UPDATE clients SET lang = ? WHERE id = ?", (lang, client_id))

    async def set_contact(self, client_id: int, name: str | None = None, phone: str | None = None) -> None:
        if name is not None:
            await self.write("UPDATE clients SET name = ? WHERE id = ?", (name, client_id))
        if phone is not None:
            await self.write("UPDATE clients SET phone = ? WHERE id = ?", (phone, client_id))

    async def manual_client(self, name: str, phone: str) -> int:
        row = await self.one("SELECT id FROM clients WHERE phone = ? AND tg_id IS NULL", (phone,))
        if row is not None:
            await self.write("UPDATE clients SET name = ? WHERE id = ?", (name, row["id"]))
            return row["id"]
        return await self.write(
            "INSERT INTO clients (name, phone, created_ts) VALUES (?, ?, ?)", (name, phone, now_ts())
        )

    async def busy(self, staff_ids: list[str], start_ts: int, end_ts: int, exclude: int | None = None) -> list[Row]:
        if not staff_ids:
            return []
        marks = ",".join("?" * len(staff_ids))
        return await self.all(
            f"""
            SELECT staff_id, start_ts, end_ts FROM bookings
            WHERE status = 'active' AND staff_id IN ({marks}) AND start_ts < ? AND end_ts > ? AND id IS NOT ?
            UNION ALL
            SELECT staff_id, start_ts, end_ts FROM time_off
            WHERE staff_id IN ({marks}) AND start_ts < ? AND end_ts > ?
            """,
            (*staff_ids, end_ts, start_ts, exclude, *staff_ids, end_ts, start_ts),
        )

    async def loads(self, start_ts: int, end_ts: int) -> dict[str, int]:
        rows = await self.all(
            "SELECT staff_id, COUNT(*) AS n FROM bookings WHERE status = 'active' AND start_ts >= ? AND start_ts < ? GROUP BY staff_id",
            (start_ts, end_ts),
        )
        return {row["staff_id"]: row["n"] for row in rows}

    async def create_booking(
        self,
        client_id: int,
        service_id: str,
        staff_id: str,
        start_ts: int,
        end_ts: int,
        source: str = "client",
        max_active: int | None = None,
    ) -> int:
        async with self.lock:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                if max_active is not None:
                    row = await self.one(
                        "SELECT COUNT(*) AS n FROM bookings WHERE client_id = ? AND status = 'active' AND end_ts > ?",
                        (client_id, now_ts()),
                    )
                    if row is not None and row["n"] >= max_active:
                        raise LimitReached
                if await self.busy([staff_id], start_ts, end_ts):
                    raise SlotTaken
                cur = await self.conn.execute(
                    "INSERT INTO bookings (client_id, service_id, staff_id, start_ts, end_ts, source, created_ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (client_id, service_id, staff_id, start_ts, end_ts, source, now_ts()),
                )
                booking_id = cur.lastrowid or 0
                await cur.close()
                await self.conn.execute("COMMIT")
                return booking_id
            except BaseException:
                await self.conn.execute("ROLLBACK")
                raise

    async def reschedule(self, booking_id: int, start_ts: int, end_ts: int) -> None:
        async with self.lock:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                row = await self.one("SELECT staff_id FROM bookings WHERE id = ? AND status = 'active'", (booking_id,))
                if row is None or await self.busy([row["staff_id"]], start_ts, end_ts, exclude=booking_id):
                    raise SlotTaken
                await self.conn.execute(
                    "UPDATE bookings SET start_ts = ?, end_ts = ?, reminded = 0, confirmed = 0, created_ts = ? WHERE id = ?",
                    (start_ts, end_ts, now_ts(), booking_id),
                )
                await self.conn.execute("COMMIT")
            except BaseException:
                await self.conn.execute("ROLLBACK")
                raise

    async def booking(self, booking_id: int) -> Row | None:
        return await self.one(BOOKING_SELECT + " WHERE b.id = ?", (booking_id,))

    async def set_status(self, booking_id: int, status: str) -> None:
        await self.write("UPDATE bookings SET status = ? WHERE id = ?", (status, booking_id))

    async def confirm(self, booking_id: int) -> None:
        await self.write("UPDATE bookings SET confirmed = 1 WHERE id = ?", (booking_id,))

    async def mark_reminded(self, booking_id: int, bit: int) -> None:
        await self.write("UPDATE bookings SET reminded = reminded | ? WHERE id = ?", (bit, booking_id))

    async def client_bookings(self, client_id: int, after_ts: int) -> list[Row]:
        return await self.all(
            BOOKING_SELECT + " WHERE b.client_id = ? AND b.status = 'active' AND b.end_ts > ? ORDER BY b.start_ts",
            (client_id, after_ts),
        )

    async def bookings_between(self, start_ts: int, end_ts: int, active_only: bool = True) -> list[Row]:
        status = " AND b.status = 'active'" if active_only else ""
        return await self.all(
            BOOKING_SELECT + f" WHERE b.start_ts >= ? AND b.start_ts < ?{status} ORDER BY b.start_ts, b.staff_id",
            (start_ts, end_ts),
        )

    async def upcoming_active(self, after_ts: int, before_ts: int) -> list[Row]:
        return await self.all(
            BOOKING_SELECT + " WHERE b.status = 'active' AND b.start_ts > ? AND b.start_ts <= ? ORDER BY b.start_ts",
            (after_ts, before_ts),
        )

    async def count_bookings(self, staff_id: str, start_ts: int, end_ts: int) -> int:
        row = await self.one(
            "SELECT COUNT(*) AS n FROM bookings WHERE status = 'active' AND staff_id = ? AND start_ts < ? AND end_ts > ?",
            (staff_id, end_ts, start_ts),
        )
        return row["n"] if row else 0

    async def add_time_off(self, staff_id: str, start_ts: int, end_ts: int) -> int:
        return await self.write(
            "INSERT INTO time_off (staff_id, start_ts, end_ts, created_ts) VALUES (?, ?, ?, ?)",
            (staff_id, start_ts, end_ts, now_ts()),
        )

    async def time_off_between(self, start_ts: int, end_ts: int) -> list[Row]:
        return await self.all(
            "SELECT * FROM time_off WHERE start_ts < ? AND end_ts > ? ORDER BY start_ts", (end_ts, start_ts)
        )

    async def delete_time_off(self, off_id: int) -> None:
        await self.write("DELETE FROM time_off WHERE id = ?", (off_id,))

    async def add_relay(self, chat_id: int, message_id: int, client_tg_id: int) -> None:
        await self.write(
            "INSERT OR REPLACE INTO relay (chat_id, message_id, client_tg_id) VALUES (?, ?, ?)",
            (chat_id, message_id, client_tg_id),
        )

    async def relay_target(self, chat_id: int, message_id: int) -> int | None:
        row = await self.one("SELECT client_tg_id FROM relay WHERE chat_id = ? AND message_id = ?", (chat_id, message_id))
        return row["client_tg_id"] if row else None
