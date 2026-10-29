"""Canvas calendar feeds: check the link, download it safely, and read the assignments in it.

Every Canvas user has a private iCal link (Calendar, then Calendar Feed). The format comes
from CalendarEvent::IcalEvent in canvas-lms (app/models/calendar_event.rb):

- An assignment's UID is event-assignment-<id>, or event-assignment-override-<id> when the
  student's section has its own date, or event-sub-assignment-<id> for discussion
  checkpoints. Lectures and other calendar events are event-calendar-event-<id>; we skip them.
- DTSTART is the due time in UTC, or a plain date for all-day items.
- SUMMARY is the title followed by " [COURSE_CODE]".
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar

# The API downloads whatever link a student saves, so it only accepts Canvas feed links
# on Instructure's own domain, and never follows a redirect off it.
FEED_URL = re.compile(
    r"https://[a-z0-9-]+(\.[a-z0-9-]+)*\.instructure\.com/feeds/calendars/(user|course)_[A-Za-z0-9]+\.ics"
)
MAX_FEED_BYTES = 5_000_000
TIMEOUT_SECONDS = 10

ASSIGNMENT_UID = re.compile(r"event-(assignment|assignment-override|sub-assignment)-\d+")
COURSE_SUFFIX = re.compile(r"\s*\[([^\[\]]+)\]\s*$")

# Canvas has no time estimates. First match wins, and students can change any of them.
HOURS_BY_KEYWORD = [
    (re.compile(r"\b(final|midterm|exam|test)\b", re.I), 6.0),
    (re.compile(r"\b(project|paper|essay|report|presentation|case)\b", re.I), 5.0),
    (re.compile(r"\b(quiz|discussion|reflection|reading|participation|attendance|survey)\b", re.I), 1.0),
]
DEFAULT_HOURS = 2.0

Fetcher = Callable[[str], bytes]


class FeedError(Exception):
    """A problem with the feed, worded for the student."""


@dataclass(frozen=True)
class FeedItem:
    uid: str
    title: str
    course: str | None
    due_at: datetime  # timezone-aware


def normalize_feed_url(raw: str) -> str:
    """Return the https form of a Canvas feed link, or raise FeedError."""
    url = raw.strip()
    if url.startswith("webcal://"):  # some calendar apps hand the link back this way
        url = "https://" + url.removeprefix("webcal://")
    if not FEED_URL.fullmatch(url):
        raise FeedError(
            "That is not a Canvas calendar feed link. In Canvas, open Calendar, click Calendar Feed, "
            "and copy the link (it ends in .ics)."
        )
    return url


def fetch_feed(url: str, transport: httpx.BaseTransport | None = None) -> bytes:
    """Download a link that passed normalize_feed_url: no redirects, a timeout, and a size cap."""
    try:
        with httpx.Client(transport=transport, timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
            with client.stream("GET", url) as response:
                if response.status_code in (401, 403, 404):
                    raise FeedError("Canvas did not accept this feed link. If you reset it, copy the new one from Canvas.")
                if response.status_code != 200:
                    raise FeedError(f"Canvas answered with an error ({response.status_code}). Try again in a few minutes.")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_FEED_BYTES:
                        raise FeedError("This calendar feed is too large to import.")
                return bytes(body)
    except httpx.HTTPError as e:
        raise FeedError("Could not reach Canvas. Try again in a few minutes.") from e


def parse_feed(content: bytes, tz: ZoneInfo) -> list[FeedItem]:
    """The assignments in a Canvas feed. All-day items are due at 11:59 PM in the student's time zone."""
    if not content.lstrip().startswith(b"BEGIN:VCALENDAR"):
        raise FeedError("Canvas sent something that is not a calendar. Check that you copied the Calendar Feed link.")
    try:
        calendar = Calendar.from_ical(content)
    except ValueError as e:
        raise FeedError("Canvas sent a calendar NexLearn could not read.") from e

    items = []
    for event in calendar.walk("VEVENT"):
        uid = str(event.get("UID", ""))
        if not ASSIGNMENT_UID.fullmatch(uid) or "DTSTART" not in event:
            continue
        summary = str(event.get("SUMMARY", "")).strip()
        match = COURSE_SUFFIX.search(summary)
        title = (summary[: match.start()] if match else summary).strip()
        if not title:
            continue
        start = event.decoded("DTSTART")
        if isinstance(start, datetime):
            due = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        else:
            due = datetime.combine(start, time(23, 59), tz)
        items.append(FeedItem(uid, title[:200], match.group(1).strip()[:100] if match else None, due))
    return items


def estimate_hours(title: str) -> float:
    return next((hours for pattern, hours in HOURS_BY_KEYWORD if pattern.search(title)), DEFAULT_HOURS)


def mask(url: str) -> str:
    """Enough of a saved link to recognize it, without the part that grants access."""
    host = url.removeprefix("https://").split("/", 1)[0]
    return f"{host}, link ending {url.removesuffix('.ics')[-4:]}"
