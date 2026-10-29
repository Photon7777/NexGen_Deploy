from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from nexlearn import planner

NOW = datetime(2026, 10, 28, 8, 0)  # Wednesday morning


def _df(rows):
    return pd.DataFrame(rows, columns=["Course", "Assignment", "Due_Date", "Hours_Required"])


def test_priority_uses_remaining_hours_and_days_left():
    df = _df([
        ("A", "Essay", NOW + timedelta(days=4), 8),
        ("B", "Quiz", NOW + timedelta(days=1), 2),
        ("C", "Old", NOW - timedelta(days=1), 3),
    ])
    t = planner.assignment_table(df, {"Essay": 50}, NOW).set_index("Assignment")
    assert t.loc["Essay", "Remaining_Hours"] == 4
    assert t.loc["Essay", "Priority"] == 1.0  # 4 hours over 4 days
    assert t.loc["Quiz", "Priority"] == 2.0
    assert bool(t.loc["Old", "Overdue"])
    done = planner.assignment_table(df, {"Quiz": 100}, NOW).set_index("Assignment")
    assert done.loc["Quiz", "Priority"] == 0


def test_busy_intervals_split_at_midnight_and_merge():
    late = datetime(2026, 10, 28, 22, 0)
    busy = planner.busy_by_day([
        (late, late + timedelta(hours=4)),
        (datetime(2026, 10, 28, 9), datetime(2026, 10, 28, 10)),
        (datetime(2026, 10, 28, 9, 30), datetime(2026, 10, 28, 11)),
    ])
    assert busy[date(2026, 10, 28)] == [
        (datetime(2026, 10, 28, 9), datetime(2026, 10, 28, 11)),
        (late, datetime(2026, 10, 29)),
    ]
    assert busy[date(2026, 10, 29)] == [(datetime(2026, 10, 29), datetime(2026, 10, 29, 2))]


def test_free_slots_skip_busy_and_past_time():
    day = NOW.date()
    busy = [(datetime(2026, 10, 28, 12), datetime(2026, 10, 28, 13, 30))]
    slots = planner.free_slots(day, busy, 9, 16, 60, not_before=datetime(2026, 10, 28, 10, 15))
    starts = [s.hour for s, _ in slots]
    assert starts == [11, 14, 15]


def _plan(df, progress=None, **kw):
    t = planner.assignment_table(df, progress or {}, NOW)
    return planner.allocate(t, NOW, **kw)


def test_blocks_never_overlap_and_respect_daily_cap():
    df = _df([
        ("A", "Report", NOW + timedelta(days=3), 6),
        ("B", "Slides", NOW + timedelta(days=3), 6),
    ])
    blocks, short = _plan(df, daily_cap_hours=3)
    spans = sorted((b.start, b.end) for b in blocks)
    for (s1, e1), (s2, _) in zip(spans, spans[1:]):
        assert e1 <= s2, "two assignments were booked into the same time"
    per_day = {}
    for b in blocks:
        per_day[b.start.date()] = per_day.get(b.start.date(), 0) + b.hours
    assert max(per_day.values()) <= 3
    # 3 days (Wed, Thu, Fri before the Sat 8am deadline) x 3 h = 9 h of the 12 needed.
    assert sum(b.hours for b in blocks) == 9
    assert sum(short.values()) == 3


def test_blocks_end_before_deadline_and_after_now():
    df = _df([("A", "Quiz", datetime(2026, 10, 29, 12, 0), 5)])
    blocks, short = _plan(df, daily_cap_hours=8)
    assert all(b.start >= NOW and b.end <= datetime(2026, 10, 29, 12) for b in blocks)
    assert sum(b.hours for b in blocks) == 5
    assert short == {}


def test_partial_hours_and_progress_reduce_the_plan():
    df = _df([("A", "Essay", NOW + timedelta(days=5), 3)])
    blocks, _ = _plan(df, progress={"Essay": 50})
    # A 1 h slot plus a 30 min slot, back to back, merged into one session.
    assert [b.hours for b in blocks] == [1.5]
    assert blocks[0].start == datetime(2026, 10, 28, 9)


def test_calendar_events_are_avoided():
    df = _df([("A", "Essay", NOW + timedelta(days=1), 2)])
    busy = [(datetime(2026, 10, 28, 9), datetime(2026, 10, 28, 12))]
    blocks, _ = _plan(df, busy=busy)
    assert blocks[0].start == datetime(2026, 10, 28, 12)


def test_far_deadlines_carry_over_without_a_shortfall():
    df = _df([("A", "Thesis", NOW + timedelta(days=30), 100)])
    blocks, short = _plan(df, daily_cap_hours=2)
    assert sum(b.hours for b in blocks) == 14  # 7 days x 2 h
    assert short == {}


def test_overdue_and_finished_work_is_not_scheduled():
    df = _df([
        ("A", "Late", NOW - timedelta(hours=1), 3),
        ("B", "Done", NOW + timedelta(days=2), 3),
    ])
    blocks, short = _plan(df, progress={"Done": 100})
    assert blocks == [] and short == {}


@pytest.mark.parametrize("cap", [1, 4, 8])
def test_sample_data_always_produces_a_plan(cap):
    from nexlearn.data import sample_assignments

    blocks, _ = _plan(sample_assignments(NOW.date()), daily_cap_hours=cap)
    assert blocks
