from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Staff

Interval = tuple[datetime, datetime]


def work_intervals(staff: Staff, day: date, tz: ZoneInfo) -> list[Interval]:
    hours = staff.hours.get(day.weekday())
    if hours is None:
        return []
    start = datetime.combine(day, hours[0], tz)
    end = datetime.combine(day, hours[1], tz)
    if staff.lunch is None:
        return [(start, end)]
    lunch_start = datetime.combine(day, staff.lunch[0], tz)
    lunch_end = datetime.combine(day, staff.lunch[1], tz)
    if lunch_end <= start or lunch_start >= end:
        return [(start, end)]
    parts = []
    if lunch_start > start:
        parts.append((start, lunch_start))
    if lunch_end < end:
        parts.append((lunch_end, end))
    return parts


def overlaps(start: datetime, end: datetime, busy: list[Interval]) -> bool:
    return any(b_start < end and b_end > start for b_start, b_end in busy)


def free_slots(
    staff: Staff,
    minutes: int,
    day: date,
    busy: list[Interval],
    earliest: datetime,
    step_minutes: int,
    tz: ZoneInfo,
) -> list[datetime]:
    duration = timedelta(minutes=minutes)
    step = timedelta(minutes=step_minutes)
    result = []
    for begin, finish in work_intervals(staff, day, tz):
        start = begin
        while start + duration <= finish:
            if start >= earliest and not overlaps(start, start + duration, busy):
                result.append(start)
            start += step
    return result


def pick_staff(candidates: list[str], loads: dict[str, int]) -> str:
    return min(candidates, key=lambda staff_id: loads.get(staff_id, 0))
