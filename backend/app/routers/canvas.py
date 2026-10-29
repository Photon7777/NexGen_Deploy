from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from psycopg import Connection
from pydantic import BaseModel, Field

from .. import canvas
from ..auth import User, current_user
from ..db import db, user_transaction
from ..planning import user_tz
from .assignments import Assignment, _course_id, _list

router = APIRouter(prefix="/canvas", tags=["canvas"])


def get_fetcher() -> canvas.Fetcher:
    """Tests override this dependency with a canned feed."""
    return canvas.fetch_feed


class FeedIn(BaseModel):
    feed_url: str = Field(max_length=500)


class CanvasStatus(BaseModel):
    connected: bool
    feed: str | None = Field(default=None, description="The host and last characters of the saved link, never all of it")
    synced_at: datetime | None = None
    last_error: str | None = None


class SyncResult(BaseModel):
    added: int
    changed: int
    unchanged: int
    skipped_past: int = Field(description="Assignments already due, which are not imported")
    synced_at: datetime
    assignments: list[Assignment]


@router.get("", response_model=CanvasStatus)
def status(conn: Connection = Depends(db)) -> CanvasStatus:
    row = conn.execute("select feed_url, synced_at, last_error from canvas_feeds").fetchone()
    if row is None:
        return CanvasStatus(connected=False)
    return CanvasStatus(connected=True, feed=canvas.mask(row["feed_url"]), synced_at=row["synced_at"], last_error=row["last_error"])


@router.put("", response_model=SyncResult)
def connect(body: FeedIn, user: User = Depends(current_user), fetch: canvas.Fetcher = Depends(get_fetcher)) -> SyncResult:
    """Save a Canvas feed link and import from it. A link that does not work is not saved."""
    try:
        url = canvas.normalize_feed_url(body.feed_url)
    except canvas.FeedError as e:
        raise HTTPException(422, str(e)) from e
    with user_transaction(user) as conn:
        tz = user_tz(conn)
    try:
        items = canvas.parse_feed(fetch(url), tz)
    except canvas.FeedError as e:
        raise HTTPException(502, str(e)) from e
    return _save(user, items, new_url=url)


@router.post("/sync", response_model=SyncResult)
def sync(user: User = Depends(current_user), fetch: canvas.Fetcher = Depends(get_fetcher)) -> SyncResult:
    with user_transaction(user) as conn:
        row = conn.execute("select feed_url from canvas_feeds").fetchone()
        tz = user_tz(conn)
    if row is None:
        raise HTTPException(404, "Canvas is not connected.")
    # The download can take seconds, so no connection is held during it.
    try:
        items = canvas.parse_feed(fetch(row["feed_url"]), tz)
    except canvas.FeedError as e:
        with user_transaction(user) as conn:
            conn.execute("update canvas_feeds set last_error = %s", (str(e),))
        raise HTTPException(502, str(e)) from e
    return _save(user, items)


@router.delete("", status_code=204)
def disconnect(conn: Connection = Depends(db)) -> Response:
    """Forget the feed link. Assignments already imported stay."""
    conn.execute("delete from canvas_feeds")
    return Response(status_code=204)


def _save(user: User, items: list[canvas.FeedItem], new_url: str | None = None) -> SyncResult:
    now = datetime.now(timezone.utc)
    with user_transaction(user) as conn:
        if new_url:
            conn.execute(
                "insert into canvas_feeds (feed_url, synced_at) values (%s, %s) "
                "on conflict (user_id) do update set feed_url = excluded.feed_url, synced_at = excluded.synced_at, last_error = null",
                (new_url, now),
            )
        else:
            conn.execute("update canvas_feeds set synced_at = %s, last_error = null", (now,))
        feed = conn.execute("select dismissed from canvas_feeds").fetchone()
        dismissed = set(feed["dismissed"]) if feed else set()  # None if disconnected mid-sync

        upcoming = [i for i in items if i.due_at > now and i.uid not in dismissed]
        added = changed = 0
        for item in upcoming:
            # Canvas owns the title, course, and due date; the student owns hours and progress.
            # Rows that did not change return nothing, so the counts are exact.
            row = conn.execute(
                """
                insert into assignments (title, course_id, due_at, hours_required, source, external_id)
                values (%s, %s, %s, %s, 'canvas_feed', %s)
                on conflict (user_id, source, external_id) do update
                    set title = excluded.title, course_id = excluded.course_id, due_at = excluded.due_at
                    where (assignments.title, assignments.course_id, assignments.due_at)
                          is distinct from (excluded.title, excluded.course_id, excluded.due_at)
                returning (xmax = 0) as inserted
                """,
                (item.title, _course_id(conn, item.course), item.due_at, canvas.estimate_hours(item.title), item.uid),
            ).fetchone()
            if row is not None:
                added += row["inserted"]
                changed += not row["inserted"]
        return SyncResult(
            added=added,
            changed=changed,
            unchanged=len(upcoming) - added - changed,
            skipped_past=sum(i.due_at <= now for i in items),
            synced_at=now,
            assignments=_list(conn),
        )
