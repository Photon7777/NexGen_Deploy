# NexLearn API

FastAPI over Supabase Postgres. Every request runs as the signed-in student, so the
row-level security policies in `../supabase/migrations/` decide what each query can see.

```bash
cp .env.example .env
uv sync
PYTHONPATH=.. uv run uvicorn app.main:app --reload --port 8000   # docs at http://localhost:8000/docs
```

| File | Role |
| --- | --- |
| `app/auth.py` | Verifies Supabase access tokens (JWKS for new projects, HS256 for legacy ones) |
| `app/db.py` | Connection pool; runs each request as the `authenticated` role with the caller's claims |
| `app/planning.py` | Converts database rows to and from the `nexlearn` planner (naive local times, unique names) |
| `app/ai_deps.py` | The chat model dependency, and daily AI caps enforced by `private.take_ai_request` in Postgres |
| `app/canvas.py` | Canvas feed links: an allow-list check, a download with no redirects and a size cap, and the iCal parser |
| `app/syllabus.py` | Syllabus PDFs: text extraction, the structured-output prompt, and the checks behind each review flag |
| `app/materials.py`, `app/ask.py` | Chunk RAG: line-packed chunks with overlap, `text-embedding-3-small` vectors in pgvector (HNSW), and grounded answers with citations |
| `app/routers/` | See the endpoints below |
| `tests/` | Runs against a real Postgres with the real migrations; AI endpoints use a scripted model, never OpenAI |

| Endpoint | What it does |
| --- | --- |
| `GET /me` | Profile created at sign-up |
| `GET/POST /assignments`, `PATCH/DELETE /assignments/{id}` | Assignments with remaining hours, days left, and priority; progress changes are logged |
| `POST /assignments/sample`, `POST /assignments/import` | Demo data, or a syllabus CSV (re-importing updates rows) |
| `GET/PUT/DELETE /canvas`, `POST /canvas/sync` | Connect a Canvas calendar feed; syncing updates titles and due dates but never the student's hours or progress |
| `POST /syllabus/extract`, `POST /syllabus/save` | Read a syllabus PDF into a draft the student reviews (flags for missing dates, items not in the PDF, and text aimed at AI tools), then save the rows they keep |
| `GET/POST /courses`, `GET/POST /courses/{id}/documents`, `DELETE /documents/{id}` | Courses and their PDF materials: each page's text is kept, then chunked and embedded |
| `POST /courses/{id}/ask`, `GET /courses/{id}/questions` | Answer from a course's materials only, citing pages; every question is logged with what was retrieved |
| `POST /plan`, `GET /plan`, `GET /plan/ics` | Plan the next 7 days, read the saved plan, download it for any calendar |
| `GET/POST/DELETE /chat` | The tool-calling agent; history is stored, so it remembers the conversation |
| `POST /flashcards` | Structured-output flashcards on any topic |
| `GET/POST /checkins` | Daily mood, energy, and confidence |

AI calls never hold a database connection: `/chat` reads in one transaction, calls the model,
then writes the turn and any tool changes in a second transaction.

Tests need a local Postgres with pgvector:

```bash
docker run -d --name nexlearn-testdb -e POSTGRES_PASSWORD=postgres -p 54329:5432 pgvector/pgvector:pg17
uv run pytest
```

## Evals

`evals/syllabus/` scores syllabus extraction against hand-checked answer keys for four fictional
syllabi (a schedule table, prose with "Week 8" and "TBA" dates, a bulleted list, and a messy page
that tries to plant an item through text aimed at AI tools). It calls the real model, so it is not
part of the test suite:

```bash
uv run python evals/syllabus/run.py   # needs OPENAI_API_KEY; writes evals/syllabus/results.md
```

After changing dependencies, refresh the Docker requirements:

```bash
uv lock && uv export --frozen --no-dev --format requirements-txt -o requirements.lock.txt
```

Deployment: [`../docs/setup.md`](../docs/setup.md).
