"""Export study blocks as an .ics file that Google, Outlook, and Apple Calendar can import."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .config import TZ
from .planner import StudyBlock


def _utc(dt: datetime) -> str:
    return dt.replace(tzinfo=TZ).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545 caps lines at 75 octets; continuation lines start with a space."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode())
            cur = b""
        cur += b
    out.append(cur.decode())
    return "\r\n ".join(out)


def to_ics(blocks: list[StudyBlock], stamp: datetime | None = None) -> str:
    stamp_utc = (stamp or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NexLearn AI//Study Planner//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for b in blocks:
        course = f" ({b.course})" if b.course else ""
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uuid.uuid4()}@nexlearn",
            f"DTSTAMP:{stamp_utc}",
            f"DTSTART:{_utc(b.start)}",
            f"DTEND:{_utc(b.end)}",
            f"SUMMARY:{_escape('Study: ' + b.assignment + course)}",
            f"DESCRIPTION:{_escape('Study block planned by NexLearn AI.')}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
