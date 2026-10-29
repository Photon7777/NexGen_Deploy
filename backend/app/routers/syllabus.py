from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from langchain_core.language_models import BaseChatModel
from psycopg import Connection
from pydantic import AwareDatetime, BaseModel, Field

from .. import syllabus
from ..ai_deps import ai_failure, get_extraction_model, take_ai_request
from ..auth import User, current_user
from ..config import Settings, get_settings
from ..db import db, user_transaction
from ..planning import user_tz
from .assignments import ImportResult, _list, _upsert

router = APIRouter(prefix="/syllabus", tags=["syllabus"])

INJECTION_WARNING = (
    "This PDF contains text written to AI tools rather than to students. Rows that came from it are "
    "flagged and unticked; check the rest against your syllabus too."
)


class DraftItem(BaseModel):
    title: str
    kind: str
    due_at: datetime | None
    due_text: str = Field(description="The date as the syllabus writes it")
    weight_pct: float | None
    hours_estimate: float
    evidence: str = Field(description="The model's quote from the syllabus for this item")
    flags: list[str] = Field(description="What the student should check before saving")


class SyllabusDraft(BaseModel):
    course: str | None
    pages: int
    items: list[DraftItem]
    warnings: list[str]


class SaveItem(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: AwareDatetime
    hours_required: float = Field(ge=0, le=500)


class SaveIn(BaseModel):
    course: str | None = Field(default=None, max_length=100)
    items: list[SaveItem] = Field(min_length=1, max_length=200)


@router.post("/extract", response_model=SyllabusDraft)
def extract(
    file: UploadFile,
    user: User = Depends(current_user),
    llm: BaseChatModel = Depends(get_extraction_model),
    settings: Settings = Depends(get_settings),
) -> SyllabusDraft:
    """Read a syllabus PDF into draft assignments. Nothing is saved until POST /syllabus/save."""
    content = file.file.read(syllabus.MAX_PDF_BYTES + 1)
    if len(content) > syllabus.MAX_PDF_BYTES:
        raise HTTPException(413, "Syllabus PDFs are limited to 5 MB.")
    try:
        text, pages = syllabus.pdf_text(content)  # before the quota, so a scan costs nothing
    except syllabus.SyllabusError as e:
        raise HTTPException(422, str(e)) from e

    with user_transaction(user) as conn:
        take_ai_request(conn, "syllabus", settings)
        tz = user_tz(conn)
    now = datetime.now(tz)
    try:
        result = syllabus.extract(text, now.date(), llm)  # no connection held during the model call
    except Exception as e:
        raise ai_failure(e) from e
    drafts = syllabus.review(result, text, now)
    return SyllabusDraft(
        course=(result.course or "").strip()[:100] or None,
        pages=pages,
        items=[DraftItem(**vars(d)) for d in drafts],
        warnings=[INJECTION_WARNING] if syllabus.injected_spans(text) else [],
    )


@router.post("/save", response_model=ImportResult)
def save(body: SaveIn, conn: Connection = Depends(db)) -> ImportResult:
    """Save the reviewed items. Saving the same course and title again updates that assignment."""
    course = (body.course or "").strip() or None
    for item in body.items:
        key = hashlib.sha256(f"{course or ''}|{item.title.strip()}".encode()).hexdigest()[:24]
        _upsert(conn, item.title.strip(), course, item.due_at, item.hours_required, "syllabus", key)
    return ImportResult(imported=len(body.items), messages=[], assignments=_list(conn))
