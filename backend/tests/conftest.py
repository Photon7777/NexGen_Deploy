"""Test setup: a throwaway database with the real migrations, and signed test tokens.

Needs a Postgres with pgvector. Locally:
    docker run -d --name nexlearn-testdb -e POSTGRES_PASSWORD=postgres -p 54329:5432 pgvector/pgvector:pg17
CI starts the same image as a service container.
"""
import os
import time
import uuid
from pathlib import Path

import jwt
import psycopg
import pytest

ADMIN_URL = os.getenv("TEST_DATABASE_ADMIN_URL", "postgresql://postgres:postgres@localhost:54329/postgres")
TEST_DB = "nexlearn_test"
SECRET = "test-only-secret-at-least-thirty-two-bytes-long"
ROOT = Path(__file__).resolve().parents[2]


def make_token(sub: str, *, secret: str = SECRET, aud: str = "authenticated", expires_in: int = 3600) -> str:
    now = int(time.time())
    claims = {"sub": sub, "aud": aud, "role": "authenticated", "email": f"{sub[:8]}@umd.edu",
              "iat": now, "exp": now + expires_in}
    return jwt.encode(claims, secret, algorithm="HS256")


def auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer {make_token(user_id)}"}


@pytest.fixture(scope="session")
def database_url() -> str:
    try:
        admin = psycopg.connect(ADMIN_URL, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Test Postgres is not running (see the docstring in tests/conftest.py)")
    with admin:
        admin.execute(f"drop database if exists {TEST_DB} with (force)")
        admin.execute(f"create database {TEST_DB}")
    url = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute((Path(__file__).parent / "supabase_shim.sql").read_text())
        for migration in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
            conn.execute(migration.read_text())
    return url


@pytest.fixture(scope="session")
def client(database_url):
    # Explicit values beat backend/.env and the shell: tests never reach Supabase or OpenAI.
    os.environ.update(DATABASE_URL=database_url, SUPABASE_JWT_SECRET=SECRET, SUPABASE_URL="", OPENAI_API_KEY="")
    from fastapi.testclient import TestClient

    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_db(database_url):
    """Direct connection as postgres (bypasses RLS) for setup and assertions."""
    with psycopg.connect(database_url, autocommit=True) as conn:
        yield conn


@pytest.fixture
def make_user(admin_db):
    def _make(name: str = "Test Student") -> str:
        user_id = str(uuid.uuid4())
        admin_db.execute(
            "insert into auth.users (id, email, raw_user_meta_data) values (%s, %s, jsonb_build_object('full_name', %s::text))",
            (user_id, f"{user_id[:8]}@umd.edu", name),
        )
        return user_id

    return _make
