from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from bookbot.config import Staff
from bookbot.reminders import due_reminders
from bookbot.slots import free_slots, pick_staff, work_intervals

TZ = ZoneInfo("Asia/Almaty")
MONDAY = date(2026, 11, 16)
STAFF = Staff("a", {"ru": "A"}, ("cut",), {0: (time(10), time(14))}, None)
LUNCH = Staff("b", {"ru": "B"}, ("cut",), {0: (time(10), time(16))}, (time(12), time(13)))
EARLY = datetime(2026, 1, 1, tzinfo=TZ)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 16, hour, minute, tzinfo=TZ)


def times(slots: list[datetime]) -> list[str]:
    return [f"{s:%H:%M}" for s in slots]


def test_day_off_has_no_slots():
    assert work_intervals(STAFF, MONDAY + timedelta(days=1), TZ) == []
    assert free_slots(STAFF, 30, MONDAY + timedelta(days=1), [], EARLY, 30, TZ) == []


def test_slots_fill_the_day_and_respect_duration():
    assert times(free_slots(STAFF, 30, MONDAY, [], EARLY, 30, TZ)) == [
        "10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30",
    ]
    assert times(free_slots(STAFF, 75, MONDAY, [], EARLY, 30, TZ))[-1] == "12:30"


def test_lunch_splits_the_day():
    slots = times(free_slots(LUNCH, 45, MONDAY, [], EARLY, 30, TZ))
    assert "11:00" in slots and "11:30" not in slots and "12:00" not in slots and "13:00" in slots
    assert slots[-1] == "15:00"


def test_busy_interval_blocks_overlapping_slots():
    busy = [(at(11), at(11, 45))]
    slots = times(free_slots(STAFF, 30, MONDAY, busy, EARLY, 30, TZ))
    assert "10:30" in slots and "11:00" not in slots and "11:30" not in slots and "12:00" in slots
    assert "10:30" not in times(free_slots(STAFF, 45, MONDAY, busy, EARLY, 30, TZ))


def test_earliest_cuts_past_slots():
    assert times(free_slots(STAFF, 30, MONDAY, [], at(12, 10), 30, TZ)) == ["12:30", "13:00", "13:30"]


def test_pick_staff_prefers_the_least_loaded():
    assert pick_staff(["a", "b"], {"a": 3, "b": 1}) == "b"
    assert pick_staff(["a", "b"], {}) == "a"


def test_reminders_fire_once_and_skip_late_bookings():
    start = 1_000_000
    hours = (24, 2)
    assert due_reminders(start, 0, 0, hours, start - 25 * 3600) == (0, None)
    assert due_reminders(start, 0, 0, hours, start - 24 * 3600) == (1, 0)
    assert due_reminders(start, 0, 1, hours, start - 23 * 3600) == (0, None)
    assert due_reminders(start, 0, 1, hours, start - 2 * 3600) == (2, 1)
    assert due_reminders(start, start - 5 * 3600, 0, hours, start - 5 * 3600) == (1, None)
    assert due_reminders(start, 0, 0, hours, start - 3600) == (3, 1)
