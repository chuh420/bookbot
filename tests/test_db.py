import asyncio

import pytest

from bookbot.db import Database, LimitReached, SlotTaken

FAR = 4_000_000_000


def run(coro):
    return asyncio.run(coro)


async def fresh() -> tuple[Database, int]:
    db = await Database.open(":memory:")
    client = await db.ensure_client(1, "ru")
    return db, client["id"]


def test_overlapping_booking_is_rejected():
    async def scenario():
        db, cid = await fresh()
        await db.create_booking(cid, "cut", "a", FAR, FAR + 2700)
        with pytest.raises(SlotTaken):
            await db.create_booking(cid, "cut", "a", FAR + 1800, FAR + 3600)
        await db.create_booking(cid, "cut", "b", FAR + 1800, FAR + 3600)
        await db.create_booking(cid, "cut", "a", FAR + 2700, FAR + 5400)
        await db.close()

    run(scenario())


def test_parallel_requests_get_one_slot():
    async def scenario():
        db, cid = await fresh()
        results = await asyncio.gather(
            *[db.create_booking(cid, "cut", "a", FAR, FAR + 1800) for _ in range(5)], return_exceptions=True
        )
        assert sum(isinstance(r, int) for r in results) == 1
        assert sum(isinstance(r, SlotTaken) for r in results) == 4
        await db.close()

    run(scenario())


def test_active_limit_and_cancel_frees_it():
    async def scenario():
        db, cid = await fresh()
        first = await db.create_booking(cid, "cut", "a", FAR, FAR + 1800, max_active=2)
        await db.create_booking(cid, "cut", "a", FAR + 3600, FAR + 5400, max_active=2)
        with pytest.raises(LimitReached):
            await db.create_booking(cid, "cut", "a", FAR + 7200, FAR + 9000, max_active=2)
        await db.set_status(first, "cancelled")
        await db.create_booking(cid, "cut", "a", FAR, FAR + 1800, max_active=2)
        await db.close()

    run(scenario())


def test_time_off_blocks_and_reschedule_ignores_itself():
    async def scenario():
        db, cid = await fresh()
        await db.add_time_off("a", FAR, FAR + 3600)
        with pytest.raises(SlotTaken):
            await db.create_booking(cid, "cut", "a", FAR + 1800, FAR + 3600)
        bid = await db.create_booking(cid, "cut", "a", FAR + 3600, FAR + 5400)
        await db.mark_reminded(bid, 1)
        await db.reschedule(bid, FAR + 4500, FAR + 6300)
        row = await db.booking(bid)
        assert row["start_ts"] == FAR + 4500 and row["reminded"] == 0
        with pytest.raises(SlotTaken):
            await db.reschedule(bid, FAR + 1800, FAR + 3600)
        await db.close()

    run(scenario())
