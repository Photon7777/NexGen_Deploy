"""Phase 1a: importing assignments from a Canvas calendar feed."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from app import canvas
from conftest import auth

FEED = "https://umd.instructure.com/feeds/calendars/user_AbCdEf0123456789wxyz.ics"
EASTERN = ZoneInfo("America/New_York")
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def vevent(uid: str, summary: str, start: datetime | date) -> str:
    """One event as Canvas writes it (CalendarEvent::IcalEvent in canvas-lms)."""
    if isinstance(start, datetime):
        when = f"DTSTART;TZID=UTC:{start:%Y%m%dT%H%M%S}\r\nDTEND;TZID=UTC:{start:%Y%m%dT%H%M%S}\r\n"
    else:
        when = f"DTSTART;VALUE=DATE:{start:%Y%m%d}\r\n"
    return f"BEGIN:VEVENT\r\nUID:{uid}\r\nSUMMARY:{summary}\r\n{when}END:VEVENT\r\n"


def feed(*events: str) -> bytes:
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Instructure//Canvas//EN\r\n" + "".join(events) + "END:VCALENDAR\r\n").encode()


def semester(days: int = 0) -> bytes:
    """A small feed: three upcoming assignments, one past, one lecture. `days` shifts the case study."""
    return feed(
        vevent("event-assignment-101", "Case Study 2 [BUDT758T]", NOW + timedelta(days=5 + days)),
        vevent("event-assignment-102", "Midterm Exam [BUDT704]", NOW + timedelta(days=10)),
        vevent("event-assignment-override-7", "Weekly Quiz 6 (Section 0101) [BUDT758T]", NOW + timedelta(days=2)),
        vevent("event-assignment-90", "Weekly Quiz 1 [BUDT758T]", NOW - timedelta(days=30)),
        vevent("event-calendar-event-55", "Lecture: Regression [BUDT704]", NOW + timedelta(days=1)),
    )


# ------------------------------------------------------------------ the feed module


def test_parse_keeps_assignments_and_splits_out_the_course_code():
    items = {i.uid: i for i in canvas.parse_feed(semester(), EASTERN)}
    assert set(items) == {"event-assignment-101", "event-assignment-102", "event-assignment-override-7", "event-assignment-90"}
    assert items["event-assignment-101"].title == "Case Study 2"
    assert items["event-assignment-101"].course == "BUDT758T"
    assert items["event-assignment-override-7"].title == "Weekly Quiz 6 (Section 0101)"
    assert items["event-assignment-102"].due_at == NOW + timedelta(days=10)


def test_parse_handles_all_day_items_escapes_and_folded_lines():
    long_title = "Final Project Report, including the appendix on data sources and the model comparison table"
    escaped = long_title.replace(",", "\\,")
    folded = f"SUMMARY:{escaped} [BUDT758T]"
    folded = folded[:70] + "\r\n " + folded[70:]  # RFC 5545 line folding
    content = feed(
        vevent("event-assignment-1", "Reading Response [INST314]", date(2026, 12, 4)),
        f"BEGIN:VEVENT\r\nUID:event-assignment-2\r\n{folded}\r\nDTSTART:20261210T045900Z\r\nEND:VEVENT\r\n",
    )
    reading, report = canvas.parse_feed(content, EASTERN)
    assert reading.due_at == datetime(2026, 12, 4, 23, 59, tzinfo=EASTERN)
    assert report.title == long_title
    assert report.due_at == datetime(2026, 12, 10, 4, 59, tzinfo=timezone.utc)


def test_parse_rejects_something_that_is_not_a_calendar():
    with pytest.raises(canvas.FeedError, match="not a calendar"):
        canvas.parse_feed(b"<!DOCTYPE html><html>Log in to Canvas</html>", EASTERN)


@pytest.mark.parametrize("link", [FEED, FEED.replace("https://", "webcal://"), f"  {FEED}\n"])
def test_feed_links_from_canvas_are_accepted(link):
    assert canvas.normalize_feed_url(link) == FEED


@pytest.mark.parametrize(
    "link",
    [
        FEED.replace("https://", "http://"),
        "https://umd.instructure.com.example.com/feeds/calendars/user_abc.ics",
        "https://example.com/feeds/calendars/user_abc.ics?x=.instructure.com",
        "https://umd.instructure.com/api/v1/users/self",
        "https://umd.instructure.com/feeds/calendars/user_abc.ics/../../api",
        "https://user:pw@umd.instructure.com/feeds/calendars/user_abc.ics",
    ],
)
def test_other_links_are_refused(link):
    with pytest.raises(canvas.FeedError):
        canvas.normalize_feed_url(link)


def fetch_with(handler) -> bytes:
    return canvas.fetch_feed(FEED, transport=httpx.MockTransport(handler))


def test_fetch_returns_the_feed():
    assert fetch_with(lambda request: httpx.Response(200, content=semester())) == semester()


def test_fetch_does_not_follow_redirects():
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/computeMetadata/v1/"})

    with pytest.raises(canvas.FeedError, match="302"):
        fetch_with(handler)
    assert len(calls) == 1


def test_fetch_explains_a_revoked_link_and_caps_the_size(monkeypatch):
    with pytest.raises(canvas.FeedError, match="did not accept"):
        fetch_with(lambda request: httpx.Response(404))
    monkeypatch.setattr(canvas, "MAX_FEED_BYTES", 1000)
    with pytest.raises(canvas.FeedError, match="too large"):
        fetch_with(lambda request: httpx.Response(200, content=b"x" * 5000))


def test_fetch_turns_network_errors_into_a_message():
    def handler(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(canvas.FeedError, match="Could not reach Canvas"):
        fetch_with(handler)


# ------------------------------------------------------------------ the API


@pytest.fixture
def canvas_serves(client):
    """Make the API's Canvas download return the given bytes, or raise the given FeedError."""
    from app.main import app
    from app.routers.canvas import get_fetcher

    requested = []

    def _serve(content: bytes | canvas.FeedError):
        def fetch(url: str) -> bytes:
            requested.append(url)
            if isinstance(content, canvas.FeedError):
                raise content
            return content

        app.dependency_overrides[get_fetcher] = lambda: fetch

    _serve.requested = requested
    yield _serve
    app.dependency_overrides.pop(get_fetcher, None)


def canvas_rows(client, user):
    return {a["title"]: a for a in client.get("/assignments", headers=auth(user)).json() if a["source"] == "canvas_feed"}


def test_connecting_imports_upcoming_assignments_and_hides_the_link(client, make_user, canvas_serves):
    user = make_user()
    canvas_serves(semester())
    result = client.put("/canvas", headers=auth(user), json={"feed_url": FEED}).json()
    assert (result["added"], result["changed"], result["unchanged"], result["skipped_past"]) == (3, 0, 0, 1)

    rows = canvas_rows(client, user)
    assert set(rows) == {"Case Study 2", "Midterm Exam", "Weekly Quiz 6 (Section 0101)"}
    assert rows["Midterm Exam"]["course"] == "BUDT704"
    assert [rows[t]["hours_required"] for t in ("Midterm Exam", "Case Study 2", "Weekly Quiz 6 (Section 0101)")] == [6, 5, 1]

    status = client.get("/canvas", headers=auth(user)).json()
    assert status["connected"] and status["last_error"] is None
    assert status["feed"] == "umd.instructure.com, link ending wxyz"
    assert "AbCdEf0123456789" not in str(status)


def test_a_link_that_is_not_canvas_is_refused_before_any_download(client, make_user, canvas_serves):
    user = make_user()
    canvas_serves(semester())
    response = client.put("/canvas", headers=auth(user), json={"feed_url": "https://example.com/cal.ics"})
    assert response.status_code == 422
    assert canvas_serves.requested == []
    assert client.get("/canvas", headers=auth(user)).json() == {"connected": False, "feed": None, "synced_at": None, "last_error": None}


def test_a_link_that_fails_to_download_is_not_saved(client, make_user, canvas_serves):
    user = make_user()
    canvas_serves(canvas.FeedError("Canvas did not accept this feed link."))
    assert client.put("/canvas", headers=auth(user), json={"feed_url": FEED}).status_code == 502
    assert client.get("/canvas", headers=auth(user)).json()["connected"] is False


def test_resync_updates_canvas_fields_but_keeps_the_students_hours_and_progress(client, make_user, canvas_serves):
    user = make_user()
    canvas_serves(semester())
    client.put("/canvas", headers=auth(user), json={"feed_url": FEED})
    case = canvas_rows(client, user)["Case Study 2"]
    client.patch(f"/assignments/{case['id']}", headers=auth(user), json={"hours_required": 8, "completion_pct": 40})

    canvas_serves(semester(days=2))  # the instructor moved the case study back two days
    result = client.post("/canvas/sync", headers=auth(user)).json()
    assert (result["added"], result["changed"], result["unchanged"]) == (0, 1, 2)

    case_after = canvas_rows(client, user)["Case Study 2"]
    assert case_after["id"] == case["id"]
    assert datetime.fromisoformat(case_after["due_at"]) == NOW + timedelta(days=7)
    assert (case_after["hours_required"], case_after["completion_pct"]) == (8, 40)


def test_a_deleted_canvas_assignment_stays_deleted(client, make_user, canvas_serves):
    user = make_user()
    canvas_serves(semester())
    client.put("/canvas", headers=auth(user), json={"feed_url": FEED})
    quiz = canvas_rows(client, user)["Weekly Quiz 6 (Section 0101)"]
    assert client.delete(f"/assignments/{quiz['id']}", headers=auth(user)).status_code == 204

    result = client.post("/canvas/sync", headers=auth(user)).json()
    assert result["added"] == 0
    assert "Weekly Quiz 6 (Section 0101)" not in canvas_rows(client, user)


def test_a_failed_sync_is_reported_and_remembered(client, make_user, canvas_serves):
    user = make_user()
    canvas_serves(semester())
    client.put("/canvas", headers=auth(user), json={"feed_url": FEED})

    canvas_serves(canvas.FeedError("Could not reach Canvas. Try again in a few minutes."))
    response = client.post("/canvas/sync", headers=auth(user))
    assert response.status_code == 502
    assert client.get("/canvas", headers=auth(user)).json()["last_error"].startswith("Could not reach Canvas")

    canvas_serves(semester())
    client.post("/canvas/sync", headers=auth(user))
    assert client.get("/canvas", headers=auth(user)).json()["last_error"] is None


def test_disconnecting_keeps_imported_assignments(client, make_user, canvas_serves):
    user = make_user()
    canvas_serves(semester())
    client.put("/canvas", headers=auth(user), json={"feed_url": FEED})
    assert client.delete("/canvas", headers=auth(user)).status_code == 204
    assert client.get("/canvas", headers=auth(user)).json()["connected"] is False
    assert len(canvas_rows(client, user)) == 3
    assert client.post("/canvas/sync", headers=auth(user)).status_code == 404


def test_feeds_are_private_to_each_student(client, make_user, canvas_serves, admin_db):
    owner, other = make_user(), make_user()
    canvas_serves(semester())
    client.put("/canvas", headers=auth(owner), json={"feed_url": FEED})

    assert client.get("/canvas", headers=auth(other)).json()["connected"] is False
    assert client.delete("/canvas", headers=auth(other)).status_code == 204  # deletes nothing of the owner's
    assert admin_db.execute("select count(*) from canvas_feeds where user_id = %s", (owner,)).fetchone()[0] == 1
