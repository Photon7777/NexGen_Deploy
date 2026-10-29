"""Priority scoring and the adaptive weekly planner. Pure functions, no Streamlit."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pandas as pd

Interval = tuple[datetime, datetime]


@dataclass
class StudyBlock:
    assignment: str
    course: str
    start: datetime
    end: datetime

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600


def assignment_table(df: pd.DataFrame, progress: dict[str, int], now: datetime) -> pd.DataFrame:
    """Add completion, remaining hours, days left, and priority to the assignment list.

    Priority is the remaining hours divided by the days left: how many hours a day the
    assignment needs from now until it is due.
    """
    t = df.copy()
    t["Completion_%"] = t["Assignment"].map(lambda a: int(progress.get(a, 0)))
    t["Remaining_Hours"] = (t["Hours_Required"] * (100 - t["Completion_%"]) / 100).round(2)
    days_left = (t["Due_Date"] - now) / pd.Timedelta(days=1)
    t["Days_Left"] = days_left.round(1)
    t["Overdue"] = t["Due_Date"] < now
    # Half a day floor keeps due-today and overdue work at the top without dividing by ~0.
    t["Priority"] = (t["Remaining_Hours"] / days_left.clip(lower=0.5)).round(2)
    t.loc[t["Remaining_Hours"] <= 0, "Priority"] = 0.0
    return t.sort_values("Due_Date").reset_index(drop=True)


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    merged: list[list[datetime]] = []
    for s, e in sorted(intervals):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def busy_by_day(intervals: list[Interval]) -> dict[date, list[Interval]]:
    """Group busy intervals by day, splitting any that run past midnight."""
    days: dict[date, list[Interval]] = {}
    for s, e in intervals:
        while s < e:
            midnight = datetime.combine(s.date() + timedelta(days=1), time(0))
            days.setdefault(s.date(), []).append((s, min(e, midnight)))
            s = midnight
    return {d: merge_intervals(v) for d, v in days.items()}


def free_slots(
    day: date,
    busy: list[Interval],
    start_hour: int = 9,
    end_hour: int = 22,
    slot_minutes: int = 60,
    not_before: datetime | None = None,
) -> list[Interval]:
    """Fixed-length slots inside the study window that overlap nothing busy."""
    slots = []
    cur = datetime.combine(day, time(start_hour))
    window_end = datetime.combine(day, time(end_hour))
    step = timedelta(minutes=slot_minutes)
    while cur + step <= window_end:
        nxt = cur + step
        starts_ok = not_before is None or cur >= not_before
        if starts_ok and all(nxt <= bs or cur >= be for bs, be in busy):
            slots.append((cur, nxt))
        cur = nxt
    return slots


def allocate(
    table: pd.DataFrame,
    now: datetime,
    busy: list[Interval] | None = None,
    days_ahead: int = 7,
    daily_cap_hours: float = 4,
    start_hour: int = 9,
    end_hour: int = 22,
    slot_minutes: int = 60,
) -> tuple[list[StudyBlock], dict[str, float]]:
    """Spread each assignment's remaining hours over free slots before it is due.

    Earliest deadline goes first, then highest priority. Each scheduled block is marked
    busy, so two assignments never share a slot, and no day goes over the daily cap.

    Returns (blocks in time order, shortfalls). A shortfall is the hours that could not
    fit for an assignment due inside the planning window. Work due later that does not
    fit simply carries over to the next plan.
    """
    days = [now.date() + timedelta(days=i) for i in range(days_ahead)]
    busy_map = busy_by_day(busy or [])
    used = {d: 0.0 for d in days}
    blocks: list[StudyBlock] = []
    shortfalls: dict[str, float] = {}

    todo = table[(~table["Overdue"]) & (table["Remaining_Hours"] > 0)]
    todo = todo.sort_values(["Due_Date", "Priority"], ascending=[True, False])

    for row in todo.itertuples(index=False):
        due = row.Due_Date.to_pydatetime()
        remaining = round(row.Remaining_Hours * 60)
        for d in days:
            if remaining <= 0 or d > due.date():
                break
            for s, _ in free_slots(d, busy_map.get(d, []), start_hour, end_hour, slot_minutes, now):
                cap_left = round((daily_cap_hours - used[d]) * 60)
                if remaining <= 0 or cap_left <= 0:
                    break
                end = s + timedelta(minutes=min(slot_minutes, remaining, cap_left))
                if end > due:
                    break
                blocks.append(StudyBlock(row.Assignment, row.Course, s, end))
                busy_map.setdefault(d, []).append((s, end))
                used[d] += (end - s).total_seconds() / 3600
                remaining -= round((end - s).total_seconds() / 60)
        if remaining > 0 and due.date() <= days[-1]:
            shortfalls[row.Assignment] = round(remaining / 60, 1)

    return _merge_adjacent(blocks), shortfalls


def _merge_adjacent(blocks: list[StudyBlock]) -> list[StudyBlock]:
    """Join back-to-back blocks of the same assignment into one study session."""
    merged: list[StudyBlock] = []
    for b in sorted(blocks, key=lambda b: b.start):
        if merged and merged[-1].assignment == b.assignment and merged[-1].end == b.start:
            merged[-1] = StudyBlock(b.assignment, b.course, merged[-1].start, b.end)
        else:
            merged.append(b)
    return merged


def _clock(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def blocks_frame(blocks: list[StudyBlock]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Day": [b.start.strftime("%a %b %d") for b in blocks],
            "Time": [f"{_clock(b.start)} to {_clock(b.end)}" for b in blocks],
            "Assignment": [b.assignment for b in blocks],
            "Hours": [f"{b.hours:g}" for b in blocks],
        }
    )
