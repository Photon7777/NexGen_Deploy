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
| `app/routers/` | `/me`, `/assignments` (CRUD, sample data, progress history) |
| `tests/` | Runs against a real Postgres with the real migrations, including cross-student isolation tests |

Tests need a local Postgres with pgvector:

```bash
docker run -d --name nexlearn-testdb -e POSTGRES_PASSWORD=postgres -p 54329:5432 pgvector/pgvector:pg17
uv run pytest
```

After changing dependencies, refresh the Docker requirements:

```bash
uv lock && uv export --frozen --no-dev --format requirements-txt -o requirements.lock.txt
```

Deployment: [`../docs/setup.md`](../docs/setup.md).
