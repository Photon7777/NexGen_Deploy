from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from psycopg import Connection
from pydantic import BaseModel, Field, model_validator

from nexlearn import ics
from nexlearn.config import TZ as ICS_TZ
from nexlearn.planner import StudyBlock

from ..db import db
from ..planning import load_assignments, make_plan, save_plan, upcoming_blocks, user_tz

router = APIRouter(prefix="/plan", tags=["plan"])


class PlanSettings(BaseModel):
    daily_cap_hours: float = Field(4, ge=1, le=12)
    start_hour: int = Field(9, ge=0, le=22)
    end_hour: int = Field(22, ge=1, le=23)

    @model_validator(mode="after")
    def window_is_open(self) -> PlanSettings:
        if self.end_hour <= self.start_hour:
            raise ValueError("end_hour must be after start_hour")
        return self


class Block(BaseModel):
    id: UUID
    assignment_id: UUID
    title: str
    course: str | None
    starts_at: datetime
    ends_at: datetime


class Shortfall(BaseModel):
    assignment: str
    hours: float


class Plan(BaseModel):
    blocks: list[Block]
    shortfalls: list[Shortfall] = Field(description="Work due this week that will not fit before its deadline")


@router.post("", response_model=Plan)
def create_plan(settings: PlanSettings, conn: Connection = Depends(db)) -> Plan:
    """Plan the next 7 days and replace any upcoming study blocks."""
    tz = user_tz(conn)
    blocks, shortfalls, id_by_name = make_plan(
        load_assignments(conn), tz,
        daily_cap_hours=settings.daily_cap_hours, start_hour=settings.start_hour, end_hour=settings.end_hour,
    )
    save_plan(conn, blocks, id_by_name, tz)
    return Plan(
        blocks=[Block(**b) for b in upcoming_blocks(conn)],
        shortfalls=[Shortfall(assignment=a, hours=h) for a, h in shortfalls.items()],
    )


@router.get("", response_model=Plan)
def get_plan(conn: Connection = Depends(db)) -> Plan:
    return Plan(blocks=[Block(**b) for b in upcoming_blocks(conn)], shortfalls=[])


@router.get("/ics", response_class=Response)
def plan_ics(conn: Connection = Depends(db)) -> Response:
    """The upcoming plan as a calendar file for Google, Outlook, or Apple Calendar."""
    # nexlearn.ics expects naive US Eastern times.
    blocks = [
        StudyBlock(
            b["title"], b["course"] or "",
            b["starts_at"].astimezone(ICS_TZ).replace(tzinfo=None),
            b["ends_at"].astimezone(ICS_TZ).replace(tzinfo=None),
        )
        for b in upcoming_blocks(conn)
    ]
    return Response(
        ics.to_ics(blocks),
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="nexlearn_study_plan.ics"'},
    )
