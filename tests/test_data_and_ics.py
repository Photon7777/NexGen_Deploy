import io
from datetime import date, datetime

from nexlearn import data, ics
from nexlearn.planner import StudyBlock


def test_sample_assignments_are_always_upcoming():
    today = date(2027, 3, 1)
    df = data.sample_assignments(today)
    assert (df["Due_Date"].dt.date > today).all()
    assert set(df.columns) == set(data.REQUIRED_COLUMNS)


def test_template_round_trips_through_the_loader():
    df, msgs = data.load_syllabus_csv(io.BytesIO(data.template_csv()))
    assert msgs == [] and len(df) == 2


def test_loader_reports_missing_columns():
    df, msgs = data.load_syllabus_csv(io.StringIO("Assignment,Due\nX,2026-11-01\n"))
    assert df is None and "Course" in msgs[0]


def test_loader_cleans_rows():
    csv = (
        " Course ,Assignment,Due_Date,Hours_Required\n"
        "BUDT 704,Midterm,2026-11-04,4\n"
        "BUDT 758,Midterm,2026-11-05 17:00,2\n"
        "BMGT 340,Case,not a date,3\n"
        "BMGT 340,Memo,2026-11-06,lots\n"
    )
    df, msgs = data.load_syllabus_csv(io.StringIO(csv))
    assert len(msgs) == 2  # one bad date, one bad hours value
    assert list(df["Assignment"]) == ["Midterm (BUDT 704)", "Midterm (BUDT 758)"]
    assert df.loc[0, "Due_Date"] == datetime(2026, 11, 4, 23, 59)  # date only means end of day
    assert df.loc[1, "Due_Date"] == datetime(2026, 11, 5, 17, 0)


def test_ics_converts_eastern_time_to_utc_across_dst():
    blocks = [
        StudyBlock("Essay, draft 2", "BMGT 340", datetime(2026, 10, 30, 10), datetime(2026, 10, 30, 11)),  # EDT
        StudyBlock("Quiz", "", datetime(2026, 11, 2, 10), datetime(2026, 11, 2, 10, 30)),  # EST
    ]
    out = ics.to_ics(blocks, stamp=datetime(2026, 10, 28))
    assert out.startswith("BEGIN:VCALENDAR\r\n") and out.endswith("END:VCALENDAR\r\n")
    assert out.count("BEGIN:VEVENT") == 2
    assert "DTSTART:20261030T140000Z" in out
    assert "DTSTART:20261102T150000Z" in out and "DTEND:20261102T153000Z" in out
    assert "SUMMARY:Study: Essay\\, draft 2 (BMGT 340)" in out


def test_ics_folds_long_lines():
    long_name = "A very long assignment title " * 6
    out = ics.to_ics([StudyBlock(long_name, "X", datetime(2026, 11, 2, 9), datetime(2026, 11, 2, 10))])
    assert all(len(line.encode()) <= 75 for line in out.split("\r\n"))
    assert "\r\n " in out
