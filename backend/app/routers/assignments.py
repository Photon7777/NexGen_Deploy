from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from psycopg import Connection
from pydantic import AwareDatetime, BaseModel, Field

from nexlearn.data import sample_assignments

from ..db import db

router = APIRouter(prefix="/assignments", tags=["assignments"])


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


_SELECT = """
    select a.id, a.title, c.name as course, a.due_at, a.hours_required::float as hours_required,
           a.completion_pct, a.source
    from assignments a left join courses c on c.id = a.course_id
"""


def _course_id(conn: Connection, name: str | None) -> UUID | None:
    if not name:
        return None
    row = conn.execute(
        "insert into courses (name) values (%s) "
        "on conflict (user_id, name) do update set name = excluded.name returning id",
        (name.strip(),),
    ).fetchone()
    return row["id"]


def _get(conn: Connection, assignment_id: UUID) -> Assignment:
    row = conn.execute(_SELECT + " where a.id = %s", (assignment_id,)).fetchone()
    if row is None:  # missing, or another student's (RLS hides it)
        raise HTTPException(404, "Assignment not found")
    return Assignment(**row)


@router.get("", response_model=list[Assignment])
def list_assignments(conn: Connection = Depends(db)) -> list[Assignment]:
    return [Assignment(**r) for r in conn.execute(_SELECT + " order by a.due_at, a.title").fetchall()]


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
    if conn.execute("delete from assignments where id = %s returning id", (assignment_id,)).fetchone() is None:
        raise HTTPException(404, "Assignment not found")
    return Response(status_code=204)


@router.post("/sample", response_model=list[Assignment])
def load_sample(conn: Connection = Depends(db)) -> list[Assignment]:
    """Add the six demo assignments, dated from today. Running it again refreshes them."""
    tz = ZoneInfo(conn.execute("select timezone from profiles").fetchone()["timezone"])
    today = datetime.now(tz).date()
    for i, r in enumerate(sample_assignments(today).itertuples(index=False), 1):
        conn.execute(
            """
            insert into assignments (title, course_id, due_at, hours_required, source, external_id)
            values (%s, %s, %s, %s, 'sample', %s)
            on conflict (user_id, source, external_id) do update
                set title = excluded.title, course_id = excluded.course_id,
                    due_at = excluded.due_at, hours_required = excluded.hours_required
            """,
            (r.Assignment, _course_id(conn, r.Course), r.Due_Date.to_pydatetime().replace(tzinfo=tz),
             r.Hours_Required, f"sample-{i}"),
        )
    return list_assignments(conn)
