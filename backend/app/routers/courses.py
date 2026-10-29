from __future__ import annotations

import hashlib
import time
from datetime import datetime
from pathlib import PurePath
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from langchain_core.language_models import BaseChatModel
from psycopg import Connection, errors
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from .. import ask, materials, pdf
from ..ai_deps import ai_failure, get_embedder, get_extraction_model, take_ai_request
from ..auth import User, current_user
from ..config import Settings, get_settings
from ..db import db, user_transaction
from .assignments import _course_id

router = APIRouter(tags=["courses"])


class Course(BaseModel):
    id: UUID
    name: str
    documents: int
    pages: int
    assignments: int


class CourseIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class Document(BaseModel):
    id: UUID
    filename: str
    page_count: int
    chunks: int
    created_at: datetime


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class Citation(BaseModel):
    n: int
    document_id: UUID
    filename: str
    page_from: int
    page_to: int
    text: str = Field(description="The passage the answer drew on")


class AskResult(BaseModel):
    answer: str
    covered: bool
    citations: list[Citation]
    latency_ms: int


class PastQuestion(BaseModel):
    id: int
    question: str
    answer: str
    covered: bool
    citations: list[Citation]
    created_at: datetime


COURSES_SQL = """
select c.id, c.name,
       (select count(*) from documents d where d.course_id = c.id) as documents,
       (select coalesce(sum(page_count), 0) from documents d where d.course_id = c.id) as pages,
       (select count(*) from assignments a where a.course_id = c.id) as assignments
from courses c
"""


def _course(conn: Connection, course_id: UUID) -> Course:
    row = conn.execute(COURSES_SQL + " where c.id = %s", (course_id,)).fetchone()
    if row is None:  # missing, or another student's (RLS hides it)
        raise HTTPException(404, "Course not found")
    return Course(**row)


@router.get("/courses", response_model=list[Course])
def list_courses(conn: Connection = Depends(db)) -> list[Course]:
    return [Course(**r) for r in conn.execute(COURSES_SQL + " order by c.name").fetchall()]


@router.post("/courses", response_model=Course, status_code=201)
def create_course(body: CourseIn, conn: Connection = Depends(db)) -> Course:
    """Create a course, or return the existing one with the same course code."""
    return _course(conn, _course_id(conn, body.name))


# ------------------------------------------------------------------ materials


@router.get("/courses/{course_id}/documents", response_model=list[Document])
def list_documents(course_id: UUID, conn: Connection = Depends(db)) -> list[Document]:
    _course(conn, course_id)
    rows = conn.execute(
        "select d.id, d.filename, d.page_count, d.created_at, (select count(*) from chunks c where c.document_id = d.id) as chunks "
        "from documents d where d.course_id = %s order by d.created_at",
        (course_id,),
    ).fetchall()
    return [Document(**r) for r in rows]


@router.post("/courses/{course_id}/documents", response_model=Document, status_code=201)
def upload_document(
    course_id: UUID,
    file: UploadFile,
    user: User = Depends(current_user),
    embed: materials.Embedder = Depends(get_embedder),
) -> Document:
    """Add a PDF to a course: keep each page's text, then chunk and embed it for Ask."""
    content = file.file.read(materials.MAX_UPLOAD_BYTES + 1)
    if len(content) > materials.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Files are limited to 20 MB.")
    try:
        pages, total = pdf.read_pages(content, materials.MAX_DOCUMENT_PAGES)
    except pdf.PdfError as e:
        raise HTTPException(422, "NexLearn could not read this file as a PDF.") from e
    if total > materials.MAX_DOCUMENT_PAGES:
        raise HTTPException(413, f"PDFs are limited to {materials.MAX_DOCUMENT_PAGES} pages.")
    chunks = materials.chunk_pages(pages)
    if not chunks:
        raise HTTPException(422, "This PDF has no readable text, so it is probably a scan.")
    filename = PurePath(file.filename or "document.pdf").name.strip()[:200] or "document.pdf"
    digest = hashlib.sha256(content).hexdigest()

    with user_transaction(user) as conn:
        course = _course(conn, course_id)
        if conn.execute("select 1 from documents where course_id = %s and sha256 = %s", (course_id, digest)).fetchone():
            raise HTTPException(409, "This file is already in the course.")
        if course.pages + total > materials.MAX_COURSE_PAGES:
            raise HTTPException(413, f"A course can hold {materials.MAX_COURSE_PAGES} pages of materials; this one has {course.pages}.")

    try:
        vectors = embed([c.text for c in chunks])  # no connection held during the embedding calls
    except Exception as e:
        raise ai_failure(e) from e

    with user_transaction(user) as conn:
        try:
            doc = conn.execute(
                "insert into documents (course_id, filename, sha256, page_count) values (%s, %s, %s, %s) returning id, created_at",
                (course_id, filename, digest, total),
            ).fetchone()
        except errors.UniqueViolation as e:  # the same file, uploaded twice at once
            raise HTTPException(409, "This file is already in the course.") from e
        with conn.cursor() as cur:
            cur.executemany(
                "insert into document_pages (document_id, page_no, text) values (%s, %s, %s)",
                [(doc["id"], n, materials.clean(text)) for n, text in enumerate(pages, 1)],
            )
            cur.executemany(
                "insert into chunks (course_id, document_id, page_from, page_to, text, embedding) values (%s, %s, %s, %s, %s, %s::vector)",
                [(course_id, doc["id"], c.page_from, c.page_to, c.text, materials.to_vector(v)) for c, v in zip(chunks, vectors)],
            )
    return Document(id=doc["id"], filename=filename, page_count=total, chunks=len(chunks), created_at=doc["created_at"])


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: UUID, conn: Connection = Depends(db)) -> Response:
    """Remove a file and everything made from it (pages and chunks)."""
    if conn.execute("delete from documents where id = %s returning id", (document_id,)).fetchone() is None:
        raise HTTPException(404, "Document not found")
    return Response(status_code=204)


# ------------------------------------------------------------------ ask


@router.post("/courses/{course_id}/ask", response_model=AskResult)
def ask_course(
    course_id: UUID,
    body: AskIn,
    user: User = Depends(current_user),
    embed: materials.Embedder = Depends(get_embedder),
    llm: BaseChatModel = Depends(get_extraction_model),
    settings: Settings = Depends(get_settings),
) -> AskResult:
    """Answer from the course's materials only, citing the pages used."""
    question = body.question.strip()
    with user_transaction(user) as conn:
        _course(conn, course_id)
        if conn.execute("select 1 from chunks where course_id = %s limit 1", (course_id,)).fetchone() is None:
            raise HTTPException(409, "Upload course materials before asking about them.")
        take_ai_request(conn, "ask", settings)

    # Embed, retrieve, and answer, holding a connection only for the retrieval query.
    started = time.perf_counter()
    try:
        query = embed([question])[0]
    except Exception as e:
        raise ai_failure(e) from e
    with user_transaction(user) as conn:
        sources = ask.retrieve(conn, course_id, query)
    try:
        result, tokens = ask.answer(question, sources, llm)
    except Exception as e:
        raise ai_failure(e) from e
    latency_ms = round((time.perf_counter() - started) * 1000)

    citations = [
        Citation(n=s.n, document_id=s.document_id, filename=s.filename, page_from=s.page_from, page_to=s.page_to, text=s.text)
        for s in ask.cited_sources(result, sources)
    ]
    with user_transaction(user) as conn:
        conn.execute(
            "insert into course_questions (course_id, question, answer, covered, approach, citations, retrieved, latency_ms, tokens) "
            "values (%s, %s, %s, %s, 'chunks', %s, %s, %s, %s)",
            (
                course_id, question, result.answer, result.covered,
                Jsonb([c.model_dump(mode="json") for c in citations]),
                Jsonb([{"chunk_id": s.chunk_id, "distance": round(s.distance, 4)} for s in sources]),
                latency_ms, tokens,
            ),
        )
    return AskResult(answer=result.answer, covered=result.covered, citations=citations, latency_ms=latency_ms)


@router.get("/courses/{course_id}/questions", response_model=list[PastQuestion])
def past_questions(course_id: UUID, conn: Connection = Depends(db)) -> list[PastQuestion]:
    """The course's last 20 questions, newest first."""
    _course(conn, course_id)
    rows = conn.execute(
        "select id, question, answer, covered, citations, created_at from course_questions "
        "where course_id = %s order by created_at desc, id desc limit 20",
        (course_id,),
    ).fetchall()
    return [PastQuestion(**r) for r in rows]
