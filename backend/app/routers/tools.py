from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from langchain_core.language_models import BaseChatModel
from psycopg import Connection
from pydantic import BaseModel, Field

from nexlearn import ai

from ..ai_deps import ai_failure, get_chat_model, take_ai_request
from ..auth import User, current_user
from ..config import Settings, get_settings
from ..db import db, user_transaction

router = APIRouter(tags=["study tools"])


class FlashcardsIn(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    count: int = Field(6, ge=3, le=10)


class Flashcard(BaseModel):
    question: str
    answer: str


class CheckinIn(BaseModel):
    mood: int = Field(ge=1, le=5)
    energy: int = Field(ge=1, le=5)
    confidence: int = Field(ge=1, le=5)
    note: str | None = Field(default=None, max_length=500)


class Checkin(CheckinIn):
    id: int
    created_at: datetime


@router.post("/flashcards", response_model=list[Flashcard])
def flashcards(
    body: FlashcardsIn,
    user: User = Depends(current_user),
    llm: BaseChatModel = Depends(get_chat_model),
    settings: Settings = Depends(get_settings),
) -> list[Flashcard]:
    with user_transaction(user) as conn:
        take_ai_request(conn, "flashcards", settings)
    try:
        cards = ai.make_flashcards(body.topic.strip(), body.count, llm)
    except Exception as e:
        raise ai_failure(e) from e
    return [Flashcard(question=c.question, answer=c.answer) for c in cards]


@router.get("/checkins", response_model=list[Checkin])
def list_checkins(conn: Connection = Depends(db)) -> list[Checkin]:
    rows = conn.execute(
        "select * from (select id, mood, energy, confidence, note, created_at from checkins "
        "order by created_at desc limit 60) c order by created_at"
    ).fetchall()
    return [Checkin(**r) for r in rows]


@router.post("/checkins", response_model=Checkin, status_code=201)
def add_checkin(body: CheckinIn, conn: Connection = Depends(db)) -> Checkin:
    row = conn.execute(
        "insert into checkins (mood, energy, confidence, note) values (%s, %s, %s, %s) "
        "returning id, mood, energy, confidence, note, created_at",
        (body.mood, body.energy, body.confidence, (body.note or "").strip() or None),
    ).fetchone()
    return Checkin(**row)
