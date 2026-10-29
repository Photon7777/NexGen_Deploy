"""Optional Google Calendar sync for local runs.

Google's desktop sign-in flow opens a browser on the machine running the app, so it
only works when you run NexLearn on your own computer with a credentials.json from
Google Cloud. On Streamlit Cloud there is no credentials.json, the toggle stays hidden,
and the .ics download covers the same need.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import pandas as pd

from .config import TZ
from .planner import Interval, StudyBlock

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


def available() -> bool:
    return os.path.exists(CREDENTIALS_FILE)


def _service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES).run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def _to_local(value: str) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(TZ).tz_localize(None)
    return ts.to_pydatetime()


def busy_intervals(now: datetime, days: int = 7) -> list[Interval]:
    """Timed events from the primary calendar. All-day events (birthdays, holidays) are
    skipped so they do not block a whole day."""
    start = now.replace(tzinfo=TZ).isoformat()
    end = (now + timedelta(days=days)).replace(tzinfo=TZ).isoformat()
    items = (
        _service()
        .events()
        .list(calendarId="primary", timeMin=start, timeMax=end, singleEvents=True, orderBy="startTime", maxResults=250)
        .execute()
        .get("items", [])
    )
    return [
        (_to_local(ev["start"]["dateTime"]), _to_local(ev["end"]["dateTime"]))
        for ev in items
        if "dateTime" in ev.get("start", {}) and "dateTime" in ev.get("end", {})
    ]


def add_blocks(blocks: list[StudyBlock]) -> int:
    service = _service()
    for b in blocks:
        course = f" ({b.course})" if b.course else ""
        service.events().insert(
            calendarId="primary",
            body={
                "summary": f"Study: {b.assignment}{course}",
                "description": "Study block planned by NexLearn AI.",
                "start": {"dateTime": b.start.isoformat(), "timeZone": "America/New_York"},
                "end": {"dateTime": b.end.isoformat(), "timeZone": "America/New_York"},
            },
        ).execute()
    return len(blocks)
