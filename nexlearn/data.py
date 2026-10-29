"""Assignment data: the built-in sample set and syllabus CSV loading."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd

REQUIRED_COLUMNS = ["Course", "Assignment", "Due_Date", "Hours_Required"]

# (course, assignment, days from today, hours). Dates are relative so the demo
# always has upcoming work; the original hard-coded Nov 2025 and went stale.
_SAMPLE = [
    ("Global Markets", "Global Markets Quiz", 1, 2),
    ("Marketing Management", "Marketing Reflection", 2, 3),
    ("Data Analytics", "Data Analytics Midterm", 4, 5),
    ("Corporate Finance", "Finance Simulation Report", 6, 6),
    ("Business Strategy", "Business Strategy Presentation", 9, 4),
    ("Leadership", "Leadership Essay", 12, 3),
]

END_OF_DAY = time(23, 59)


def sample_assignments(today: date) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Course": [c for c, _, _, _ in _SAMPLE],
            "Assignment": [a for _, a, _, _ in _SAMPLE],
            "Due_Date": [datetime.combine(today + timedelta(days=d), END_OF_DAY) for _, _, d, _ in _SAMPLE],
            "Hours_Required": [float(h) for _, _, _, h in _SAMPLE],
        }
    )


def template_csv() -> bytes:
    rows = [
        "Course,Assignment,Due_Date,Hours_Required",
        "BUDT 704,Problem Set 3,2026-11-04,4",
        "BMGT 340,Case Write-up,2026-11-06 17:00,2.5",
    ]
    return ("\n".join(rows) + "\n").encode()


def load_syllabus_csv(file) -> tuple[pd.DataFrame | None, list[str]]:
    """Read and clean an uploaded syllabus CSV.

    Returns (dataframe or None, messages). A date with no time is treated as due at
    11:59 PM that day. Rows with an unreadable date or hours are dropped and reported.
    """
    messages: list[str] = []
    try:
        df = pd.read_csv(file)
    except Exception as e:
        return None, [f"Could not read the CSV: {e}"]

    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return None, [f"Missing required columns: {', '.join(missing)}"]
    df = df[REQUIRED_COLUMNS].copy()

    df["Course"] = df["Course"].fillna("").astype(str).str.strip()
    df["Assignment"] = df["Assignment"].fillna("").astype(str).str.strip()
    df = df[df["Assignment"] != ""]

    # "mixed": pandas otherwise infers one format from the first row and drops rows that
    # differ, e.g. "2026-11-04" next to "2026-11-05 17:00".
    df["Due_Date"] = pd.to_datetime(df["Due_Date"], errors="coerce", format="mixed")
    bad_dates = int(df["Due_Date"].isna().sum())
    if bad_dates:
        messages.append(f"Dropped {bad_dates} row(s) with a due date that could not be read.")
        df = df.dropna(subset=["Due_Date"])
    midnight = df["Due_Date"].dt.time == time(0, 0)
    df.loc[midnight, "Due_Date"] = df.loc[midnight, "Due_Date"].map(
        lambda d: datetime.combine(d.date(), END_OF_DAY)
    )

    df["Hours_Required"] = pd.to_numeric(df["Hours_Required"], errors="coerce")
    bad_hours = int((df["Hours_Required"].isna() | (df["Hours_Required"] < 0)).sum())
    if bad_hours:
        messages.append(f"Dropped {bad_hours} row(s) with missing or negative hours.")
        df = df[df["Hours_Required"] >= 0]

    # Progress is tracked by assignment name, so names must be unique.
    dupes = df["Assignment"].duplicated(keep=False)
    df.loc[dupes, "Assignment"] = df.loc[dupes, "Assignment"] + " (" + df.loc[dupes, "Course"] + ")"
    df = df.drop_duplicates(subset=["Assignment"])

    if df.empty:
        return None, messages + ["No usable rows left in the file."]
    return df.reset_index(drop=True), messages
