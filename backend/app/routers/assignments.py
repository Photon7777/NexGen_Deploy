from __future__ import annotations

import hashlib
import io
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from psycopg import Connection
from pydantic import AwareDatetime, BaseModel, Field

from nexlearn.data import load_syllabus_csv, sample_assignments

from ..db import db
from ..planning import ASSIGNMENTS_SQL, enrich, load_assignments, user_tz

router = APIRouter(prefix="/assignments", tags=["assignments"])

MAX_CSV_BYTES = 1_000_000


class AssignmentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    course: str | None = Field(default=None, max_length=100)
    due_at: AwareDatetime
    hours_required: float = Field(ge=0, le=500)


class AssignmentPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    course: str | None = Field(default=None, max_length=100)
    due_at: AwareDatetime | None = None
    hours_required: float | None = Field(default=None, ge=0, le=500)
    completion_pct: int | None = Field(default=None, ge=0, le=100)


class Assignment(BaseModel):
    id: UUID
    title: str
    course: str | None
    due_at: datetime
    hours_required: float
    completion_pct: int
    source: str
    remaining_hours: float
    days_left: float
    priority: float = Field(description="Hours per day needed from now until the due date")
    overdue: bool


class ImportResult(BaseModel):
    imported: int
    messages: list[str]
    assignments: list[Assignment]


def _course_id(conn: Connection, name: str | None) -> UUID | None:
    if not name or not name.strip():
        return None
    row = conn.execute(
        "insert into courses (name) values (%s) "
        "on conflict (user_id, name) do update set name = excluded.name returning id",
        (name.strip(),),
    ).fetchone()
    return row["id"]


def _get(conn: Connection, assignment_id: UUID) -> Assignment:
    row = conn.execute(ASSIGNMENTS_SQL + " where a.id = %s", (assignment_id,)).fetchone()
    if row is None:  # missing, or another student's (RLS hides it)
        raise HTTPException(404, "Assignment not found")
    return Assignment(**enrich([row], user_tz(conn))[0])


def _list(conn: Connection) -> list[Assignment]:
    return [Assignment(**r) for r in enrich(load_assignments(conn), user_tz(conn))]


@router.get("", response_model=list[Assignment])
def list_assignments(conn: Connection = Depends(db)) -> list[Assignment]:
    return _list(conn)


@router.post("", response_model=Assignment, status_code=201)
def create_assignment(body: AssignmentIn, conn: Connection = Depends(db)) -> Assignment:
    row = conn.execute(
        "insert into assignments (title, course_id, due_at, hours_required) values (%s, %s, %s, %s) returning id",
        (body.title.strip(), _course_id(conn, body.course), body.due_at, body.hours_required),
    ).fetchone()
    return _get(conn, row["id"])


@router.patch("/{assignment_id}", response_model=Assignment)
def update_assignment(assignment_id: UUID, body: AssignmentPatch, conn: Connection = Depends(db)) -> Assignment:
    current = _get(conn, assignment_id)
    # An explicit null clears the course; for required fields it means "no change".
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k == "course"}
    if "course" in changes:
        changes["course_id"] = _course_id(conn, changes.pop("course"))
    if changes:
        columns = ", ".join(f"{col} = %s" for col in changes)  # keys come from the model, not the client
        conn.execute(f"update assignments set {columns} where id = %s", (*changes.values(), assignment_id))
    if "completion_pct" in changes and changes["completion_pct"] != current.completion_pct:
        conn.execute(
            "insert into progress_events (assignment_id, completion_pct, changed_by) values (%s, %s, 'student')",
            (assignment_id, changes["completion_pct"]),
        )
    return _get(conn, assignment_id)


@router.delete("/{assignment_id}", status_code=204)
def delete_assignment(assignment_id: UUID, conn: Connection = Depends(db)) -> Response:
    row = conn.execute("delete from assignments where id = %s returning source, external_id", (assignment_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Assignment not found")
    if row["source"] == "canvas_feed":  # keep the next Canvas sync from adding it back
        conn.execute("update canvas_feeds set dismissed = array_append(dismissed, %s)", (row["external_id"],))
    return Response(status_code=204)


def _upsert(conn: Connection, title: str, course: str, due_at: datetime, hours: float, source: str, external_id: str) -> None:
    conn.execute(
        """
        insert into assignments (title, course_id, due_at, hours_required, source, external_id)
        values (%s, %s, %s, %s, %s, %s)
        on conflict (user_id, source, external_id) do update
            set title = excluded.title, course_id = excluded.course_id,
                due_at = excluded.due_at, hours_required = excluded.hours_required
        """,
        (title, _course_id(conn, course), due_at, hours, source, external_id),
    )


@router.post("/sample", response_model=list[Assignment])
def load_sample(conn: Connection = Depends(db)) -> list[Assignment]:
    """Add the six demo assignments, dated from today. Running it again refreshes them."""
    tz = user_tz(conn)
    for i, r in enumerate(sample_assignments(datetime.now(tz).date()).itertuples(index=False), 1):
        _upsert(conn, r.Assignment, r.Course, r.Due_Date.to_pydatetime().replace(tzinfo=tz), r.Hours_Required, "sample", f"sample-{i}")
    return _list(conn)


@router.post("/import", response_model=ImportResult)
def import_csv(file: UploadFile, conn: Connection = Depends(db)) -> ImportResult:
    """Import a syllabus CSV (Course, Assignment, Due_Date, Hours_Required). Re-importing
    the same rows updates them instead of adding duplicates."""
    content = file.file.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise HTTPException(413, "CSV files are limited to 1 MB.")
    df, messages = load_syllabus_csv(io.BytesIO(content))
    if df is None:
        raise HTTPException(422, " ".join(messages))
    tz = user_tz(conn)
    for r in df.itertuples(index=False):
        due = r.Due_Date.to_pydatetime().replace(tzinfo=tz)
        key = hashlib.sha256(f"{r.Course}|{r.Assignment}".encode()).hexdigest()[:24]
        _upsert(conn, r.Assignment, r.Course, due, float(r.Hours_Required), "csv", key)
    return ImportResult(imported=len(df), messages=messages, assignments=_list(conn))
