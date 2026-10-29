"""Bridge between database rows and the nexlearn planner.

The planner works in naive datetimes in the student's local time zone, keyed by
assignment name. The database stores timestamptz values keyed by id. These helpers
convert in both directions.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pandas as pd
from psycopg import Connection

from nexlearn import planner

ASSIGNMENTS_SQL = """
    select a.id, a.title, c.name as course, a.due_at, a.hours_required::float as hours_required,
           a.completion_pct, a.source
    from assignments a left join courses c on c.id = a.course_id
"""


def load_assignments(conn: Connection) -> list[dict]:
    return conn.execute(ASSIGNMENTS_SQL + " order by a.due_at, a.title").fetchall()


def user_tz(conn: Connection) -> ZoneInfo:
    row = conn.execute("select timezone from profiles").fetchone()
    return ZoneInfo(row["timezone"] if row else "America/New_York")


def local_now(tz: ZoneInfo) -> datetime:
    return datetime.now(tz).replace(tzinfo=None)


def display_names(rows: list[dict]) -> dict[UUID, str]:
    """Unique names for the planner and the agent: the title, plus the course when titles repeat."""
    counts = Counter(r["title"] for r in rows)
    names: dict[UUID, str] = {}
    taken: set[str] = set()
    for r in rows:
        name = r["title"] if counts[r["title"]] == 1 else f"{r['title']} ({r['course'] or 'no course'})"
        base, n = name, 2
        while name in taken:
            name, n = f"{base} #{n}", n + 1
        names[r["id"]] = name
        taken.add(name)
    return names


def frame(rows: list[dict], names: dict[UUID, str], tz: ZoneInfo) -> tuple[pd.DataFrame, dict[str, int]]:
    df = pd.DataFrame(
        {
            "Course": pd.Series([r["course"] or "" for r in rows], dtype=object),
            "Assignment": pd.Series([names[r["id"]] for r in rows], dtype=object),
            "Due_Date": pd.Series([r["due_at"].astimezone(tz).replace(tzinfo=None) for r in rows], dtype="datetime64[us]"),
            "Hours_Required": pd.Series([float(r["hours_required"]) for r in rows], dtype=float),
        }
    )
    return df, {names[r["id"]]: r["completion_pct"] for r in rows}


def enrich(rows: list[dict], tz: ZoneInfo) -> list[dict]:
    """Add remaining hours, days left, priority, and overdue to each assignment row."""
    if not rows:
        return []
    names = display_names(rows)
    df, progress = frame(rows, names, tz)
    table = planner.assignment_table(df, progress, local_now(tz)).set_index("Assignment")
    out = []
    for r in rows:
        t = table.loc[names[r["id"]]]
        out.append(
            {
                **r,
                "remaining_hours": float(t["Remaining_Hours"]),
                "days_left": float(t["Days_Left"]),
                "priority": float(t["Priority"]),
                "overdue": bool(t["Overdue"]),
            }
        )
    return out


def make_plan(
    rows: list[dict], tz: ZoneInfo, *, daily_cap_hours: float, start_hour: int, end_hour: int, days_ahead: int = 7
) -> tuple[list[planner.StudyBlock], dict[str, float], dict[str, UUID]]:
    names = display_names(rows)
    df, progress = frame(rows, names, tz)
    now = local_now(tz)
    blocks, shortfalls = planner.allocate(
        planner.assignment_table(df, progress, now), now, [],
        days_ahead=days_ahead, daily_cap_hours=daily_cap_hours, start_hour=start_hour, end_hour=end_hour,
    )
    return blocks, shortfalls, {name: id_ for id_, name in names.items()}


def save_plan(conn: Connection, blocks: list[planner.StudyBlock], id_by_name: dict[str, UUID], tz: ZoneInfo) -> None:
    """Replace upcoming study blocks. Past blocks stay as history for later analytics."""
    conn.execute("delete from study_blocks where ends_at > now()")
    for b in blocks:
        conn.execute(
            "insert into study_blocks (assignment_id, starts_at, ends_at) values (%s, %s, %s)",
            (id_by_name[b.assignment], b.start.replace(tzinfo=tz), b.end.replace(tzinfo=tz)),
        )


def upcoming_blocks(conn: Connection) -> list[dict]:
    return conn.execute(
        """
        select s.id, s.assignment_id, a.title, c.name as course, s.starts_at, s.ends_at
        from study_blocks s
        join assignments a on a.id = s.assignment_id
        left join courses c on c.id = a.course_id
        where s.ends_at > now()
        order by s.starts_at
        """
    ).fetchall()
